import json
import aiohttp
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
    def __init__(self, q_type: Qtype = Qtype.MULTI_CHOICE, category: str = "General Knowledge",
                         difficulty: str = "any", num: int = 10):
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

    async def initialize(self, session):
        self._index = 0
        request_url = API_BASE_URL + f"amount={self._num}"
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
        await self._fetch_questions(request_url, session)

    async def _fetch_questions(self, url, session):
        # TODO: Despite await it seems like response's content is never ready. Connection closing early?
        async with session.get(url) as response:
            print("version:", response.version)
            print("status:", response.status)
            print("content type:", response.content_type)
            if response.status != 200:
                raise RuntimeError(f"Fuggg, the response code was {response.status}")
            print(response.content)
            q_data = await response.json()
            await asyncio.sleep(0.01)
            # q_data = json.loads(payload_json)
            if q_data["response code"] == 2:
                raise ApiError(f"Bad questions get request url: {url}")
            elif q_data["response code"] != 0:
                print("API Request failed")
                raise RuntimeError(f"Get request for questions failed. {q_data['response code']=}")
            question_lst = q_data["results"]
            self._questions = [self._construct_question(q_dict) for q_dict in question_lst]

    def _construct_question(self, question_dict):
        diff = question_dict["difficulty"]
        question = question_dict["question"]
        cat = question_dict["category"]
        answer = question_dict["correct_answer"]
        if self._q_type == Qtype.TRUE_FALSE:
            return TFQuestion(cat=cat, diff=diff, question=question, answer=answer)
        elif self._q_type == Qtype.MULTI_CHOICE:
            choices = [ans for ans in question_dict["incorrect_answers"]]
            choices = [answer].extend(choices)
            random.shuffle(choices)
            return MCQuestion(cat=cat, diff=diff, question=question, answer=answer, choices=choices)
        else:
            return FreeQuestion(cat=cat, diff=diff, question=question, answer=answer)

@dataclass
class MCQuestion:
    q_type: Qtype.MULTI_CHOICE
    cat: str
    diff: str
    question: str
    answer: str
    choices: list[str]


@dataclass
class TFQuestion:
    q_type: Qtype.TRUE_FALSE
    cat: str
    diff: str
    question: str
    answer: bool


# For use in eventual free response mode
@dataclass
class FreeQuestion:
    q_type: Qtype.FREE_RESPONSE
    cat: str
    diff: str
    question: str
    answer: str


async def main():
    questions = QuestionSet()
    async with aiohttp.ClientSession() as session:
        await questions.initialize(session)



if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.close()
    finally:
        loop.close()