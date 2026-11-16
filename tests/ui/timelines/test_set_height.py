"""`timeline.set_height` sets the height of the kinds whose context menu offers
it, and refuses range and score timelines, whose height comes from their rows
and staves."""

import pytest

from tests.mock import Serve
from tests.utils import undoable
from tilia.requests import Get
from tilia.ui import commands

REFUSED = [("range_tlui", "range", "rows"), ("score_tlui", "score", "staves")]


@pytest.mark.parametrize(
    "fixture, kind, source", REFUSED, ids=[kind for _, kind, _ in REFUSED]
)
def test_refuses_and_says_why(
    fixture, kind, source, tluis, tilia_state, tilia_errors, request
):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")
    stack = [id(entry["state"]) for entry in tilia_state.undo_manager.stack]

    commands.execute("timeline.set_height", tlui, height + 50)

    assert tlui.timeline.get_data("height") == height
    assert [id(entry["state"]) for entry in tilia_state.undo_manager.stack] == stack
    tilia_errors.assert_in_error_message(
        f"The height of a {kind} timeline comes from its {source}."
    )


@pytest.mark.parametrize(
    "fixture, kind, source", REFUSED, ids=[kind for _, kind, _ in REFUSED]
)
def test_refuses_without_asking_for_a_height(
    fixture, kind, source, tluis, tilia_errors, request
):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")

    with Serve(Get.FROM_USER_INT, (True, height + 50)) as asked:
        commands.execute("timeline.set_height", tlui)

    assert not asked.called
    assert tlui.timeline.get_data("height") == height
    tilia_errors.assert_error()


@pytest.mark.parametrize(
    "fixture", ["marker_tlui", "hierarchy_tlui", "pdf_tlui", "audiowave_tlui"]
)
def test_sets_the_height_of_other_kinds(fixture, tluis, tilia_errors, request):
    tlui = request.getfixturevalue(fixture)
    height = tlui.timeline.get_data("height")

    with undoable():
        commands.execute("timeline.set_height", tlui, height + 50)

    assert tlui.timeline.get_data("height") == height + 50
    # The AudioWave timeline says it has no media to show, which is no refusal.
    assert not [e for e in tilia_errors.errors if "comes from its" in e["message"]]
