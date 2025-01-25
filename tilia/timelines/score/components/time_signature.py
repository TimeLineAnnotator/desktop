from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_positive_integer
from tilia.timelines.component_kinds import ComponentKind


class TimeSignature(PointLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["staff_index", "time", "numerator", "denominator"]
    ORDERING_ATTRS = ("time", "staff_index")

    KIND = ComponentKind.TIME_SIGNATURE

    def __init__(self, timeline, id, staff_index, time, numerator, denominator, **_):
        self.validators |= {
            "numerator": validate_positive_integer,
            "denominator": validate_positive_integer,
        }

        self.staff_index = staff_index
        self.time = time
        self.numerator = numerator
        self.denominator = denominator

        super().__init__(timeline, id)

    def __str__(self):
        return f"TimeSignature({self.time}, {self.numerator}/{self.denominator})"
