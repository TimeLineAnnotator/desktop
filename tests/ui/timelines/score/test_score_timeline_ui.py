import json

import pytest
from PySide6.QtGui import QColor

from tests.constants import (
    EXAMPLE_MULTISTAFF_MUSICXML_PATH,
    EXAMPLE_RESTS_ONLY_MUSICXML_PATH,
)
from tests.mock import (
    Serve,
    patch_file_dialog,
    patch_yes_or_no_dialog,
)
from tests.utils import get_blank_file_data, reloadable, undoable
from tilia.errors import SCORE_STAFF_ID_ERROR
from tilia.exceptions import NoReplyToRequest
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


class TestClear:
    def test_clear(self, score_tlui, note):
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)

        assert score_tlui.is_empty

    def test_undo_redo(self, score_tlui, note):
        # Score components have no user-facing creation command, so the fixture
        # builds them directly and nothing records the resulting state. Record
        # it here, or undo would restore the empty timeline the tlui fixture
        # recorded instead. The staff and the clef have equal ordinals, so undo
        # may recreate them in either order; the timeline hash must not notice.
        post(Post.APP_STATE_RECORD, "components created by fixture")

        with undoable(), patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)


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

    commands.execute("file.open", tmp_file)

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

    commands.execute("file.open", tmp_file)

    tilia_errors.assert_in_error_title(SCORE_STAFF_ID_ERROR.title)
    assert tls.get_timeline_by_type(ScoreTimeline) is None


def test_symbols_do_not_collide_with_staff_without_notes(
    qtui, score_tlui, beat_tlui, beat_tl
):
    # With no notes to size the staff, the space reserved above it must
    # still keep the clef clear of the staff lines.
    beat_tl.beat_pattern = [1]
    for i in range(1, 3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2]
    beat_tl.recalculate_measures()

    with (
        patch_file_dialog(True, [EXAMPLE_RESTS_ONLY_MUSICXML_PATH]),
        patch_yes_or_no_dialog(False),
    ):
        commands.execute("timelines.import.score")

    clef = score_tlui.timeline.get_component_by_attr("KIND", ComponentKind.CLEF)
    staff = score_tlui.timeline.get_component_by_attr("KIND", ComponentKind.STAFF)
    clef_bottom_y = score_tlui.get_element(clef.id).body.sceneBoundingRect().bottom()
    staff_top_y = score_tlui.get_element(staff.id).staff_lines.lines[0].line().y1()

    assert clef_bottom_y <= staff_top_y


SVG_WITH_MARKERS = (
    "<svg>"
    "<g class='vf-text'><text font-size='0.00001px' x='100'>1␟0␟4</text></g>"
    "<g class='vf-text'><text font-size='0.00001px' x='150'>1␟2␟4</text></g>"
    "</svg>"
)


