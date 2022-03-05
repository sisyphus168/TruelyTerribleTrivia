import discord
import asyncio
import dotenv
import os
import logging
import re
import json
from QuestionSet import QuestionSet, Qtype
from FFAMultiChoice import FFAMultiChoice, GameStatus

# TODO: Write help message and commands list
HELP_MESSAGE = """
TODO: help message for now type ttt commands for a commands list
"""

COMMANDS_LIST = """
Commands to Terrible Trivia Bot must be prefixed with "ttt". Commands are case insensitive.

Commands:
    - "commands" or "command list": Request a list of commands 
    - "help": Request the help message
    - "categories": get a list of categories
    - "start mc {num of questions 1-50} {difficulty} cat {category}": Start a multiple choice free for all game.
        - **Note**: Only "start mc" and "start mc num" work right now
        - 1-50 questions. Default of 20 questions.
        - type "ttt categories" for a list of categories. Default is general knowledge.
        - difficulties: easy, medium, hard. Leave blank for a mix.
    - "ttt end": Ends any currently running game.
"""

GAMEMODE_CLASSES = {
    "mc": FFAMultiChoice
}


class TriviaBot(discord.Client):
    _sound_path: str
    _sounds_available: set[str]
    _games: dict[int, FFAMultiChoice]
    _voice_clients: dict[int, discord.VoiceClient]
    _game_code_to_q_type: dict[str, Qtype]

    def __init__(self, sound_path):
        super(TriviaBot, self).__init__()
        self._game_code_to_q_type = {"mc": Qtype.MULTI_CHOICE,
                                     "tf": Qtype.TRUE_FALSE,
                                     "free": Qtype.FREE_RESPONSE}
        self._sound_path = sound_path
        self._sounds_available = {wavfile for wavfile in os.listdir(self._sound_path) if wavfile.endswith(".wav")}
        self._games = {}
        self._voice_clients = {}
        self._categories = {}
        with open(f"{os.getenv('CATEGORIES')}", "r") as f:
            self._categories = set(json.load(f).keys())

    async def _cleanup_clients(self):
        for client in self._voice_clients.values():
            print(f"Closing client: {client}")
            await client.disconnect()

    async def _init_voice_clients(self):
        for guild in self.guilds:
            g_id = guild.id
            vc: discord.VoiceProtocol = discord.utils.get(guild.voice_channels, name="TerribleTrivia")
            if vc is not None:
                client = await vc.connect()
                self._voice_clients[g_id] = client
                print(f"new client for {vc}: {self._voice_clients[g_id]}")
            else:
                print(f"Failed to find voice channel for guild {guild.name}")

    async def on_message(self, message: discord.Message):
        if message.author.id == self.user.id:
            return
        # Does message start with ttt?
        msg = str(message.content).lower()
        if msg.startswith("ttt "):
            msg = msg.removeprefix("ttt ").strip()
            channel: discord.TextChannel = message.channel
            if msg == "help":
                await channel.send(HELP_MESSAGE)
            elif msg == "commands" or msg == "command list":
                await channel.send(COMMANDS_LIST)
            elif msg == "categories":
                cat_string = "Categories:\n\t- " + "\n\t- ".join(self._categories)
                await channel.send(cat_string)
            elif msg.startswith("start "):
                # only start a game if one is not already begun for this guild
                if message.guild.id not in self._games:
                    if await self._setup_game(msg, message.guild.id):
                        await message.reply("**Success! Starting your game...**\n")
                        await self._games[message.guild.id].start()
                    else:
                        await message.reply("Ooops, invalid start command. Type \"ttt help\" or \"ttt commands\" for help.")
                else:
                    await message.reply(f"Cannot start a new game while one is currently running on this server.")
            elif msg == "end":
                if self.has_game(message.guild.id):
                    await self._games[message.guild.id].end()
        elif self.has_game(message.guild.id):
            await self._pass_message_to_game(message, message.guild.id)

    async def _pass_message_to_game(self, message: discord.Message, g_id: int):
        game: FFAMultiChoice = self._games[g_id]
        if game.get_state() == GameStatus.GETTING_PLAYERS:
            if message.content.startswith("play"):
                print(type(message.author))
                if game.add_player(message.author):
                    await self.say(g_id, f"{message.author.name} added to players!")
        elif game.get_state() == GameStatus.WAIT_ANSWERS:
            game.receive_answer(message)

    async def on_ready(self):
        logger.info(f"{self.user} logged on.")
        for guild in self.guilds:
            logger.info(f"Connected to guild {guild.name} with id {guild.id}")
        await self._init_voice_clients()

    async def speak(self, guild_id: int, announcements: list[tuple[str, str | None]]):
        # "Speaks" ie. prints a message and plays a sound over voice client (if possible)
        guild: discord.Guild = discord.utils.find(lambda g: g.id == guild_id, self.guilds)
        if guild is None:
            raise ValueError(f"Invalid guild id {guild_id}")
        text_channel: discord.TextChannel = discord.utils.get(guild.text_channels, name="terrible-trivia")
        voice_client: discord.VoiceClient = self._voice_clients.get(guild_id)
        for msg, sound_file in announcements:
            if text_channel is not None:
                await text_channel.send(msg)
            if voice_client is not None and sound_file is not None:
                while voice_client.is_playing():
                    await asyncio.sleep(1)
                source_path = os.path.join(self._sound_path, sound_file)
                audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source_path))
                voice_client.play(audio_source)

    async def say(self, guild_id: int, msg: str, sound_file: str | None = None):
        await self.speak(guild_id, [(msg, sound_file)])

    async def _setup_game(self, msg: str, guild_id: int):
        parsed_setup_tuple = self._parse_start_message(msg)
        if parsed_setup_tuple is None or len(parsed_setup_tuple) != 3:
            return False
        try:
            game_mode = parsed_setup_tuple[0]
            q_set_kwargs = parsed_setup_tuple[2]
            game = GAMEMODE_CLASSES[game_mode](q_set_kwargs, guild_id, self, logger)
            self._games[guild_id] = game
            return True
            # else:
            #     return False
        except ValueError | AssertionError as err:
            logger.error(f"Exception: {err}")
            return False

    def _parse_start_message(self, msg: str) -> tuple[str, QuestionSet] | None:
        # Some wacky regex to parse and extract the start command args. Pass via arglist to QuestionSet ctor
        print(f"{msg=}")
        command_pattern = re.compile("start (mc|tf|free)( \d{1,2})?( (easy|medium|hard))?( cat [a-zA-Z &]+$)?")
        num_pattern = re.compile("\d{1,2}")
        diff_pattern = re.compile("easy|medium|hard")
        cat_pattern = re.compile("cat [a-zA-Z &]+$")
        gamemode_pattern = re.compile("(mc|tf|free)")
        if command_pattern.fullmatch(msg) is None:
            logger.info(f"Invalid start command: {msg}")
            return None
        try:
            chunks = msg.removeprefix("start ").split()
            q_type = self._game_code_to_q_type[chunks[0]]
            q_set_kwargs = {}
            if match := num_pattern.search(msg):
                q_set_kwargs["num"] = int(msg[match.start(): match.end()])
            if match := diff_pattern.search(msg):
                q_set_kwargs["difficulty"] = msg[match.start(): match.end()]
            if match := cat_pattern.search(msg):
                q_set_kwargs["category"] = msg[match.start()+4: match.end()]  # add 4 to remove "cat" portion
            if match := gamemode_pattern.search(msg):
                game_mode = msg[match.start(): match.end()].strip()
                return game_mode, q_type, q_set_kwargs  # QuestionSet(q_type, **kwargs)
            else:
                logger.error("I botched the RegEx")
                return None
        except Exception as err:
            logger.error(f"Exception: {err}")
            return None

    def cleanup_game(self, game: FFAMultiChoice):
        g_id = game.get_guild_id()
        if self.has_game(g_id):
            print(f"Deleting game for guild: {g_id}")
            del self._games[g_id]

    def has_game(self, g_id: int):
        return g_id in self._games

    async def close(self):
        await self._cleanup_clients()
        await super().close()


async def main(bot):
    token = os.getenv("TOKEN")
    if token is not None:
        try:
            await bot.start(token)
        except KeyboardInterrupt as e:
            print(f"Cleaning up bot")
            await bot.cleanup()
            await bot.close()
    else:
        logger.error("Failed to start bot. No token in .env file.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Add some logging
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='trivia.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    dotenv.load_dotenv("../.env")
    sound_dir = os.getenv("SOUNDS")
    bot = TriviaBot(sound_dir)
    try:
        loop.run_until_complete(main(bot))
    except KeyboardInterrupt as e:
        loop.run_until_complete(bot.close())
    finally:
        loop.close()
