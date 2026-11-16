"""`timeline.set_height` sets the height of the kinds whose context menu offers
it, hierarchy and AudioWave timelines, and refuses the others, saying where
their height comes from."""

import pytest

from tests.mock import Serve
from tests.utils import undoable
from tilia.requests import Get
from tilia.timelines.base.timeline import Timeline
from tilia.ui import commands
from tilia.ui.timelines.collection.collection import HEIGHT_COMES_FROM, HEIGHT_IS_SET

REFUSED = {
    "beat_tlui": "The height of a beat timeline is fixed.",
    "harmony_tlui": (
        "The height of a harmony timeline is its level height times the levels "
        "shown."
    ),
    "marker_tlui": (
        "The height of a marker timeline comes from the default height in the "
        "settings."
    ),
    "pdf_tlui": (
        "The height of a PDF timeline comes from the default height in the settings."
    ),
    "range_tlui": "The height of a range timeline comes from its rows.",
    "score_tlui": "The height of a score timeline comes from its staves.",
    "slider_tlui": (
        "The height of a slider timeline comes from the default height in the "
        "settings."
    ),
}


def test_every_kind_is_either_set_or_says_where_its_height_comes_from():
    kinds = set(Timeline.subclasses())

    assert set(HEIGHT_IS_SET) | set(HEIGHT_COMES_FROM) == kinds
    assert not set(HEIGHT_IS_SET) & set(HEIGHT_COMES_FROM)


@pytest.mark.parametrize("fixture", REFUSED)
def test_refuses_and_says_why(fixture, tluis, tilia_state, tilia_errors, request):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")
    stack = [id(entry["state"]) for entry in tilia_state.undo_manager.stack]
    tilia_errors.errors = []

    commands.execute("timeline.set_height", tlui, height + 50)

    assert tlui.timeline.get_data("height") == height
    assert [id(entry["state"]) for entry in tilia_state.undo_manager.stack] == stack
    assert [e["message"] for e in tilia_errors.errors] == [REFUSED[fixture]]


@pytest.mark.parametrize("fixture", REFUSED)
def test_refuses_without_asking_for_a_height(fixture, tluis, tilia_errors, request):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")

    with Serve(Get.FROM_USER_INT, (True, height + 50)) as asked:
        commands.execute("timeline.set_height", tlui)

    assert not asked.called
    assert tlui.timeline.get_data("height") == height


@pytest.mark.parametrize("fixture", ["hierarchy_tlui", "audiowave_tlui"])
def test_sets_the_height_of_hierarchy_and_audiowave(
    fixture, tluis, tilia_errors, request
):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")

    with undoable():
        commands.execute("timeline.set_height", tlui, height + 50)

    assert tlui.timeline.get_data("height") == height + 50
    # The AudioWave timeline says it has no media to show, which is no refusal.
    assert not [e for e in tilia_errors.errors if "The height of" in e["message"]]
