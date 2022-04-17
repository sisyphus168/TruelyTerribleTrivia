import nextcord
import asyncio
import dotenv
import os
import logging
import re
import json
from QuestionSet import QuestionSet, Qtype
from FFAMultiChoice import FFAMultiChoice, GameStatus
from FFALives import FFALives

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
    "mc": FFAMultiChoice,
    "lives": FFALives
}


class TriviaBot(nextcord.Client):
    _sound_path: str
    _sounds_available: set[str]
    _games: dict[int, FFAMultiChoice]
    _voice_clients: dict[int, nextcord.VoiceClient]
    _game_code_to_q_type: dict[str, Qtype]
    _vol_settings: dict[int:int]

    def __init__(self, sound_path):
        super(TriviaBot, self).__init__()
        self._game_code_to_q_type = {"mc": Qtype.MULTI_CHOICE,
                                     "lives": Qtype.MULTI_CHOICE,
                                     "tf": Qtype.TRUE_FALSE,
                                     "free": Qtype.FREE_RESPONSE}
        self._sound_path = sound_path
        self._sounds_available = {wavfile for wavfile in os.listdir(self._sound_path) if wavfile.endswith(".wav")}
        self._games = {}
        self._voice_clients = {}
        self._categories = {}
        self._vol_settings = {}
        with open(f"{os.getenv('CATEGORIES')}", "r") as f:
            self._categories = set(json.load(f).keys())

    async def _cleanup_clients(self):
        for client in self._voice_clients.values():
            print(f"Closing client: {client}")
            await client.disconnect()

    async def _init_voice_clients(self):
        for guild in self.guilds:
            g_id = guild.id
            vc: nextcord.VoiceProtocol = nextcord.utils.get(guild.voice_channels, name="TerribleTrivia")
            if vc is not None:
                client = await vc.connect()
                self._voice_clients[g_id] = client
                print(f"new client for {vc}: {self._voice_clients[g_id]}")
            else:
                print(f"Failed to find voice channel for guild {guild.name}")

    async def on_message(self, message: nextcord.Message):
        if message.author.id == self.user.id:
            return
        # Does message start with ttt?
        msg = str(message.content).lower()
        if msg.startswith("ttt "):
            msg = msg.removeprefix("ttt ").strip()
            channel: nextcord.TextChannel = message.channel
            if msg == "help" or msg == "commands" or msg == "command list":
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
            elif msg.startswith("vol"):
                await self._set_volume(msg, message.guild.id)
        elif self.has_game(message.guild.id):
            await self._pass_message_to_game(message, message.guild.id)

    async def _set_volume(self, msg: str, guild_id: int) -> None:
        # users can query what the volume is set to
        if re.match(pattern="vol(\s)+\?", string=msg) is not None:
            curr_vol = self._vol_settings[guild_id]
            await self.say(guild_id, f"Current bot volume: {curr_vol}%", None, None)
            return
        if re.match(pattern="vol(\s)+(\d){1,3}", string=msg) is None:
            await self.say(guild_id, "Invalid volume command", None, None)
            return
        vol_setting = int(msg.removeprefix("vol").strip())
        if vol_setting > 100 or vol_setting < 0:
            await self.say(guild_id, f"Invalid volume value: {vol_setting}", None, None)
            return
        self._vol_settings[guild_id] = vol_setting
        await self.say(guild_id, f"bot volume set to {vol_setting}%", None, None)

    async def _pass_message_to_game(self, message: nextcord.Message, g_id: int):
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
            # set volumes to 50% by default
            self._vol_settings[guild.id] = 50
        await self._init_voice_clients()

    async def speak(self, guild_id: int, announcements: list[tuple[str, str | None]]):
        # "Speaks" ie. prints a message and plays a sound over voice client (if possible)
        guild: nextcord.Guild = nextcord.utils.find(lambda g: g.id == guild_id, self.guilds)
        if guild is None:
            raise ValueError(f"Invalid guild id {guild_id}")
        for announcement in announcements:
            await self.say(guild_id, announcement[0], announcement[1])

    async def say(self, guild_id: int, msg: str, sound_file: str | None = None, view: nextcord.ui.View | None = None):
        """
        "Speaks" ie. prints a message and plays a sound over voice client (if possible)
        :param guild_id:
        :param msg:
        :param sound_file:
        :param view:
        :return: None
        """
        guild: nextcord.Guild = nextcord.utils.find(lambda g: g.id == guild_id, self.guilds)
        if guild is None:
            raise ValueError(f"Invalid guild id {guild_id}")
        text_channel: nextcord.TextChannel = nextcord.utils.get(guild.text_channels, name="terrible-trivia")
        voice_client: nextcord.VoiceClient = self._voice_clients.get(guild_id)
        if text_channel is not None:
            await text_channel.send(msg, view=view)
        if voice_client is not None and sound_file is not None:
            vol = self._vol_settings[guild_id]
            while voice_client.is_playing():
                await asyncio.sleep(1)
            source_path = os.path.join(self._sound_path, sound_file)
            audio_source = nextcord.PCMVolumeTransformer(nextcord.FFmpegPCMAudio(source_path), volume=(vol/100))
            voice_client.play(audio_source)

    async def _setup_game(self, msg: str, guild_id: int):
        parsed_setup_tuple = self._parse_start_message(msg)
        if parsed_setup_tuple is None or len(parsed_setup_tuple) != 3:
            return False
        try:
            game_mode = parsed_setup_tuple[0]
            print(f"Game Mode: {game_mode}\nGAMEMODE_CLASSES keys:")
            for k in GAMEMODE_CLASSES.keys():
                print(k)
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
        command_pattern = re.compile("start (mc|tf|free|lives)( \d{1,2})?( (easy|medium|hard))?( cat [a-zA-Z &]+$)?")
        num_pattern = re.compile("\d{1,2}")
        diff_pattern = re.compile("easy|medium|hard")
        cat_pattern = re.compile("cat [a-zA-Z &]+$")
        gamemode_pattern = re.compile("(mc|tf|free|lives)")
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
                print("Matched a game mode")
                game_mode = msg[match.start(): match.end()].strip()
                return game_mode, q_type, q_set_kwargs  # QuestionSet(q_type, **kwargs)
            else:
                logger.error("I botched the RegEx")
                return None
        except Exception as err:
            logger.error(f"Exception: {type(err)} {err}")
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
    logger = logging.getLogger('nextcord')
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
