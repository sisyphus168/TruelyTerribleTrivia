import json
# import aiohttp
import requests
import base64
import asyncio
from dataclasses import dataclass
import enum
import random
import time

random.seed(time.time())
API_BASE_URL = "https://opentdb.com/api.php?"
DIFFICULTIES = {"easy", "medium", "hard", "any"}


class Qtype(enum.Enum):
    MULTI_CHOICE = 0
    TRUE_FALSE = 1
    FREE_RESPONSE = 2


class ApiError(RuntimeError):
    def __init__(self, message):
        super(message)


class QuestionSet:
    # def __init__(self, q_type: Qtype = Qtype.MULTI_CHOICE, category: str = "General Knowledge", difficulty: str = "any",
    #              num: int = 10):
    def __init__(self, q_type: Qtype = Qtype.MULTI_CHOICE, **kwargs):
        # keyword args set to default if need be
        category = kwargs["category"] if "category" in kwargs else "General Knowledge"
        difficulty = kwargs["difficulty"] if "difficulty" in kwargs else "any"
        num = kwargs["num"] if "num" in kwargs else 20
        with open("../resource/categories.json", "r") as f:
            self._categories = json.load(f)
        assert 0 < num < 51
        assert category in self._categories.keys()
        assert difficulty in DIFFICULTIES
        assert isinstance(q_type, Qtype)
        self._index = 0
        self._questions = []
        self._q_type = q_type
        self._category = category
        self._difficulty = difficulty.lower()
        self._num = num
        self._initialized = False

    def get_q_type(self):
        return self._q_type

    def get_category(self):
        return self._category

    def get_num_questions(self):
        return self._num

    def get_difficulty(self):
        return self._difficulty

    def get_index(self):
        return self._index

    def get_question_no(self):
        return self._index + 1

    async def initialize(self):
        self._index = 0
        request_url = API_BASE_URL + f"amount={self._num}"
        request_url += "&encode=base64"
        if self._category != "":
            cat_id = self._categories[self._category]
            request_url += f"&category={cat_id}"
        if self._difficulty != "any":
            request_url += f"&difficulty={self._difficulty}"
        if self._q_type == Qtype.MULTI_CHOICE or self._q_type == Qtype.FREE_RESPONSE:
            request_url += "&type=multiple"
        elif self._q_type == Qtype.TRUE_FALSE:
            request_url += "&type=boolean"
        print(f"Request URL: {request_url}")
        await self._fetch_questions(request_url)
        self._initialized = True

    async def _fetch_questions(self, url):
        # TODO: replace requests with aiohttp asyc http request
        with requests.request("GET", url) as response:
            print("status:", response.status_code)
            print("content type:", response.encoding)
            if response.status_code != 200:
                raise RuntimeError(f"The response code was {response.status_code}")
            q_data = response.json()
            if q_data["response_code"] == 2:
                raise ApiError(f"Bad opentdb api url: {url}")
            elif q_data["response_code"] != 0:
                print("API Request failed")
                raise RuntimeError(f"Get request for questions failed. {q_data['response code']=}")
            question_lst = q_data["results"]
            self._questions = [self._construct_question(q_dict) for q_dict in question_lst]

    def _construct_question(self, question_dict):
        # Question, answers, etc are base64 encoded, so decode them
        def decode(s): return str(base64.urlsafe_b64decode(s), "utf-8")
        diff = decode(question_dict["difficulty"])
        question = decode(question_dict["question"])
        cat = decode(question_dict["category"])
        answer = decode(question_dict["correct_answer"])
        if self._q_type == Qtype.TRUE_FALSE:
            return TFQuestion(cat=cat, diff=diff, question=question, answer=bool(answer))
        elif self._q_type == Qtype.MULTI_CHOICE:
            choices = [decode(ans) for ans in question_dict["incorrect_answers"]]
            choices.append(answer)  # answer already decoded
            random.shuffle(choices)
            ans_idx = choices.index(answer)
            return MCQuestion(cat=cat, diff=diff, question=question, answer=answer,
                              choices=choices, answer_index=ans_idx)
        elif self._q_type == Qtype.FREE_RESPONSE:
            return FreeQuestion(cat=cat, diff=diff, question=question, answer=answer)
        else:
            raise ValueError(f"Unknown question type {self._q_type}")

    def is_initialized(self):
        return self._initialized

    def __repr__(self):
        rep = f"Category:\t{self._category}"
        rep += f"\nQuestion type:\t{self._q_type}"
        rep += f"\nDifficulty:\t{self._difficulty}"
        rep += f"\nNo. Questions:\t{self._num}"
        rep += f"\nInitialized:\t{self._initialized}"
        rep += f"Questions:\n\n"
        for question in self._questions:
            rep += f"\t- {question}\n"
        return rep

    def __str__(self):
        return self.__repr__()

    def __iter__(self):
        if not self._initialized:
            raise RuntimeError(f"Call to __iter__ on QuestionSet {self} before it was initialized")
        self._index = 0
        return self

    def __next__(self):
        if not self._initialized:
            raise RuntimeError(f"Call to __next__ on QuestionSet {self} before it was initialized.")
        if self._index < self._num:
            next_q = self._questions[self._index]
            self._index += 1
            return next_q
        else:
            raise StopIteration


@dataclass
class MCQuestion:
    cat: str
    diff: str
    question: str
    answer: str
    choices: list[str]
    answer_index: int

    @staticmethod
    def get_q_type():
        return Qtype.MULTI_CHOICE

    @staticmethod
    def get_index(char):
        return "abcd".index(char)


@dataclass
class TFQuestion:
    cat: str
    diff: str
    question: str
    answer: bool

    @staticmethod
    def get_q_type():
        return Qtype.TRUE_FALSE

    @staticmethod
    def get_index(char):
        return "abcd".index(char)


# For use in eventual free response mode
@dataclass
class FreeQuestion:
    cat: str
    diff: str
    question: str
    answer: str

    @staticmethod
    def get_q_type():
        return Qtype.FREE_RESPONSE

    @staticmethod
    def get_index(char):
        return "abcd".index(char)


async def main():
    questions = QuestionSet()
    # async with aiohttp.ClientSession() as session:
    await questions.initialize()
    print("question set:", questions, sep="\n\n")
    print("\nIterating over the question set:")
    for question in questions:
        print("\t", question)


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.stop()
    finally:
        loop.close()