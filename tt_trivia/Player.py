import dataclasses


@dataclasses.dataclass
class PLayer:
    name: str
    id: int
    score: int = 0
    streak: int = 0
    perfect: bool = True
    answer: str | None = None

    def __repr__(self):
        r = f"Player: {self.id}: {self.name}"
        r += f"\n\t- score: {self.score}"
        r += f"\n\t- streak: {self.streak}"
        r += f"\n\t- perfect: {self.perfect}"
        return r

    def __str__(self):
        return self.__repr__()

    @property
    def get_name(self):
        return self.name

    @property
    def get_score(self):
        return self.score

    def get_streak(self):
        return self.streak

    def is_perfect(self):
        return self.perfect

    def get_answer(self):
        return self.answer
