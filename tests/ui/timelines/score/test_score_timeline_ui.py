import pytest

from tests.constants import EXAMPLE_MULTISTAFF_MUSICXML_PATH
from tests.mock import Serve
from tests.utils import reloadable
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction


def test_create(tluis, user_actions):
    with Serve(Get.FROM_USER_STRING, (True, "")):
        user_actions.trigger(TiliaAction.TIMELINES_ADD_SCORE_TIMELINE)

    assert len(tluis) == 1


def test_create_note(score_tlui, note):
    assert score_tlui[0]


def test_create_staff(score_tlui, staff):
    assert score_tlui[0]


@pytest.mark.parametrize("shorthand", Clef.Shorthand)
def test_create_clef(score_tlui, shorthand):
    score_tlui.create_component(ComponentKind.CLEF, 0, 0, shorthand=shorthand)
    assert score_tlui[0]


def test_create_barline(score_tlui, bar_line):
    assert score_tlui[0]


def test_create_time_signature(score_tlui, time_signature):
    assert score_tlui[0]


@pytest.mark.parametrize("fifths", range(-7, 8))
def test_create_key_signature(score_tlui, fifths):
    score_tlui.create_component(
        ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE
    )
    score_tlui.create_component(ComponentKind.KEY_SIGNATURE, 0, 0, fifths)
    assert score_tlui[0]


def _check_attrs(tmp_path, user_actions):
    @reloadable(tmp_path / "file.tla", user_actions)
    def check_attrs() -> None:
        score = get(
            Get.TIMELINE_UI_BY_ATTR, "TIMELINE_KIND", TimelineKind.SCORE_TIMELINE
        )
        for cmp_kind in (
            ComponentKind.CLEF,
            ComponentKind.KEY_SIGNATURE,
            ComponentKind.TIME_SIGNATURE,
        ):
            components = score.timeline.get_components_by_attr("KIND", cmp_kind)
            staff_no_to_y = {
                cmp.staff_index: score.get_element(cmp.id).body.y()
                for cmp in components
            }
            sorted_y = [
                k for k, _ in sorted(staff_no_to_y.items(), key=lambda item: item[1])
            ]
            assert len(sorted_y) == 3
            for i in range(len(sorted_y)):
                assert i == sorted_y[i]

    return check_attrs


def test_attribute_positions(qtui, score_tl, beat_tl, tmp_path, user_actions):
    beat_tl.beat_pattern = [1]
    for i in range(0, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [0, 1, 2]
    beat_tl.recalculate_measures()

    notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    _check_attrs(tmp_path, user_actions)


def test_attribute_positions_without_measure_zero(
    qtui, score_tl, beat_tl, tmp_path, user_actions
):
    beat_tl.beat_pattern = [1]
    for i in range(1, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2]
    beat_tl.recalculate_measures()

    with Serve(Get.FROM_USER_YES_OR_NO, False):
        notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    _check_attrs(tmp_path, user_actions)
