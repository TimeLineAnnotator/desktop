import math

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.ui.format import format_media_time
from tilia_core import rules


def test_create(score_tl):
    assert score_tl


def test_create_note(note):
    assert note


def test_create_staff(staff):
    assert staff


class TestCreateClef:
    def test_create_clef(self, clef):
        assert clef

    @pytest.mark.parametrize("shorthand", Clef.Shorthand)
    def test_create_with_shorthand(self, shorthand, score_tl):
        score_tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=shorthand)
        assert len(score_tl) == 1


def test_create_bar_line(bar_line):
    assert bar_line


def test_create_time_signature(time_signature):
    assert time_signature


def test_time_signature_with_a_whole_number_numerator_has_it_as_text(score_tl):
    # Files written before numerators were text have whole numbers.
    time_signature, _ = score_tl.create_component(
        ComponentKind.TIME_SIGNATURE, 0, 0, numerator=4, denominator=4
    )
    assert time_signature.numerator == "4"
    assert time_signature.get_pairs() == [("4", 4)]


def test_create_key_signature(key_signature):
    assert key_signature


def test_crop_segmentlike_components(score_tl, tilia_state):
    tilia_state.duration = 100
    c1, _ = score_tl.create_component(
        ComponentKind.NOTE, 0, 100, 0, 0, 3, 0
    )  # end will be cropped
    c2, _ = score_tl.create_component(
        ComponentKind.NOTE, 0, 50, 0, 0, 3, 0
    )  # will not be altered
    c3, _ = score_tl.create_component(
        ComponentKind.NOTE, 50, 100, 0, 0, 3, 0
    )  # start will be cropped
    c4, _ = score_tl.create_component(
        ComponentKind.NOTE, 80, 100, 0, 0, 3, 0
    )  # will be deleted

    new_end = 75
    score_tl.crop(new_end)

    assert c1.start == 0
    assert c1.end == new_end

    assert c2.start == 0
    assert c2.end == 50

    assert c3.start == 50
    assert c3.end == new_end

    assert c4 not in score_tl


def test_scale_segmentlike_components(score_tl, tilia_state):
    tilia_state.duration = 100
    n, _ = score_tl.create_component(ComponentKind.NOTE, 10, 100, 0, 0, 3, 0)

    score_tl.scale(2)

    assert n.start == 20
    assert n.end == 200


def test_crop_pointlike_components(score_tl, tilia_state):
    tilia_state.duration = 100
    c1, _ = score_tl.create_component(
        ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE
    )
    c2, _ = score_tl.create_component(
        ComponentKind.CLEF, 0, 100, shorthand=Clef.Shorthand.TREBLE
    )

    b1, _ = score_tl.create_component(ComponentKind.BAR_LINE, 0)
    b2, _ = score_tl.create_component(ComponentKind.BAR_LINE, 100)

    ts1, _ = score_tl.create_component(ComponentKind.TIME_SIGNATURE, 0, 0, 4, 4)
    ts2, _ = score_tl.create_component(ComponentKind.TIME_SIGNATURE, 0, 100, 4, 4)

    ks1, _ = score_tl.create_component(ComponentKind.KEY_SIGNATURE, 0, 0, 0)
    ks2, _ = score_tl.create_component(ComponentKind.KEY_SIGNATURE, 0, 100, 0)

    score_tl.crop(50)

    for component in [c1, b1, ts1, ks1]:
        assert component.time == 0

    for component in [c2, b2, ts2, ks2]:
        assert component not in score_tl


def test_scale_pointlike_components(score_tl, tilia_state):
    tilia_state.duration = 100
    c, _ = score_tl.create_component(
        ComponentKind.CLEF, 0, 10, shorthand=Clef.Shorthand.TREBLE
    )
    b, _ = score_tl.create_component(ComponentKind.BAR_LINE, 20)
    ts, _ = score_tl.create_component(ComponentKind.TIME_SIGNATURE, 0, 30, 4, 4)
    ks, _ = score_tl.create_component(ComponentKind.KEY_SIGNATURE, 0, 40, 0)

    score_tl.scale(2)

    assert c.time == 20
    assert b.time == 40
    assert ts.time == 60
    assert ks.time == 80


