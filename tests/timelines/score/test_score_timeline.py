import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef


def test_create(score_tl):
    assert score_tl


def test_create_note(note):
    assert note


def test_create_staff(staff):
    assert staff


class TestCreateClef:
    def test_create_clef(self, clef):
        assert clef

    @pytest.mark.parametrize('shorthand', Clef.Shorthand)
    def test_create_with_shorthand(self, shorthand, score_tl):
        score_tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=shorthand)
        assert len(score_tl) == 1


def test_create_bar_line(bar_line):
    assert bar_line


def test_create_time_signature(time_signature):
    assert time_signature


def test_create_key_signature(key_signature):
    assert key_signature


def test_crop_segmentlike_components(score_tl, tilia_state):
    tilia_state.duration = 100
    c1, _ = score_tl.create_component(ComponentKind.NOTE, 0, 100, 0, 0, 3, 0)  # end will be cropped
    c2, _ = score_tl.create_component(ComponentKind.NOTE, 0, 50, 0, 0, 3, 0)  # will not be altered
    c3, _ = score_tl.create_component(ComponentKind.NOTE, 50, 100, 0, 0, 3, 0)  # start will be cropped
    c4, _ = score_tl.create_component(ComponentKind.NOTE, 80, 100, 0, 0, 3, 0)  # will be deleted

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
    c1, _ = score_tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE)
    c2, _ = score_tl.create_component(ComponentKind.CLEF, 0, 100, shorthand=Clef.Shorthand.TREBLE)

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
    c, _ = score_tl.create_component(ComponentKind.CLEF, 0, 10, shorthand=Clef.Shorthand.TREBLE)
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



