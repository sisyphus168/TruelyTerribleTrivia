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
        self._logger.exception(f"Critical failure ancountereD: {e}")
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


