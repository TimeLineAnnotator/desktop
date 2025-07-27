import pytest
import json

from tests.constants import EXAMPLE_MULTISTAFF_MUSICXML_PATH
from tests.mock import Serve, patch_file_dialog, patch_yes_or_no_dialog
from tests.utils import reloadable, get_blank_file_data
from tilia.errors import SCORE_STAFF_ID_ERROR
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.timeline_kinds import TimelineKind


def test_create(tluis, user_actions):
    with Serve(Get.FROM_USER_STRING, (True, "")):
        user_actions.execute("timelines.add.score")

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


def _check_attrs(tmp_path, user_actions, items_per_attr):
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
            assert len(sorted_y) == items_per_attr
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

    _check_attrs(tmp_path, user_actions, items_per_attr=3)


def test_attribute_positions_without_measure_zero(
    qtui, score_tl, beat_tl, tmp_path, user_actions
):
    beat_tl.beat_pattern = [1]
    for i in range(1, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2]
    beat_tl.recalculate_measures()

    with patch_yes_or_no_dialog(False):
        notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    _check_attrs(tmp_path, user_actions, items_per_attr=3)


def test_correct_clef_to_staff(qtui, score_tl, beat_tl):
    beat_tl.beat_pattern = [1]
    for i in range(1, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2]
    beat_tl.recalculate_measures()

    with patch_yes_or_no_dialog(False):
        notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    clefs = score_tl.get_components_by_attr("KIND", ComponentKind.CLEF)
    staff_no_to_clef = {clef.staff_index: clef.icon for clef in clefs}
    assert "alto" in staff_no_to_clef[0]
    assert "treble" in staff_no_to_clef[1]
    assert "bass" in staff_no_to_clef[2]


def test_missing_staff_deletes_timeline(
    qtui, tls, tilia_errors, tmp_path, user_actions
):
    file_data = get_blank_file_data()
    file_data["timelines"] = {
        0: {
            "kind": "SCORE_TIMELINE",
            "height": 1,
            "is_visible": True,
            "name": "",
            "ordinal": 1,
            "svg_data": "",
            "viewer_beat_x": {},
            "hash": "",
            "components": {
                2: {
                    "staff_index": 0,
                    "time": 0,
                    "line_number": -1,
                    "step": 4,
                    "octave": 4,
                    "icon": "clef-treble.svg",
                    "kind": "CLEF",
                    "hash": "",
                },
                3: {
                    "start": 0,
                    "end": 1,
                    "step": 0,
                    "accidental": 0,
                    "octave": 3,
                    "staff_index": 0,
                    "color": None,
                    "comments": "",
                    "" "display_accidental": False,
                    "kind": "NOTE",
                    "hash": "",
                },
            },
            "components_hash": "",
        }
    }
    file_data["media_metadata"]["media length"] = 1

    tmp_file = tmp_path / "test.tla"
    tmp_file.write_text(json.dumps(file_data), encoding="utf-8")

    with patch_file_dialog(True, [tmp_file]):
        user_actions.execute("file_open")

    tilia_errors.assert_in_error_title(SCORE_STAFF_ID_ERROR.title)
    assert tls.get_timeline_by_attr("KIND", TimelineKind.SCORE_TIMELINE) is None


def test_duplicate_staff_deletes_timeline(
    qtui, tls, tilia_errors, tmp_path, user_actions
):
    file_data = get_blank_file_data()
    file_data["timelines"] = {
        0: {
            "kind": "SCORE_TIMELINE",
            "height": 1,
            "is_visible": True,
            "name": "",
            "ordinal": 1,
            "svg_data": "",
            "viewer_beat_x": {},
            "hash": "",
            "components": {
                1: {"line_count": 5, "index": 0, "kind": "STAFF", "hash": ""},
                2: {"line_count": 5, "index": 0, "kind": "STAFF", "hash": ""},
            },
            "components_hash": "",
        }
    }

    tmp_file = tmp_path / "test.tla"
    tmp_file.write_text(json.dumps(file_data), encoding="utf-8")

    with patch_file_dialog(True, [tmp_file]):
        user_actions.execute("file_open")

    tilia_errors.assert_in_error_title(SCORE_STAFF_ID_ERROR.title)
    assert tls.get_timeline_by_attr("KIND", TimelineKind.SCORE_TIMELINE) is None


def test_symbol_staff_collision(qtui, tmp_path, user_actions):
    file_data_with_symbols = get_blank_file_data()
    file_data_with_symbols["timelines"] = {
        0: {
            "kind": "SCORE_TIMELINE",
            "height": 1,
            "is_visible": True,
            "name": "",
            "ordinal": 1,
            "svg_data": "",
            "viewer_beat_x": {},
            "hash": "",
            "components": {
                1: {"line_count": 5, "index": 0, "kind": "STAFF", "hash": ""},
                2: {
                    "staff_index": 0,
                    "time": 0,
                    "line_number": -1,
                    "step": 4,
                    "octave": 4,
                    "icon": "clef-treble.svg",
                    "kind": "CLEF",
                    "hash": "",
                },
            },
            "components_hash": "",
        }
    }

    tmp_file_with_symbols = tmp_path / "test_with_sym.tla"
    tmp_file_with_symbols.write_text(
        json.dumps(file_data_with_symbols), encoding="utf-8"
    )

    with (patch_file_dialog(True, [tmp_file_with_symbols])):
        user_actions.execute("file_open")

    score = get(Get.TIMELINE_UI_BY_ATTR, "TIMELINE_KIND", TimelineKind.SCORE_TIMELINE)
    clef = score.timeline.get_component_by_attr("KIND", ComponentKind.CLEF)
    staff = score.timeline.get_component_by_attr("KIND", ComponentKind.STAFF)

    staff_top_y_with_symbols = (
        score.get_element(staff.id).staff_lines.lines[0].line().y1()
    )

    assert score.get_element(clef.id).body.y() != staff_top_y_with_symbols

    file_data_sans_symbols = get_blank_file_data()
    file_data_sans_symbols["timelines"] = {
        0: {
            "kind": "SCORE_TIMELINE",
            "height": 1,
            "is_visible": True,
            "name": "",
            "ordinal": 1,
            "svg_data": "",
            "viewer_beat_x": {},
            "hash": "",
            "components": {
                1: {"line_count": 5, "index": 0, "kind": "STAFF", "hash": ""},
            },
            "components_hash": "",
        }
    }

    tmp_file_sans_symbols = tmp_path / "test_sans_sym.tla"
    tmp_file_sans_symbols.write_text(
        json.dumps(file_data_sans_symbols), encoding="utf-8"
    )

    with (
        patch_file_dialog(True, [tmp_file_sans_symbols]),
        patch_yes_or_no_dialog(False),  # do not save changes
    ):
        user_actions.execute("file_open")

    score = get(Get.TIMELINE_UI_BY_ATTR, "TIMELINE_KIND", TimelineKind.SCORE_TIMELINE)
    staff = score.timeline.get_component_by_attr("KIND", ComponentKind.STAFF)

    staff_top_y_sans_symbols = (
        score.get_element(staff.id).staff_lines.lines[0].line().y1()
    )

    assert staff_top_y_sans_symbols < staff_top_y_with_symbols
