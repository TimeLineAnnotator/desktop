"""Range and score timelines start at a default height, as the other kinds do,
so that undoing a change of height can give it back. Before they had one, TiLiA
saved them with height 1, which the validator refuses: such a height gets the
default too."""

from pathlib import Path

import pytest

from tests.utils import undoable
from tilia.file.file_manager import open_tla
from tilia.file.migration import normalize_kind_string
from tilia.requests import Post, post
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


@pytest.mark.parametrize("kind", [k for k, _ in KINDS], ids=IDS)
@pytest.mark.parametrize("stored", [1, 9, 10])
def test_loading_a_height_the_validator_refuses_gives_the_default(kind, stored, tls):
    timeline = tls.create_timeline(kind)
    data = {timeline.id: timeline.get_state() | {"height": stored}}
    tls.clear()

    tls.deserialize_timelines(data)

    expected = _default_height(kind) if stored < 10 else stored
    assert tls.get_timeline(timeline.id).get_data("height") == expected


# The core's copy of a file saved by TiLiA 0.5.15, whose score timeline has
# height 1. Read where it is, never copied or changed.
OLD_FILE = Path(__file__).parents[2] / "packages/tilia-core/tests/tla/old/0.5.15.tla"


@pytest.mark.skipif(
    not OLD_FILE.exists(), reason="the core's old files come with tilia-core"
)
def test_a_score_timeline_saved_by_0_5_15_gets_the_default_height(tls, tluis):
    stored = OLD_FILE.read_bytes()

    # TiLiA's reader and migration, as on opening the file. Only the score
    # timeline is loaded: the file's harmony has a display mode, "chord", that
    # TiLiA no longer shows.
    success, file, _ = open_tla(OLD_FILE)
    assert success
    score_id, data = next(
        (id, data)
        for id, data in file.timelines.items()
        if normalize_kind_string(data["kind"]) == ScoreTimeline.type_name()
    )
    assert data["height"] == 1
    tls.deserialize_timelines({score_id: data})
    post(Post.APP_STATE_RECORD, "file start")  # as opening a file does

    score = tls.get_timeline(score_id)
    assert score.get_data("height") == _default_height(ScoreTimeline)

    tlui = tluis.get_timeline_ui(score_id)
    with undoable():
        commands.execute("timeline.set_height", tlui, score.get_data("height") + 50)
    commands.execute("edit.undo")

    assert score.get_data("height") == _default_height(ScoreTimeline)
    assert OLD_FILE.read_bytes() == stored
