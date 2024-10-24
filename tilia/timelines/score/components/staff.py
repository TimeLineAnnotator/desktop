from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.validators import validate_positive_integer
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline


class Staff(TimelineComponent):
    SERIALIZABLE_BY_VALUE = ['line_count', 'position']
    ORDERING_ATTRS = ('position',)

    KIND = ComponentKind.STAFF

    validators = {
        'timeline': lambda _: False,  # read-only
        'id': lambda _: False,  # read-only
        "line_count": validate_positive_integer,
        "position": validate_positive_integer,

    }

    def __init__(self, timeline: ScoreTimeline, id: int, position: int, line_count: int):
        super().__init__(timeline, id)

        self.position = position
        self.line_count = line_count

    def __str__(self):
        return f"Staff({self.line_count, self.position})"
