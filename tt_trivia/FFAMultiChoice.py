from QuestionSet import QuestionSet, MCQuestion, Qtype
import nextcord
from Player import Player
import asyncio
from FFAGame import GameStatus, FFAGame, SKIP_THRESHOLD, ANSWER_TIME, WAIT_PLAYERS


class FFAMultiChoice(FFAGame):
    _current_question: MCQuestion | None

    def __init__(self, q_set_kwargs: dict[str,str], g_id: int, bot, logger):
        super().__init__(g_id, bot, logger)
        self._questions = QuestionSet(Qtype.MULTI_CHOICE, **q_set_kwargs)

    def receive_answer(self, message: nextcord.Message):
        ans = message.content.lower().strip()
        self._logger.info(f"Receiving answer {ans}")
        if self._current_question is None:
            raise RuntimeError(f"record_answer called for game {self.get_guild_id()} when no question was set.")
        # Skip if message was from non-player
        if message.author.id not in self._players:
            return
        # One a player skips, no taking back
        if self._players[message.author.id].answer == "skip!":
            return
        if ans in {"a", "b", "c", "d", "skip!"} or ans in [a.strip().lower() for a in self._current_question.choices]:
            self._players[message.author.id].answer = ans

    def receive_button_answer(self, answer: str, interaction: nextcord.Interaction):
        u_id = interaction.user.id
        if u_id not in self._players:
            return
        # One a player skips, no taking back
        if self._players[u_id].answer == "skip!":
            return
        self._players[u_id].answer = answer
        self._logger.info(f"Set player {self._players[u_id].name}'s answer to {answer}")

    async def _ask_next_question(self):
        self._logger.info("Asking Question")
        question: MCQuestion = next(self._questions, None)
        # If none, then we're outta questions end the game
        if question is None:
            self._logger.info("All outta questions")
            await self._set_status(GameStatus.ENDING)
            return
        self._current_question = question
        q_view = McQuestionView(self)
        self._current_view = q_view
        q_str = f"**Question No {self._questions.get_index()}:**\n"
        q_str += f"{question.question}"
        for char, answer in zip("abcd", question.choices):
            q_str += f"\n\t{char}. {answer}"
        q_str += "\n\n"
        await self._trivia_bot.say(self._guild_id, q_str, view=q_view)
        await self._trivia_bot.say(self._guild_id, f"\n{ANSWER_TIME} seconds to answer.\n\n", "question_ready.wav")
        await self._set_status(GameStatus.WAIT_ANSWERS)

    def _clear_last_question(self):
        self._current_question = None
        for player in self._players.values():
            player.answer = ""

    async def _end_question(self):
        if self._skip_question():
            self._skipped_questions += 1
            await self._trivia_bot.say(self._guild_id, "**Question skipped!**\n\n")
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
                scores_msg += f"\n\t- {player.name}: {player.score}"
                self._logger.info(f"{player=}")
            question_sum_msg = correct_msg + "\n" + scores_msg + "\n\n"
            await self._trivia_bot.say(self._guild_id, question_sum_msg, None)
            await self._question_report(correct)
        self._current_view.stop()
        self._reset_answers()
        # Game flow should allow a brief pause here
        await asyncio.sleep(5)
        await self._set_status(GameStatus.ASKING)

    async def _question_report(self, correct_players: list[Player]):
        # Method to report the scores after the question, and announce streak callouts
        callouts = set()
        announcements = []
        for player in correct_players:
            streak = player.streak
            if streak > 2:
                steak_msg = f"{player.name} is on a {streak}-streak!\n\n"
                streak_wav = f"{streak}streak.wav"
                # Let's not spam the voice channel, check if the announcement is already going to play
                if streak_wav not in callouts:
                    callouts.add(streak_wav)
                    announcements.append((steak_msg, streak_wav))
                else:
                    announcements.append((steak_msg, None))
        await self._trivia_bot.speak(self._guild_id, announcements)

    def _check_answer(self, answer: str | None) -> bool:
        assert self._status == GameStatus.QUESTION_RESULTS
        if answer is None:
            return False
        # Players can answer with either a-d, or typing the full answer
        answer = answer.lower()
        if answer in {"a", "b", "c", "d"}:
            return self._current_question.answer_index == MCQuestion.get_index(answer)
        if self._current_question.answer is None:
            self._logger.info(f"WTF {self._current_question.answer=}")
        if self._current_question.answer.lower() == answer:
            return True
        return False

    def _skip_question(self) -> bool:
        assert self._status == GameStatus.QUESTION_RESULTS
        # Must consider players who failed to provide an answer, therefore check answer is not none
        votes = len([p for p in self._players.values() if p.answer is not None and p.answer.lower() == "skip!"])
        threshold = round(SKIP_THRESHOLD * len(self._players))
        return votes >= threshold

    def _reset_answers(self):
        for player in self._players.values():
            player.answer = None

    async def _end_game(self):
        self._logger.info("ending game")
        players: list[Player] = list(self._players.values())
        players.sort(reverse=True, key=lambda p: p.score)
        winner = players[0]
        game_report = "Final scores:\n"
        for i, player in enumerate(players):
            game_report += f"{i + 1}. {player}: {player.score}\n"
        # check for ties
        if len(players) > 1 and players[1].score == winner.score:
            winners: list[Player] = list(map(lambda p: p.score == winner.score, players))
            tie_result = f"@everyone There was a {len(winners)} way tie! Winners:\n"
            for winner in winners:
                tie_result += f"\n\t- {winner.name}"
                await self._trivia_bot.say(self._guild_id, tie_result)
        else:
            await self._trivia_bot.say(self._guild_id, f"<@{winner.id}> is the winner with {winner.score} points!",
                                       "victory.wav")
            # Quite an achievement
            self._logger.info("checking if player is perfect")
            if winner.is_perfect():
                await self._trivia_bot.say(self._guild_id, f"<@{winner.id}> was perfect for the game!", "flawless.wav")

    async def _set_status(self, status: GameStatus, **kwargs):
        # Transition function for various game states
        self._status = status
        self._logger.info(f"Status of game {self._guild_id} set to {self._status}")
        task = None
        if self._status == GameStatus.FAILED:
            if len(kwargs) == 1 and isinstance(kwargs["err"], Exception):
                await self._handle_failed_game(kwargs["err"])
                return
        try:
            if self._status == GameStatus.GETTING_PLAYERS:
                task = asyncio.create_task(self._wait_players("Multiple Choice FFA"))
            elif self._status == GameStatus.ASKING:
                task = asyncio.create_task(self._ask_next_question())
            elif self._status == GameStatus.WAIT_ANSWERS:
                task = asyncio.create_task(self._wait_answers())
            elif self._status == GameStatus.QUESTION_RESULTS:
                task = asyncio.create_task(self._end_question())
            elif self._status == GameStatus.ENDING:
                if self._player_count > 0:
                    await self._end_game()
                self._trivia_bot.cleanup_game(self)
                return
            # If in stopped state, need to flush the task queue, then cleanup game and return
            elif self._status == GameStatus.STOPPED:
                await self._stop_game()
                return
            # append the task to the stack and schedule it to run
            self._task_stack.append(task)
            await task
        except Exception as e:
            print(f"Caught exception {e}")
            self._logger.error(e)
            await self._set_status(GameStatus.FAILED, err=e)


class McQuestionView(nextcord.ui.View):
    """
    view class to render question button gui with callback to register answers from players.
    """
    _game: FFAMultiChoice

    def __init__(self, game: FFAMultiChoice):
        super(McQuestionView, self).__init__()
        self._game = game

    @nextcord.ui.button(label="a", style=nextcord.ButtonStyle.green)
    async def answer_a(self, btn: nextcord.ui.Button, interaction: nextcord.Interaction):
        self._game.receive_button_answer("a", interaction)

    @nextcord.ui.button(label="b", style=nextcord.ButtonStyle.red)
    async def answer_b(self, btn: nextcord.ui.Button, interaction: nextcord.Interaction):
        self._game.receive_button_answer("b", interaction)

    @nextcord.ui.button(label="c", style=nextcord.ButtonStyle.blurple)
    async def answer_c(self, btn: nextcord.ui.Button, interaction: nextcord.Interaction):
        self._game.receive_button_answer("c", interaction)

    @nextcord.ui.button(label="d", style=nextcord.ButtonStyle.grey)
    async def answer_d(self, btn: nextcord.ui.Button, interaction: nextcord.Interaction):
        self._game.receive_button_answer("d", interaction)
