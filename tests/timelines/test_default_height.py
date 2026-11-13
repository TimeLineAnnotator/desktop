"""Range and score timelines start at a default height, as the other kinds do,
so that undoing a change of height can give it back."""

import pytest

from tests.utils import undoable
from tilia.settings import settings
from tilia.timelines.range.timeline import RangeTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands


def _default_height(kind):
    if kind is RangeTimeline:
        return settings.get("range_timeline", "default_row_height") + settings.get(
            "range_timeline", "bottom_margin"
        )
    return settings.get("score_timeline", "default_height")


KINDS = [(RangeTimeline, "range_tlui"), (ScoreTimeline, "score_tlui")]
IDS = ["range", "score"]


@pytest.mark.parametrize("kind", [k for k, _ in KINDS], ids=IDS)
def test_a_new_timeline_starts_at_the_default_height(kind, tls):
    timeline = tls.create_timeline(kind)

    assert timeline.get_data("height") == _default_height(kind)
    assert timeline.get_data("height") >= 10  # the least the validator allows


@pytest.mark.parametrize("kind", [k for k, _ in KINDS], ids=IDS)
def test_a_height_given_is_kept(kind, tls):
    timeline = tls.create_timeline(kind, height=77)

    assert timeline.get_data("height") == 77


@pytest.mark.parametrize("fixture", [f for _, f in KINDS], ids=IDS)
def test_undo_a_change_of_height(fixture, tluis, request):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")

    with undoable():
        commands.execute("timeline.set_height", tlui, height + 50)
    commands.execute("edit.undo")

    assert tlui.timeline.get_data("height") == height


@pytest.mark.parametrize("kind", [k for k, _ in KINDS], ids=IDS)
def test_loading_keeps_a_stored_height(kind, tls):
    # Timelines.deserialize_timelines is what App.on_file_load calls.
    timeline = tls.create_timeline(kind, height=77)
    data = {timeline.id: timeline.get_state()}
    tls.clear()

    tls.deserialize_timelines(data)

    assert tls.get_timeline(timeline.id).get_data("height") == 77
