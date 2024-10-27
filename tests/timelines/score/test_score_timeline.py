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
        score_tl.create_component(ComponentKind.CLEF, 0, shorthand=shorthand)
        assert len(score_tl) == 1


def test_create_bar_line(bar_line):
    assert bar_line


def test_create_time_signature(time_signature):
    assert time_signature