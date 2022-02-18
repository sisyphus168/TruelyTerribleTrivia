import enum
import time
import random
from QuestionSet import QuestionSet, MCQuestion
import discord
from Player import PLayer
import asyncio

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
            random.seed(time.time())
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
            start_msg += f"If you wish to skip a question answer \"skip!\". "
            start_msg += f"To skip {SKIP_THRESHOLD:.0%} of players or more must vote to skip."
            start_msg += f" Otherwise a skip vote counts as an incorrect answer.\n"
            start_msg += "Game starting momentarily.\nPlayers:"
            for player in self._players.values():
                start_msg += f"\n\t- {player.name}"
            start_msg += "\n\n"
            await self._trivia_bot.say(self.get_guild_id(), start_msg, "prepare.wav")
            await asyncio.sleep(5)
            await self._set_status(GameStatus.ASKING)
        except Exception as e:
            print("Exception:", e)

    async def _ask_next_question(self):
        print("Asking Question")
        question: MCQuestion = next(self._questions, None)
        # If none, then we're outta questions end the game
        if question is None:
            print("All outta questions")
            await self._set_status(GameStatus.ENDING)
            return
        self._current_question = question
        q_str = f"Question No {self._questions.get_index()}:\n"
        q_str += f"{question.question}"
        for char, answer in zip("abcd", question.choices):
            q_str += f"\n\t{char}. {answer}"
        await self._trivia_bot.speak(self._guild_id, [(q_str, None), (f"\n{ANSWER_TIME} seconds to answer.", None)])
        # TODO: Remove this, debugging/testing purposes only... unless...
        print("answer:", self._current_question.answer)
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

    async def _end_question(self):
        if self._skip_question():
            self._skipped_questions += 1
            await self._trivia_bot.say(self._guild_id, "Question skipped!")
        # Loop over players, update their scores, streak, and perfect status
        else:
            correct = []
            answer = f"{'abcd'[self._current_question.answer_index]}. {self._current_question.answer}"
            correct_msg = f"Correct Answer: {answer}\nCorrect Players:"
            scores_msg = "Scores:"
            for player in self._players.values():
                if player.answer != "skip!" and self._check_answer(player.answer):
                    player.score += 1
                    player.streak += 1
                    correct.append(player)
                    correct_msg += f"\n\t- {player.name}"
                else:
                    player.perfect = False
                    player.streak = 0
                scores_msg += f"\n\t{player.name}: {player.score}"
                print(f"{player=}")
            question_sum_msg = correct_msg + "\n" + scores_msg + "\n"
            await self._trivia_bot.say(self._guild_id, question_sum_msg, None)
            await self._question_report(correct)
        # Game flow should allow a brief pause here
        await asyncio.sleep(5)
        await self._set_status(GameStatus.ASKING)

    async def _question_report(self, correct_players: list[PLayer]):
        # Method to report the scores after the question, and announce streak callouts
        callouts = set()
        announcements = []
        for player in correct_players:
            streak = player.streak
            if streak > 2:
                steak_msg = f"{player.name} is on a {streak}-streak!"
                streak_wav = f"{streak}streak.wav"
                # Let's not spam the voice channel, check if the announcement is already going to play
                if streak_wav not in callouts:
                    callouts.add(streak_wav)
                    announcements.append((steak_msg, streak_wav))
                else:
                    announcements.append((steak_msg, None))
        await self._trivia_bot.speak(self._guild_id, announcements)

    def _check_answer(self, answer) -> bool:
        assert self._status == GameStatus.QUESTION_RESULTS
        # Players can answer with either a-d, or typing the full answer
        answer = answer.lower()
        if answer in {"a", "b", "c", "d"}:
            return self._current_question.answer_index == MCQuestion.get_index(answer)
        if self._current_question.answer.lower() == answer:
            return True
        return False

    def _skip_question(self) -> bool:
        assert self._status == GameStatus.QUESTION_RESULTS
        votes = len([p for p in self._players.values() if p.answer.lower() == "skip!"])
        threshold = round(SKIP_THRESHOLD * len(self._players))
        return votes >= threshold

    async def _end_game(self):
        print("ending game")
        try:
            players: list[PLayer] = list(self._players.values())
            print("about to sort")
            players.sort(reverse=True, key=lambda p: p.score)
            print("sorted")
            winner = players[0]
            print("looping through to make final score report")
            game_report = "Final scores:\n"
            for i, player in enumerate(players):
                print(f"{i=}\t{player=}")
                game_report += f"{i + 1}. {player}: {player.score}\n"
            print("About to wait for the victory announcement to play")
            await self._trivia_bot.say(self._guild_id, f"<@{winner.id}> is the winner with {winner.score} points!",
                                       "victory.wav")
            # Quite an achievement
            print("checking if player is perfect")
            if winner.is_perfect():
                await self._trivia_bot.say(self._guild_id, f"<@{winner.id}> was perfect for the game!", "flawless.wav")
        except Exception as e:
            print(e)
            raise e

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
            await self._end_question()
        elif self._status == GameStatus.ENDING:
            if self._player_count > 0:
                await self._end_game()
            self._trivia_bot.cleanup_game(self)

    def get_guild_id(self):
        return self._guild_id

    def get_state(self):
        return self._status