class TestSvgView:
    def test_is_none_when_no_viewer_exists(self, score_tlui):
        assert score_tlui.svg_view is None

    def test_reading_it_does_not_register_a_viewer(self, score_tlui):
        assert score_tlui.svg_view is None

        with pytest.raises(NoReplyToRequest):
            get(Get.SCORE_VIEWER, score_tlui.id)

    def test_get_or_create_creates_and_loads(self, score_tlui, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        assert score_tlui.get_or_create_svg_view().is_svg_loaded

    def test_get_or_create_returns_existing_viewer(self, score_tlui, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        assert score_tlui.get_or_create_svg_view() is score_tlui.svg_view

    def test_viewer_and_tracker_come_back_after_reloading(
        self, score_tlui, note, tls, tmp_path
    ):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        @reloadable(tmp_path / "file.tla")
        def check() -> None:
            score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
            assert score.svg_view is not None
            assert score.measure_tracker.isVisible()


class TestResetSvg:
    def test_deletes_existing_viewer(self, score_tlui, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        score_tlui.reset_svg()

        assert score_tlui.svg_view is None

    def test_does_not_raise_when_no_viewer_exists(self, score_tlui):
        score_tlui.reset_svg()

        assert score_tlui.svg_view is None

    def test_does_not_raise_when_another_timeline_owns_the_viewer(
        self, score_tlui, tls, tluis
    ):
        other = tls.create_timeline(ScoreTimeline)
        tls.set_timeline_data(other.id, "svg_data", SVG_WITH_MARKERS)

        score_tlui.reset_svg()

        assert tluis.get_timeline_ui(other.id).svg_view is not None


class TestAudioTimeChange:
    def test_does_not_create_a_viewer(self, score_tlui):
        post(Post.PLAYER_CURRENT_TIME_CHANGED, 1.0, None)

        assert score_tlui.svg_view is None


class TestClear:
    @staticmethod
    def _clear(score_tlui):
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)

    def test_closes_the_svg_viewer(self, score_tlui, note, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        self._clear(score_tlui)

        assert score_tlui.svg_view is None

    def test_viewer_stays_closed_during_playback(self, score_tlui, note, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        self._clear(score_tlui)

        post(Post.PLAYER_CURRENT_TIME_CHANGED, 1.0, None)

        assert score_tlui.svg_view is None

    def test_discards_svg_data(self, score_tlui, note, tls):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        self._clear(score_tlui)

        assert score_tlui.get_data("svg_data") == ""

    def test_viewer_stays_closed_after_zooming_and_renaming(
        self, score_tlui, note, tls
    ):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        self._clear(score_tlui)

        commands.execute("view.zoom.in")
        commands.execute("timeline.set_name", score_tlui, name="Renamed")

        with pytest.raises(NoReplyToRequest):
            get(Get.SCORE_VIEWER, score_tlui.id)

    def test_redoing_clear_with_an_annotation_does_not_reopen_the_viewer(
        self, score_tlui, note, tls
    ):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        score_tlui.timeline.create_component(
            ComponentKind.SCORE_ANNOTATION,
            x=10.0,
            y=20.0,
            viewer_id=0,
            text="annotation",
            font_size=14,
        )
        post(Post.APP_STATE_RECORD, "setup")
        self._clear(score_tlui)

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        with pytest.raises(NoReplyToRequest):
            get(Get.SCORE_VIEWER, score_tlui.id)

    def test_restoring_a_cleared_state_closes_the_viewer(self, score_tlui, note, tls):
        # The path undo/redo takes when it lands on a cleared state.
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        self._clear(score_tlui)
        cleared_state, _ = tls.serialize_timelines()
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)

        tls.restore_state(cleared_state)

        assert score_tlui.get_data("svg_data") == ""
        assert score_tlui.svg_view is None

    def test_score_does_not_come_back_after_saving_and_reloading(
        self, score_tlui, note, tls, tmp_path
    ):
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        self._clear(score_tlui)

        @reloadable(tmp_path / "file.tla")
        def check() -> None:
            score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
            assert score.get_data("svg_data") == ""
            assert score.svg_view is None

    def test_undo_redo(self, score_tlui, note, tls):
        # `undoable()` can't be used here: TimelineComponentManager.restore_state
        # recreates components in set-iteration order while hash_components()
        # hashes them in list order, so a restored state's components_hash
        # depends on PYTHONHASHSEED. That is a pre-existing defect in the base
        # timeline, unrelated to clearing; assert the restored values directly.
        tls.set_timeline_data(score_tlui.id, "svg_data", SVG_WITH_MARKERS)
        svg_data = score_tlui.get_data("svg_data")
        post(Post.APP_STATE_RECORD, "setup")
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)

        commands.execute("edit.undo")

        assert len(score_tlui.timeline) == 3
        assert score_tlui.get_data("svg_data") == svg_data
        assert score_tlui.svg_view is not None

        commands.execute("edit.redo")

        assert len(score_tlui.timeline) == 0
        assert score_tlui.get_data("svg_data") == ""
        assert score_tlui.svg_view is None


FOUR_FOUR = "<time><beats>4</beats><beat-type>4</beat-type></time>"
TREBLE_CLEF = "<clef><sign>G</sign><line>2</line></clef>"


def _score_with_clef(clef: str, pitch_tag: str = "pitch", time: str = FOUR_FOUR) -> str:
    def note(step: str, octave: int) -> str:
        prefix = "" if pitch_tag == "pitch" else "display-"
        return (
            f"<note><{pitch_tag}><{prefix}step>{step}</{prefix}step>"
            f"<{prefix}octave>{octave}</{prefix}octave></{pitch_tag}>"
            "<duration>2</duration><type>half</type></note>"
        )

    return f"""<score-partwise version="4.0">
    <part-list><score-part id="P1"><part-name>P</part-name></score-part></part-list>
    <part id="P1"><measure number="1">
        <attributes>
            <divisions>1</divisions>
            <key><fifths>0</fifths></key>
            {time}
            {clef}
        </attributes>
        {note("G", 4)}{note("C", 4)}
    </measure></part>
    </score-partwise>
    """


def _import_score_text(text: str, tmp_path) -> None:
    path = tmp_path / "score.musicxml"
    path.write_text(text, encoding="utf-8")
    with patch_file_dialog(True, [str(path)]), patch_yes_or_no_dialog(True):
        commands.execute("timelines.import.score")


def _note_positions(score_tlui) -> list[tuple[float, int]]:
    """Each note's top and number of ledger lines."""
    notes = score_tlui.timeline.get_components_by_attr("KIND", ComponentKind.NOTE)
    positions = []
    for note in sorted(notes):
        ui = score_tlui.get_element(note.id)
        positions.append((ui.top_y, len(ui.ledger_line.lines) if ui.ledger_line else 0))
    return positions


@pytest.mark.parametrize(
    "clef, pitch_tag",
    [("", "pitch"), ("<clef><sign>percussion</sign></clef>", "unpitched")],
    ids=["no clef", "percussion clef"],
)
def test_notes_without_usable_clef_are_placed_as_in_treble_clef(
    clef, pitch_tag, qtui, score_tlui, beat_tlui, tmp_path
):
    # As MuseScore, Verovio and OSMD do. No clef is drawn: the score has none
    # TiLiA can show.
    for time in range(5):
        commands.execute("timeline.beat.add", time=time)
    _import_score_text(_score_with_clef(TREBLE_CLEF, pitch_tag), tmp_path)
    positions_in_treble = _note_positions(score_tlui)
    # G4 has no ledger line, C4 has one.
    assert [ledger_lines for _, ledger_lines in positions_in_treble] == [0, 1]

    _import_score_text(_score_with_clef(clef, pitch_tag), tmp_path)

    assert _note_positions(score_tlui) == positions_in_treble
    assert not score_tlui.timeline.get_components_by_attr("KIND", ComponentKind.CLEF)


def _drawn(time_signature_ui) -> tuple[str, str]:
    """A time signature's top and bottom lines, read left to right. A plus
    between two pairs is in both."""
    glyphs = sorted(time_signature_ui.body.glyphs, key=lambda glyph: glyph.x())
    top = "".join(g.character for g in glyphs if g.row != "denominator")
    bottom = "".join(g.character for g in glyphs if g.row != "numerator")
    return top, bottom


@pytest.mark.parametrize(
    "time, drawn",
    [
        (FOUR_FOUR, ("4", "4")),
        ("<time><beats>3+2</beats><beat-type>8</beat-type></time>", ("3+2", "8")),
        (
            "<time><beats>2</beats><beat-type>4</beat-type>"
            "<beats>3</beats><beat-type>8</beat-type></time>",
            ("2+3", "4+8"),
        ),
    ],
    ids=["simple", "composite", "several pairs"],
)
def test_time_signature_is_drawn_as_written(
    time, drawn, qtui, score_tlui, beat_tlui, tmp_path
):
    for t in range(5):
        commands.execute("timeline.beat.add", time=t)
    _import_score_text(_score_with_clef(TREBLE_CLEF, time=time), tmp_path)

    @reloadable(tmp_path / "file.tla")
    def check_drawn():
        score = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        (time_signature,) = score.timeline.get_components_by_attr(
            "KIND", ComponentKind.TIME_SIGNATURE
        )
        time_signature_ui = score.get_element(time_signature.id)
        assert _drawn(time_signature_ui) == drawn
        y_by_row = {}
        for glyph in time_signature_ui.body.glyphs:
            assert not glyph.pixmap().isNull()
            y_by_row.setdefault(glyph.row, set()).add(glyph.y())
        # The plus between two pairs is halfway down.
        assert max(y_by_row["numerator"]) < min(y_by_row["denominator"])
        for y in y_by_row.get("between", []):
            assert max(y_by_row["numerator"]) < y < min(y_by_row["denominator"])
