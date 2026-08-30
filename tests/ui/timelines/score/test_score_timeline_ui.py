import json

import pytest
from PySide6.QtGui import QColor

from tests.constants import EXAMPLE_MULTISTAFF_MUSICXML_PATH
from tests.mock import (
    Serve,
    patch_file_dialog,
    patch_yes_no_or_cancel_mb,
    patch_yes_or_no_dialog,
)
from tests.utils import get_blank_file_data, reloadable
from tilia.errors import SCORE_STAFF_ID_ERROR, SCORE_SVG_CREATE_ERROR
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.requests import Get, Post, get, post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands


def test_create(tluis):
    with Serve(Get.FROM_USER_STRING, (True, "")):
        commands.execute("timelines.add.score")

    assert len(tluis) == 1


def test_create_note(score_tlui, note):
    assert score_tlui[0]


def test_set_note_color(score_tlui, note_ui):
    # Note bodies are created lazily on this post; without it,
    # set_color has no body to update and the test would crash.
    post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, score_tlui.id)
    score_tlui.select_element(note_ui)

    with Serve(Get.FROM_USER_COLOR, (True, QColor("#123456"))):
        commands.execute("timeline.component.set_color")

    assert note_ui.get_data("color") == "#123456"


def test_reset_note_color(score_tlui, note_ui):
    post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, score_tlui.id)
    score_tlui.select_element(note_ui)

    with Serve(Get.FROM_USER_COLOR, (True, QColor("#123456"))):
        commands.execute("timeline.component.set_color")

    commands.execute("timeline.component.reset_color")

    assert note_ui.get_data("color") is None


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


def _check_attrs(tmp_path, items_per_attr):
    @reloadable(tmp_path / "file.tla")
    def check_attrs() -> None:
        score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
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


