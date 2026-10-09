import re

from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_positive_integer
from tilia.timelines.component_kinds import ComponentKind

# A numerator as written: "3", or "3+2" for a composite time signature.
NUMERATOR_PATTERN = re.compile(r"[0-9]+(\+[0-9]+)*")


def validate_numerator(value):
    return isinstance(value, str) and NUMERATOR_PATTERN.fullmatch(value) is not None


def validate_pairs(value):
    return value is None or (
        isinstance(value, list)
        and len(value) > 1
        and all(
            len(pair) == 2
            and validate_numerator(pair[0])
            and validate_positive_integer(pair[1])
            for pair in value
        )
    )


class TimeSignature(PointLikeTimelineComponent):
    SERIALIZABLE = ["staff_index", "time", "numerator", "denominator", "pairs"]
    ORDERING_ATTRS = ("time", "staff_index")

    KIND = ComponentKind.TIME_SIGNATURE

    def __init__(
        self,
        timeline,
        id,
        staff_index,
        time,
        numerator=None,
        denominator=None,
        pairs=None,
        **_,
    ):
        # A time signature as written. Its numerator is text, such as "3+2"
        # (files written before that have whole numbers). One with several
        # pairs, such as 2/4 + 3/8, has them in `pairs`, [["2", 4], ["3", 8]],
        # and no numerator or denominator.
        self.validators |= {
            "numerator": validate_numerator,
            "denominator": validate_positive_integer,
            "pairs": validate_pairs,
        }

        self.staff_index = staff_index
        self.time = time
        self.numerator = str(numerator) if numerator is not None else None
        self.denominator = denominator
        self.pairs = pairs

        super().__init__(timeline, id)

    def get_pairs(self) -> list[tuple[str, int]]:
        """Each numerator and denominator, as written."""
        if self.pairs:
            return [(numerator, denominator) for numerator, denominator in self.pairs]
        return [(self.numerator, self.denominator)]

    def __str__(self):
        written = " + ".join(f"{n}/{d}" for n, d in self.get_pairs())
        return f"TimeSignature({self.time}, {written})"
