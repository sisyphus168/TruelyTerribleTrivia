from FFAGame import GameStatus, ANSWER_TIME
from FFAMultiChoice import FFAMultiChoice, McQuestionView
import nextcord
import time
import random
from QuestionSet import QuestionSet, MCQuestion, Qtype
from Player import Player
import asyncio


class FFALives(FFAMultiChoice):

    _current_question = QuestionSet
    _question_number: int

    def __init__(self, q_set_kwargs: dict[str,str|int], g_id: int, bot, logger):
        print("Called FFALives init")
        # Always grab 50 q's as
        q_set_kwargs["num"] = 50
        super().__init__(q_set_kwargs, g_id, bot, logger)
        self._question_number = 1
        random.seed(time.time())

    def add_player(self, player_user: nextcord.user) -> bool:
        added = super().add_player(player_user)
        # Players in the game mode start with 10 lives
        if added:
            self._players[player_user.id].score = 10
        return added

    async def _ask_next_question(self):
        self._logger.info("Asking Question")
        question: MCQuestion = next(self._questions, None)
        # If none, then we're outta questions end the game
        if question is None:
            self._logger.info("All outta questions")
            # get more questions
            await self._questions.initialize()
            question: MCQuestion = next(self._questions, None)
        self._current_question = question
        q_view = McQuestionView(self)
        self._current_view = q_view
        q_str = f"**Question No {self._question_number}:**\n"
        self._question_number += 1
        q_str += f"{question.question}"
        for char, answer in zip("abcd", question.choices):
            q_str += f"\n\t{char}. {answer}"
        q_str += "\n\n"
        await self._trivia_bot.say(self._guild_id, q_str, view=q_view)
        await self._trivia_bot.say(self._guild_id, f"\n{ANSWER_TIME} seconds to answer.\n\n", "question_ready.wav")
        await self._set_status(GameStatus.WAIT_ANSWERS)

    async def _end_question(self):
        if self._skip_question():
            self._skipped_questions += 1
            await self._trivia_bot.say(self._guild_id, "**Question skipped!**\n\n")
            # Loop over players, update their scores, streak, and perfect status
        else:
            incorrect = []
            answer = f"{'abcd'[self._current_question.answer_index]}. {self._current_question.answer}"
            correct_msg = f"Correct Answer: {answer}\nCorrect Players:"
            scores_msg = "Hit Points Remaining:"
            for player in self._players.values():
                if player.answer != "skip!" and self._check_answer(player.answer):
                    player.streak += 1
                    correct_msg += f"\n\t- {player.name}"
                else:
                    player.perfect = False
                    player.streak = 0
                    player.score -= 1
                    incorrect.append(player)
                scores_msg += f"\n\t- {player.name}: {player.score}"
                self._logger.info(f"{player=}")
            question_sum_msg = correct_msg + "\n" + scores_msg + "\n\n"
            await self._trivia_bot.say(self._guild_id, question_sum_msg, None)
            await self._question_report(incorrect)
        self._current_view.stop()
        self._reset_answers()
        # Game flow should allow a brief pause here
        await asyncio.sleep(5)
        await self._set_status(GameStatus.ASKING)

    async def _question_report(self, incorrect_players: list[Player]):
        # Method to report the scores after the question, and announce streak callouts
        callouts = set()
        announcements = []
        for player in incorrect_players:
            # Streak == 0 --> player just answered incorrectly
            print(player)
            life_pct = 10 * player.score
            status_msg = f"{player.name} health: {life_pct / 100:.0%}\n\n"
            if life_pct in {70, 50, 30, 10}:
                status_wav = None
                version = random.randint(1, 3)
                status_wav = f"lives/{life_pct}pct_life_{version}.wav"
                # Let's not spam the voice channel, check if the announcement is already going to play
                if status_wav is not None and life_pct not in callouts:
                    callouts.add(life_pct)
                    announcements.append((status_msg, status_wav))
                else:
                    announcements.append((status_msg, None))
        await self._trivia_bot.speak(self._guild_id, announcements)

    # async def _set_status(self, status: GameStatus, **kwargs):
    #     pass