def test_attribute_positions(qtui, score_tl, beat_tl, tmp_path):
    beat_tl.beat_pattern = [1]
    for i in range(0, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [0, 1, 2]
    beat_tl.recalculate_measures()

    notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    _check_attrs(tmp_path, items_per_attr=3)


def test_attribute_positions_without_measure_zero(qtui, score_tl, beat_tl, tmp_path):
    beat_tl.beat_pattern = [1]
    for i in range(1, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2]
    beat_tl.recalculate_measures()

    with patch_yes_or_no_dialog(False):
        notes_from_musicXML(score_tl, beat_tl, EXAMPLE_MULTISTAFF_MUSICXML_PATH)

    _check_attrs(tmp_path, items_per_attr=3)


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


def test_missing_staff_deletes_timeline(qtui, tls, tilia_errors, tmp_path):
    file_data = get_blank_file_data()
    file_data["timelines"] = {
        0: {
            "kind": "Score",
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
                    "icon": "clef-treble",
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
                    "display_accidental": False,
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
        commands.execute("file.open")

    tilia_errors.assert_in_error_title(SCORE_STAFF_ID_ERROR.title)
    assert tls.get_timeline_by_type(ScoreTimeline) is None


def test_duplicate_staff_deletes_timeline(qtui, tls, tilia_errors, tmp_path):
    file_data = get_blank_file_data()
    file_data["timelines"] = {
        0: {
            "kind": "Score",
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
        commands.execute("file.open")

    tilia_errors.assert_in_error_title(SCORE_STAFF_ID_ERROR.title)
    assert tls.get_timeline_by_type(ScoreTimeline) is None


def test_symbol_staff_collision(qtui, tmp_path):
    file_data_with_symbols = get_blank_file_data()
    file_data_with_symbols["timelines"] = {
        0: {
            "kind": "Score",
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
                    "icon": "clef-treble",
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

    with patch_file_dialog(True, [tmp_file_with_symbols]):
        commands.execute("file.open")

    score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
    clef = score.timeline.get_component_by_attr("KIND", ComponentKind.CLEF)
    staff = score.timeline.get_component_by_attr("KIND", ComponentKind.STAFF)

    staff_top_y_with_symbols = (
        score.get_element(staff.id).staff_lines.lines[0].line().y1()
    )

    assert score.get_element(clef.id).body.y() != staff_top_y_with_symbols

    file_data_sans_symbols = get_blank_file_data()
    file_data_sans_symbols["timelines"] = {
        0: {
            "kind": "Score",
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
        patch_yes_no_or_cancel_mb(False),  # do not save changes
    ):
        commands.execute("file.open")

    score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
    staff = score.timeline.get_component_by_attr("KIND", ComponentKind.STAFF)

    staff_top_y_sans_symbols = (
        score.get_element(staff.id).staff_lines.lines[0].line().y1()
    )

    assert staff_top_y_sans_symbols < staff_top_y_with_symbols


MARKER_FONT_SIZE = "0.000009999999999999999px"


def _svg_with_beat_markers(*markers: tuple[int, int, int, int]) -> str:
    """Build an SVG carrying the near-invisible `measure␟division␟divisions`
    text markers the score viewer reads beat positions from. Each marker is
    (measure, division, divisions per measure, x).
    """
    elements = "".join(
        f'<g class="vf-text">'
        f'<text font-size="{MARKER_FONT_SIZE}" x="{x}" y="0">{m}␟{d}␟{divs}</text>'
        f"</g>"
        for m, d, divs, x in markers
    )
    return f'<svg width="1000" height="200">{elements}</svg>'


SVG_WITHOUT_MARKERS = '<svg width="1000" height="200"/>'
SVG_FIRST_SCORE = _svg_with_beat_markers((1, 0, 32, 100), (1, 16, 32, 150))
SVG_SECOND_SCORE = _svg_with_beat_markers((1, 0, 32, 900), (1, 16, 32, 950))
BEAT_X_FIRST_SCORE = {1.0: 100.0, 1.5: 150.0}
BEAT_X_SECOND_SCORE = {1.0: 900.0, 1.5: 950.0}


class TestViewerBeatPositions:
    @staticmethod
    def _import_score(tls, score_tlui, svg: str) -> None:
        """Stand in for the musicXML import, which reaches the timeline as a
        single `svg_data` write once the web engine has produced the SVG.
        """
        tls.set_timeline_data(score_tlui.id, "svg_data", svg)

    @staticmethod
    def _clear(score_tlui) -> None:
        with Serve(Get.FROM_USER_YES_OR_NO, True):
            commands.execute("timeline.clear", score_tlui)

    def test_beat_positions_come_from_the_imported_score(self, score_tlui, tls):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)

        assert score_tlui.get_data("viewer_beat_x") == BEAT_X_FIRST_SCORE
        assert score_tlui.svg_view.beat_x_position == BEAT_X_FIRST_SCORE

    def test_clear_drops_beat_positions(self, score_tlui, note, tls):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)

        self._clear(score_tlui)

        assert score_tlui.get_data("viewer_beat_x") == {}

    def test_score_imported_after_clear_uses_its_own_beat_positions(
        self, score_tlui, note, tls
    ):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)
        self._clear(score_tlui)

        self._import_score(tls, score_tlui, SVG_SECOND_SCORE)

        assert score_tlui.get_data("viewer_beat_x") == BEAT_X_SECOND_SCORE
        assert score_tlui.svg_view.beat_x_position == BEAT_X_SECOND_SCORE

    def test_score_imported_over_another_uses_its_own_beat_positions(
        self, score_tlui, tls
    ):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)

        self._import_score(tls, score_tlui, SVG_SECOND_SCORE)

        assert score_tlui.get_data("viewer_beat_x") == BEAT_X_SECOND_SCORE
        assert score_tlui.svg_view.beat_x_position == BEAT_X_SECOND_SCORE

    def test_beat_positions_survive_saving_and_reloading(
        self, score_tlui, note, tls, tmp_path
    ):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)

        @reloadable(tmp_path / "file.tla")
        def check() -> None:
            score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
            assert score.get_data("viewer_beat_x") == BEAT_X_FIRST_SCORE

    def test_score_saved_without_markers_falls_back_to_stored_positions(
        self, score_tlui, tls, tilia_errors
    ):
        # Files saved before the markers were kept in `svg_data` hold a
        # stripped SVG, so the mapping saved with them is the only source left.
        tls.set_timeline_data(score_tlui.id, "viewer_beat_x", BEAT_X_FIRST_SCORE)

        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITHOUT_MARKERS)

        assert score_tlui.svg_view.beat_x_position == BEAT_X_FIRST_SCORE
        tilia_errors.assert_no_error()

    def test_score_without_any_beat_positions_reports_an_error(
        self, score_tlui, tls, tilia_errors
    ):
        self._import_score(tls, score_tlui, SVG_WITHOUT_MARKERS)

        tilia_errors.assert_in_error_title(SCORE_SVG_CREATE_ERROR.title)

    def test_undo_redo_across_clear_and_reimport(
        self, score_tlui, note, tls, tilia_errors
    ):
        self._import_score(tls, score_tlui, SVG_FIRST_SCORE)
        post(Post.APP_STATE_RECORD, "import first score")
        self._clear(score_tlui)  # the clear command records the state itself
        self._import_score(tls, score_tlui, SVG_SECOND_SCORE)
        post(Post.APP_STATE_RECORD, "import second score")

        commands.execute("edit.undo")
        assert score_tlui.get_data("viewer_beat_x") == {}

        commands.execute("edit.undo")
        assert score_tlui.get_data("viewer_beat_x") == BEAT_X_FIRST_SCORE
        assert score_tlui.svg_view.beat_x_position == BEAT_X_FIRST_SCORE

        commands.execute("edit.redo")
        assert score_tlui.get_data("viewer_beat_x") == {}

        commands.execute("edit.redo")
        assert score_tlui.get_data("viewer_beat_x") == BEAT_X_SECOND_SCORE
        assert score_tlui.svg_view.beat_x_position == BEAT_X_SECOND_SCORE

        tilia_errors.assert_no_error()
