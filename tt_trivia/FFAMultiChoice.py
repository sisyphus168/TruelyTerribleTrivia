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


class GameStatus(enum.Enum):
    STARTING = 0
    GETTING_PLAYERS = 1
    ASKING = 2
    WAIT_ANSWERS = 3
    QUESTION_RESULT = 4
    ENDING = 5
    FAILED = 6


class FFAMultiChoice:
    # Delayed import to avoid cyclic import
    _status: GameStatus
    _players: dict[int, PLayer]
    _player_count: int
    _skip_votes: int
    _questions: QuestionSet
    _guild_id: int

    def __init__(self, q_set: QuestionSet, g_id: int, bot):
        self._status = GameStatus.STARTING
        self._players = {}
        self._player_count = 0
        self._questions = q_set
        self._guild_id = g_id
        self._trivia_bot = bot

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

    def vote_skip(self):
        self._skip_votes += 1
        if self._skip_votes >= SKIP_THRESHOLD:
            # TODO: Whatever needs to be done to skip this question
            pass

    def receive_answer(self, answer):
        pass

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
                                       f"Game starting in {WAIT_PLAYERS} seconds. Type \"ttt play\" to join!")
            half_wait = round(WAIT_PLAYERS/2)
            start = time.perf_counter()
            await asyncio.sleep(half_wait)
            await self._trivia_bot.say(self.get_guild_id(),
                                       f"Game starting in {half_wait} seconds. Type \"ttt play\" to join!")
            await asyncio.sleep(half_wait)
            end = time.perf_counter()
            print(f"Waited {end - start:.4f} seconds. ")
            if self._player_count < 1:
                await self._trivia_bot.say("Nobody wanted to play... sad.")
            start_msg = f"\nFree for all difficulty: {self._questions.get_difficulty()} category: {self._questions.get_category()}.\n"
            start_msg += "Game starting momentarily.\nPlayers:"
            for player in self._players.values():
                start_msg += f"\n\t- {player.name}"
            await self._trivia_bot.say(self.get_guild_id(), start_msg, "prepare.wav")
            random.seed(time.time())
            await asyncio.sleep(random.randint(5, 11))
            await self._set_status(GameStatus.ASKING)
        except Exception as e:
            print("Exception:", e)


    async def end_question(self):
        pass

    async def end_game(self):
        pass

    def get_state(self):
        return self._status

    async def _set_status(self, status: GameStatus):
        # Transition function for various game states
        self._status = status
        if self._status == GameStatus.FAILED:
            await self._trivia_bot.say(self._guild_id, ("Oops, something went wrong, game ending! Everybody loses :("))
        elif self._status == GameStatus.GETTING_PLAYERS:
            await self._wait_players()
        elif self._status == GameStatus.ASKING:
            # TODO: implement an actual ask question function
            for querstion in self._questions:
                q = querstion.question
                await self._trivia_bot.say(self._guild_id, q, "unreal.wav")
            await self._set_status(GameStatus.ENDING)
        elif self._status == GameStatus.ENDING:
            if self._player_count > 0:
                print(f"I'd have computed the winner and played silly sounds, etc.")
            # TODO: Figure out why this didn't delete teh game
            self._trivia_bot.cleanup_game(self)

    def get_guild_id(self):
        return self._guild_id
