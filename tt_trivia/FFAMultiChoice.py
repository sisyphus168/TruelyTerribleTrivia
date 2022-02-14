import enum
from QuestionSet import QuestionSet, Qtype
from TriviaBot import TriviaBot
import discord
import os

SKIP_THRESHOLD = 2/3


class GameStatus(enum.Enum):
    STARTING = 0
    GETTING_PLAYERS = 1
    ASKING = 2
    WAIT_ANSWERS = 3
    QUESTION_RESULT = 4
    ENDING = 5
    FAILED = 6


class FFAMultiChoice:
    _status: GameStatus
    _players: set[str]
    _scores: dict[str: int]
    _player_count: int
    _skip_votes: int
    _questions: QuestionSet
    _guild_id: int
    _trivia_bot: TriviaBot

    def __init__(self, q_set: QuestionSet, g_id: int, bot: TriviaBot):
        self._status = GameStatus.STARTING
        self._players = set()
        self._player_count = 0
        self._questions = q_set
        self._guild_id = g_id
        self._trivia_bot = bot
        if not q_set.is_initialized():
            self._questions.initialize()
        pass

    def add_player(self, player: discord.User):
        player_name = player.name
        if player_name not in self._players:
            self._players.add(player_name)
            self._player_count += 1
            self._scores[player_name] = 0

    def vote_skip(self):
        self._skip_votes += 1
        if self._skip_votes >= SKIP_THRESHOLD:
            # TODO: Whatever needs to be done to skip this question
            pass

    def receive_answer(self, answer):
        pass

    async def start(self):
        pass

    async def end(self):
        pass

    async def end_question(self):
        pass

    async def end_game(self):
        pass