def test_crop_staff(score_tl, tilia_state):
    tilia_state.duration = 100
    s, _ = score_tl.create_component(ComponentKind.STAFF, 0, 5)

    score_tl.crop(50)

    assert s in score_tl


# What each kind with a time is called in the texts for it
# (TimeLineAnnotator/project-management#669).
SCORE_POINTS = {
    ComponentKind.CLEF: "Clef",
    ComponentKind.BAR_LINE: "Bar line",
    ComponentKind.TIME_SIGNATURE: "Time signature",
    ComponentKind.KEY_SIGNATURE: "Key signature",
}


class TestTheTextsOfTheirTimes:
    """A score's components have the texts of the other kinds for their times, each
    naming its own kind (TimeLineAnnotator/project-management#669)."""

    @pytest.mark.parametrize("kind", SCORE_POINTS)
    def test_a_time_before_0(self, score_tl, tilia_state, kind):
        assert tilia_state.duration == 100
        assert score_tl.create_component(kind, time=-1.0) == (
            None,
            f"{SCORE_POINTS[kind]} time can't be negative."
            f" Got '{format_media_time(-1.0)}'",
        )

    @pytest.mark.parametrize("kind", SCORE_POINTS)
    @pytest.mark.parametrize(
        "time, shown",
        [(150.0, "02:30.0"), (5000.0, "1:23:20.0"), (math.inf, "inf")],
    )
    def test_a_time_past_the_end(self, score_tl, tilia_state, kind, time, shown):
        assert tilia_state.duration == 100
        assert score_tl.create_component(kind, time=time) == (
            None,
            f"{SCORE_POINTS[kind]} time '{shown}' is bigger than media time '01:40.0'",
        )

    @pytest.mark.parametrize("kind", SCORE_POINTS)
    def test_minus_infinity(self, score_tl, tilia_state, kind):
        assert score_tl.create_component(kind, time=-math.inf) == (
            None,
            f"{SCORE_POINTS[kind]} time can't be negative. Got '-inf'",
        )

    @pytest.mark.parametrize(
        "start, end, reason",
        [
            (150.0, 160.0, "Note start '02:30.0' is bigger than media time '01:40.0'"),
            (95.0, 150.0, "Note end '02:30.0' is bigger than media time '01:40.0'"),
            (95.0, math.inf, "Note end 'inf' is bigger than media time '01:40.0'"),
            (2.0, 1.0, "Note end '00:01.0' should be bigger than start '00:02.0'"),
            (2.0, 2.0, "Note end '00:02.0' should be bigger than start '00:02.0'"),
        ],
    )
    def test_a_note(self, score_tl, tilia_state, start, end, reason):
        assert tilia_state.duration == 100
        note = score_tl.create_component(ComponentKind.NOTE, start=start, end=end)
        assert note == (None, reason)

    def test_they_are_the_core_s_texts(self, score_tl, tilia_state):
        # The core has no rules for these kinds: its texts for another, by name.
        marker = rules.marker(100.0, [], {"time": 150.0}).reason
        for kind, name in SCORE_POINTS.items():
            _, reason = score_tl.create_component(kind, time=150.0)
            assert reason == marker.replace("Marker", name)
        for start, end in [(150.0, 160.0), (95.0, 150.0), (2.0, 1.0)]:
            segment = {"start": start, "end": end}
            hierarchy = rules.hierarchy(100.0, [], {"level": 1, **segment}).reason
            _, reason = score_tl.create_component(ComponentKind.NOTE, **segment)
            assert reason == hierarchy.replace("Hierarchy", "Note")
