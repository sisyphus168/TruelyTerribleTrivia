import dataclasses


@dataclasses.dataclass
class PLayer:
    name: str
    id: int
    score: int
    streak: int
    perfect: bool

    def __repr__(self):
        r = f"Player: {self.id}: {self.name}"
        r += f"\n\t- score: {self.score}"
        r += f"\n\t- streak: {self.streak}"
        r += f"\n\t- perfect: {self.perfect}"
        return r

    def __str__(self):
        return self.__repr__()