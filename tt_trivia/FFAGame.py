from abc import ABC, abstractmethod, abstractproperty
import enum
import asyncio
from logging import Logger
from collections import deque
import time
import random
import QuestionSet
from Player import Player
import nextcord


# TODO: These should probably be set via .env
SKIP_THRESHOLD = 2/3
# # of seconds to wait
MAX_PLAYERS = 20
ANSWER_TIME = 20
WAIT_PLAYERS = 20


class GameStatus(enum.Enum):
    STARTING = 0
    GETTING_PLAYERS = 1
    ASKING = 2
    WAIT_ANSWERS = 3
    QUESTION_RESULTS = 4
    ENDING = 5
    FAILED = 6
    STOPPED = 7


class FFAGame(ABC):
    _status: GameStatus
    _players: dict[int, Player]
    _player_count: int
    _questions: QuestionSet
    _guild_id: int
    _current_question: QuestionSet.Question | None
    _current_view: nextcord.ui.View | None
    _skipped_questions: int
    _task_stack: deque[asyncio.Task]
    _logger: Logger

    # Abstract methods
    @abstractmethod
    def __init__(self, g_id, bot, logger):
        self._status = GameStatus.STARTING
        self._players = {}
        self._player_count = 0
        self._guild_id = g_id
        self._trivia_bot = bot
        self._current_question = None
        self._skipped_questions = 0
        self._task_stack = deque(maxlen=250)
        self._logger = logger

    @abstractmethod
    def receive_answer(self, message: nextcord.Message):
        pass

    @abstractmethod
    def receive_button_answer(self, answer: str, interaction: nextcord.Interaction):
        pass

    @abstractmethod
    async def _set_status(self, status: GameStatus, **kwargs):
        pass

    # inheritable methods
    def add_player(self, player_user: nextcord.user) ->  bool:
        if self._status == GameStatus.GETTING_PLAYERS:
            p_name = player_user.name
            p_id = player_user.id
            if id not in self._players:
                player = Player(p_name, p_id, 0, 0, True)
                self._players[p_id] = player
                self._player_count += 1
                self._logger.info(f"Added player {player}")
                return True
        return False

    async def start(self):
        random.seed(time.time())
        if not self._questions.is_initialized():
            await self._questions.initialize()
        await self._set_status(GameStatus.GETTING_PLAYERS)

    async def end(self):
        await self._set_status(GameStatus.STOPPED)

    def get_guild_id(self):
        return self._guild_id

    def get_state(self):
        return self._status

    async def _handle_failed_game(self, e: Exception):
        self._logger.exception(f"Critical failure encountered: {e}")
        self._flush_tasks()
        self._trivia_bot.cleanup_game(self)
        await self._trivia_bot.say(self._guild_id, "Critical error encountered. Stopping game.")

    async def _stop_game(self):
        print(f"game stopped")
        self._flush_tasks()
        self._trivia_bot.cleanup_game(self)
        await self._trivia_bot.say(self._guild_id, "Game stopped.")

    def _flush_tasks(self):
        # Method to cancel up the coroutine tasks in the task stack
        while len(self._task_stack) > 0:
            task = self._task_stack.pop()
            if task is not None:
                task.cancel()

    async def _wait_answers(self):
        await asyncio.sleep(ANSWER_TIME - 5)
        start = time.perf_counter()
        await self._trivia_bot.say(self._guild_id, "5 seconds left!", "countdown5.wav")
        end = time.perf_counter()
        # Pad out the full 5 seconds
        await asyncio.sleep(5 - (end-start))
        await self._set_status(GameStatus.QUESTION_RESULTS)

    async def _wait_players(self, game_name):
        self._logger.info("Waiting for players")
        await self._trivia_bot.say(self.get_guild_id(),
                                   f"Game starting in {WAIT_PLAYERS} seconds. Type \"play\" to join!\n\n")
        half_wait = round(WAIT_PLAYERS/2)
        start = time.perf_counter()
        await asyncio.sleep(half_wait)
        await self._trivia_bot.say(self.get_guild_id(),
                                   f"Game starting in {half_wait} seconds. Type \"play\" to join!\n\n")
        await asyncio.sleep(half_wait)
        end = time.perf_counter()
        self._logger.info(f"Waited {end - start:.4f} seconds. ")
        # if nobody played, cleanup and exit
        if self._player_count < 1:
            await self._trivia_bot.say(self._guild_id, "Nobody wanted to play... sad.")
            await self._set_status(GameStatus.ENDING)
            return
        start_msg = f"\n**Starting {game_name}\t difficulty: {self._questions.get_difficulty()}\t category: {self._questions.get_category()}\n**"
        start_msg += f"If you wish to skip a question answer \"skip!\". "
        start_msg += f"The question will be skipped if {SKIP_THRESHOLD:.0%} or more of players vote to skip."
        start_msg += f" If it's not skipped all skip votes count as an incorrect answer.\n"
        start_msg += "Game starting momentarily.\nPlayers:"
        for player in self._players.values():
            start_msg += f"\n\t- {player.name}"
        start_msg += "\n\n"
        await self._trivia_bot.say(self.get_guild_id(), start_msg, "prepare.wav")
        await asyncio.sleep(5)
        await self._set_status(GameStatus.ASKING)
