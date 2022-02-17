import enum
import time
import random
from QuestionSet import QuestionSet, Qtype, MCQuestion
import discord
from Player import PLayer
import asyncio
import os

SKIP_THRESHOLD = 2/3
# # of seconds to wait
WAIT_PLAYERS = 10
MAX_PLAYERS = 20
ANSWER_TIME = 30


class GameStatus(enum.Enum):
    STARTING = 0
    GETTING_PLAYERS = 1
    ASKING = 2
    WAIT_ANSWERS = 3
    QUESTION_RESULTS = 4
    ENDING = 5
    FAILED = 6


class FFAMultiChoice:
    # Delayed import to avoid cyclic import
    _status: GameStatus
    _players: dict[int, PLayer]
    _player_count: int
    _questions: QuestionSet
    _guild_id: int
    _current_question: MCQuestion | None
    _skipped_questions: int

    def __init__(self, q_set: QuestionSet, g_id: int, bot):
        self._status = GameStatus.STARTING
        self._players = {}
        self._player_count = 0
        self._questions = q_set
        self._guild_id = g_id
        self._trivia_bot = bot
        self._current_question = None
        self._skipped_questions = 0

    def add_player(self, player_user: discord.User) -> bool:
        if self._status == GameStatus.GETTING_PLAYERS:
            p_name = player_user.name
            p_id = player_user.id
            if id not in self._players:
                player = PLayer(p_name, p_id, 0, 0, True)
                self._players[p_id] = player
                self._player_count += 1
                print(f"Added player {player}")
                return True
        return False

    def receive_answer(self, message: discord.Message):
        ans = message.content.lower().strip()
        print(f"Receiving answer {ans}")
        if self._current_question is None:
            raise RuntimeError(f"record_answer called for game {self.get_guild_id()} when no question was set.")
        # Skip if message was from non-player
        if message.author.id not in self._players:
            return
        if ans in {"a", "b", "c", "d", "skip!"} or ans in [a.strip().lower() for a in self._current_question.choices]:
            self._players[message.author.id].answer = ans

    async def start(self):
        try:
            if not self._questions.is_initialized():
                await self._questions.initialize()
            await self._set_status(GameStatus.GETTING_PLAYERS)
        except Exception as e:
            await self._set_status(GameStatus.FAILED)

    async def _wait_players(self):
        print("Waiting for players")
        try:
            await self._trivia_bot.say(self.get_guild_id(),
                                       f"Game starting in {WAIT_PLAYERS} seconds. Type \"play\" to join!")
            half_wait = round(WAIT_PLAYERS/2)
            start = time.perf_counter()
            await asyncio.sleep(half_wait)
            await self._trivia_bot.say(self.get_guild_id(),
                                       f"Game starting in {half_wait} seconds. Type \"play\" to join!")
            await asyncio.sleep(half_wait)
            end = time.perf_counter()
            print(f"Waited {end - start:.4f} seconds. ")
            # if nobody played, cleanup and exit
            if self._player_count < 1:
                await self._trivia_bot.say(self._guild_id, "Nobody wanted to play... sad.")
                await self._set_status(GameStatus.ENDING)
                return
            start_msg = f"\nFree for all difficulty: {self._questions.get_difficulty()} category: {self._questions.get_category()}.\n"
            start_msg += f"If you wish to skip a question answer with \"skip!\". {SKIP_THRESHOLD:.0%} of players must vote to skip.\n"
            start_msg += "Game starting momentarily.\nPlayers:"
            for player in self._players.values():
                start_msg += f"\n\t- {player.name}"
            await self._trivia_bot.say(self.get_guild_id(), start_msg, "prepare.wav")
            random.seed(time.time())
            await asyncio.sleep(random.randint(3, 8))
            await self._set_status(GameStatus.ASKING)
        except Exception as e:
            print("Exception:", e)

    async def _ask_next_question(self):
        print("Asking Question")
        question: MCQuestion = next(self._questions)
        self._current_question = question
        q_str = f"Question No {self._questions.get_index()}:\n"
        q_str += f"{question.question}\n"
        correct_ans = "abcd"[question.answer_index]
        for char, answer in zip("abcd", question.choices):
            q_str += f"\n\t{char}. {answer}"
        await self._trivia_bot.speak(self._guild_id, [(q_str, None), (f"\n{ANSWER_TIME} seconds to answer.", None)])
        await self._set_status(GameStatus.WAIT_ANSWERS)

    async def _wait_answers(self):
        await asyncio.sleep(ANSWER_TIME - 5)
        await self._trivia_bot.say(self._guild_id, "5 seconds left!")
        await asyncio.sleep(5)
        await self._set_status(GameStatus.QUESTION_RESULTS)

    def _clear_last_question(self):
        self._current_question = None
        for player in self._players.values():
            player.answer = ""

    async def end_question(self):
        # TODO: Implement
        pass

    async def end_game(self):
        # TODO: Implement
        pass

    async def _set_status(self, status: GameStatus, *args):
        # Transition function for various game states
        self._status = status
        print(f"Status of game {self._guild_id} set to {self._status}")
        if self._status == GameStatus.FAILED:
            await self._trivia_bot.say(self._guild_id, ("Oops, something went wrong, game ending! Everybody loses :("))
        elif self._status == GameStatus.GETTING_PLAYERS:
            await self._wait_players()
        elif self._status == GameStatus.ASKING:
            await self._ask_next_question()
        elif self._status == GameStatus.WAIT_ANSWERS:
            await self._wait_answers()
        elif self._status == GameStatus.QUESTION_RESULTS:
            for player in self._players.values():
                print(f"Player {player.name} answered: {player.answer}")
            print("I'd have looked at the answers, said some funny shit, streaks, then reset questions and all that")
        elif self._status == GameStatus.ENDING:
            if self._player_count > 0:
                print(f"I'd have computed the winner and played silly sounds, etc.")
            self._trivia_bot.cleanup_game(self)

    def get_guild_id(self):
        return self._guild_id

    def get_state(self):
        return self._status
