from dataclasses import dataclass, field


@dataclass(order=True)
class MeasureLength:
    """A type for displaying measure lengths as 'measure number'.'beat number'.
    Something like this is necessary for calcuting the length in measure of
    timeline components."""

    sort_index: tuple[int, int] = field(init=False)
    measure_part: int
    beat_part: int

    def __post_init__(self):
        self.sort_index = (self.measure_part, self.beat_part)

    def __repr__(self):
        return f"{self.measure_part}.{self.beat_part}"

    @classmethod
    def from_str(cls, string):
        return MeasureLength(*map(lambda x: int(x), string.split(".")))
