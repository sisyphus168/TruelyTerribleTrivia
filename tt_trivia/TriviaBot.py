import discord
import asyncio
import dotenv
import os
import logging
import re
import json
from QuestionSet import QuestionSet, Qtype
import FFAMultiChoice

# TODO: Write help message and commands list
HELP_MESSAGE = """
This will be the help message
"""

COMMANDS_LIST = """
Commands to Terrible Trivia Bot must be prefixed with "ttt". Commands are case insensitive.

Commands:
    - "commands" or "command list": Request this list
    - "help": Request the help message
    - "categories": get a list of categories
    - "start mc {1-50} {difficulty} {category}": Start a multiple choice free for all game.
        - 1-50 questions. Default of 20 questions.
        - type "ttt categories" for a list of categories. Default is general knowledge.
        - difficulties: easy, medium, hard. Leave blank for a mix.
    - "ttt end": Ends any currently running game.
"""


class TriviaBot(discord.Client):
    _sound_path: str
    _sounds_available: set[str] = set()
    _games: dict[int, FFAMultiChoice] = {}
    _voice_clients: dict[int, discord.VoiceClient] = {}
    _game_code_to_q_type: dict[str, Qtype] = {"mc": Qtype.MULTI_CHOICE,
                                              "tf": Qtype.TRUE_FALSE,
                                              "free": Qtype.FREE_RESPONSE}

    def __init__(self, sound_path):
        super(TriviaBot, self).__init__()
        self._sound_path = sound_path
        self._sounds_available = {wavfile for wavfile in os.listdir(self._sound_path) if wavfile.endswith(".wav")}
        self._games = {}
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
            vc: discord.VoiceChannel = discord.utils.get(guild.voice_channels, name="TerribleTrivia")
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
        if not msg.startswith("ttt "):
            return
        msg = msg.removeprefix("ttt ")
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
                q_set = self._parse_start_message(msg)
                if q_set is None:
                    await message.reply(f"Improper start game command: \"{msg}\".\nType \"ttt commands\" or \"ttt help\" for help")
                else:
                    await message.reply("Starting your game!")
                    print(q_set)
            else:
                await message.reply(f"Cannot start a new game while one is currently running on this server.")

    async def on_ready(self):
        logger.info(f"{self.user} logged on.")
        for guild in self.guilds:
            logger.info(f"Connected to guild {guild.name} with id {guild.id}")
        await self._init_voice_clients()

    async def speak(self, guild_id: int, announcements: list[tuple[str, str]]):
        # "Speaks" ie. prints a message and plays a sound over voice client (if possible)
        guild: discord.Guild = discord.utils.find(lambda g: g.id == guild_id, self.guilds)
        if guild is None:
            raise ValueError(f"Invalid guild id {guild_id}")
        text_channel: discord.TextChannel = discord.utils.get(guild.text_channels, name="terrible-trivia")
        voice_client: discord.VoiceClient = self._voice_clients.get(guild_id)
        for msg, sound_file in announcements:
            if text_channel is not None:
                await text_channel.send(msg)
            if voice_client is not None:
                while voice_client.is_playing():
                    await asyncio.sleep(1)
                audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(os.path.join(self._sound_path, sound_file)))
                voice_client.play(audio_source)

    def _parse_start_message(self, msg: str) -> QuestionSet | None:
        # Some wacky regex to parse and extract the start command args. Pass via arglist to QuestionSet ctor
        # TODO: something wrong with the diff RE group
        command_pattern = re.compile("start (mc|tf|free)( num \d{1,2})?( diff (easy|medium|hard))?( cat [a-zA-Z &]+)?")
        num_pattern = re.compile("num \d{1,2}")
        diff_pattern = re.compile("diff easy|medium|hard")
        cat_pattern = re.compile("cat [a-zA-Z &]+")
        if command_pattern.fullmatch(msg) is None:
            logger.info("Invalid start command:", msg)
            return None
        try:
            chunks = msg.removeprefix("start ").split()
            q_type = self._game_code_to_q_type[chunks[0]]
            kwargs = {}
            if match := num_pattern.search(msg):
                kwargs["num"] = int(msg[match.start()+4: match.end()])
            if match := diff_pattern.search(msg):
                kwargs["difficulty"] = msg[match.start()+5: match.end()]
            if match := cat_pattern.search(msg):
                kwargs["category"] = msg[match.start()+4: match.end()]
            return QuestionSet(q_type, **kwargs)
        except Exception as e:
            logger.error(f"Exception: {e}")
            print(e)
            return None

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
