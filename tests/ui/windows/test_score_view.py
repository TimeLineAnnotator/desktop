import json
import math
import sys
from typing import Iterable
from unittest.mock import patch

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QHideEvent, QShowEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication, QComboBox, QDockWidget, QWidget

from tests.constants import EXAMPLE_MUSICXML_PATH, EXAMPLE_REST_MUSICXML_PATH
from tests.mock import Serve, patch_file_dialog, patch_yes_or_no_dialog
from tests.ui.timelines.beat.interact import click_beat_ui
from tests.ui.timelines.interact import (
    click_timeline_ui_element_body,
    click_timeline_ui_view,
    drag_mouse_in_timeline_view,
    press_key,
)
from tests.ui.timelines.marker.interact import click_marker_ui
from tests.utils import (
    get_blank_file_data,
    run_js,
    save_and_reopen,
    undoable,
    wait_until,
)
from tilia.requests import Get, get
from tilia.settings import settings
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.coords import time_x_converter
from tilia.ui.dialogs.choose import ChooseDialog
from tilia.ui.windows.score.score_view import (
    SCORE_INITIAL_HEIGHT,
    VIEWER_PATH,
    ScoreView,
)
from tilia.ui.windows.svg_viewer import SvgStaveNote, SvgViewer

# The viewer's page compiles Verovio when it loads.
pytestmark = [pytest.mark.timeout(60), pytest.mark.draws_scores]

# A score as older versions stored it, small enough for the old viewer to load.
LEGACY_SVG = (
    '<svg width="100" height="50">'
    '<g class="vf-stavenote" id="n1"><rect width="5" height="5"/></g>'
    '<g class="vf-text"><text x="2" font-size="0.000001px">1␟0␟1</text></g>'
    "</svg>"
)


@pytest.fixture(autouse=True)
def delete_web_views():
    yield
    # Destroy deleted viewers now, so that no QtWebEngineProcess outlives the tests.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def open_file_with_svg_score(tmp_path):
    # This version can't make an SVG score, so the file is written by hand.
    file_data = get_blank_file_data()
    file_data["media_metadata"]["media length"] = 100
    file_data["timelines"] = {
        0: {
            "kind": "Score",
            "height": 150,
            "is_visible": True,
            "name": "",
            "ordinal": 1,
            "svg_data": LEGACY_SVG,
            "viewer_beat_x": {},
            "hash": "",
            "components": {},
            "components_hash": "",
        }
    }
    path = tmp_path / "svg_score.tla"
    path.write_text(json.dumps(file_data), encoding="utf-8")
    commands.execute("file.open", path)
    return get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)


def add_score_timeline(name: str = "Score"):
    commands.execute("timelines.add.score", name=name)
    return next(tlui for tlui in get(Get.TIMELINE_UIS) if tlui.get_data("name") == name)


def add_beat_timeline(beat_pattern: list[int], times: Iterable[float]):
    with Serve(Get.FROM_USER_BEAT_PATTERN, (True, beat_pattern)):
        commands.execute("timelines.add.beat", name="Beats")
    for time in times:
        commands.execute("timeline.beat.add", time=time)
    return get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)


def add_beats():
    # example.musicxml has a pick-up measure, which the import adds as measure 0.
    add_beat_timeline([3], range(5, 12))


def add_repeated_beats():
    # Measures 1 and 2 are played twice: the measures are numbered 1, 2, 1, 2, 3.
    beat_tlui = add_beat_timeline([3], range(15))
    click_beat_ui(beat_tlui[6])
    with Serve(Get.FROM_USER_INT, (True, 1)):
        commands.execute("timeline.beat.set_measure_number")


def add_four_beat_measures():
    add_beat_timeline([4], range(9))


def import_score(path: str = EXAMPLE_MUSICXML_PATH, add_measure_zero: bool = True):
    with patch_yes_or_no_dialog(add_measure_zero):
        import_score_file(path)


def import_score_file(path: str = EXAMPLE_MUSICXML_PATH):
    # Answer the import's questions around this.
    with patch_file_dialog(True, [path]):
        commands.execute("timelines.import.score")


def import_score_into(score_tlui):
    # With several score timelines, the import asks which one to import into.
    def choose_timeline(dialog):
        combo_box = dialog.findChild(QComboBox)
        for index in range(combo_box.count()):
            if combo_box.itemData(index) is score_tlui:
                combo_box.setCurrentIndex(index)
        return True

    with patch.object(ChooseDialog, "exec", choose_timeline):
        import_score()


def get_score_view(score_tlui) -> ScoreView:
    viewer = score_tlui.svg_view
    assert isinstance(viewer, ScoreView)
    # Verovio's first start takes seconds, more on a busy machine.
    assert wait_until(
        lambda: viewer.is_score_loaded, timeout=30
    ), f"The page didn't load the score (page ready: {viewer._is_page_ready})."
    return viewer


def get_notes(score_tlui):
    return [element for element in score_tlui if element.kind == ComponentKind.NOTE]


def show_narrow(score_view: ScoreView, width: int = 120, height: int = 200):
    # Makes the score's box narrower than the score, so that it has to scroll.
    # A page that was never shown gets a tiny viewport, and showing a floating
    # viewer instead crashed a macOS CI worker, so the box is sized in the page.
    page = score_view.view.page()
    run_js(
        page,
        f"scoreEl.style.cssText = 'right: auto; bottom: auto; width: {width}px;"
        f" height: {height}px'; window.dispatchEvent(new Event('resize'))",
    )
    assert wait_until(lambda: run_js(page, "scoreEl.clientWidth") == width)
    assert run_js(page, "scoreEl.scrollWidth") > width


def let_page_report():
    # Long enough for any message the page sends to arrive.
    wait_until(lambda: False, timeout=0.5)


def click(score_view: ScoreView, element_id: str, double: bool = False):
    events = ["click", "click", "dblclick"] if double else ["click"]
    run_js(
        score_view.view.page(),
        f"""(() => {{
            const el = document.getElementById({json.dumps(element_id)});
            const target = el.querySelector('.notehead') || el.querySelector('use');
            for (const name of {json.dumps(events)}) {{
                target.dispatchEvent(new MouseEvent(name, {{bubbles: true}}));
            }}
        }})()""",
    )


def get_style(score_view: ScoreView, element_id: str, prop: str) -> str:
    return run_js(
        score_view.view.page(),
        f"getComputedStyle(document.getElementById({json.dumps(element_id)})"
        f".querySelector('.notehead use')).{prop}",
    )


def get_marker(score_view: ScoreView, element_id: str) -> str:
    return run_js(
        score_view.view.page(),
        f"getComputedStyle(document.getElementById({json.dumps(element_id)})).filter",
    )


def add_svg_annotation(viewer: SvgViewer, text: str):
    note = next(item for item in viewer.scene.items() if isinstance(item, SvgStaveNote))
    note.setSelected(True)
    with Serve(Get.FROM_USER_STRING, (True, text)):
        commands.execute("timeline.score.add")


def set_color(note, color: str):
    click_timeline_ui_element_body(note)
    with Serve(Get.FROM_USER_COLOR, (True, QColor(color))):
        commands.execute("timeline.component.set_color")


@pytest.fixture
def smooth_scrolling():
    settings.set("general", "prioritise_performance", False)
    yield
    settings.set("general", "prioritise_performance", True)


@pytest.fixture
def score_tlui(tluis):
    # Unlike the shared fixture, adds the timeline as a user would.
    return add_score_timeline()


@pytest.fixture
def score_view(score_tlui):
    add_beats()
    import_score()
    return get_score_view(score_tlui)


class TestLoad:
    def test_page_reports_score_loaded(self, score_view, score_tlui):
        assert "<mei" in score_view.mei
        for note in get_notes(score_tlui):
            element_id = score_view.get_element_id(note.id)
            assert run_js(
                score_view.view.page(),
                f"document.getElementById({json.dumps(element_id)})"
                ".classList.contains('note')",
            )

    def test_timeline_without_score_has_no_viewer(self, score_tlui):
        # Renaming the timeline renames its viewer, if it has one.
        commands.execute("timeline.set_name", score_tlui, name="Renamed")

        assert score_tlui.svg_view is None

    def test_renaming_timeline_renames_viewer(self, score_view, score_tlui):
        commands.execute("timeline.set_name", score_tlui, name="Renamed")

        assert score_view.menu_title == "Renamed"

    def test_saved_file_has_no_svg(self, score_view, score_tlui, tmp_path):
        save_and_reopen(tmp_path)

        score_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        assert get_notes(score_tlui)
        assert score_tlui.timeline.svg_data == ""


class TestSeek:
    def test_double_click_note_seeks_to_its_time(
        self, score_view, score_tlui, tilia_state
    ):
        note = get_notes(score_tlui)[1]  # half-way through measure 0
        assert note.get_data("start") != 0

        click(score_view, score_view.get_element_id(note.id), double=True)

        assert wait_until(
            lambda: tilia_state.current_time == pytest.approx(note.get_data("start"))
        )

    def test_double_click_repeated_note_seeks_to_nearest_time(
        self, score_tlui, tilia_state
    ):
        add_repeated_beats()
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        first, _, second, _ = get_notes(score_tlui)
        commands.execute("media.seek", second.get_data("start") - 1)

        click(score_view, score_view.get_element_id(first.id), double=True)

        assert wait_until(
            lambda: tilia_state.current_time == pytest.approx(second.get_data("start"))
        )

    def test_double_click_rest_seeks_to_its_time(self, score_tlui, tilia_state):
        add_four_beat_measures()
        import_score(EXAMPLE_REST_MUSICXML_PATH)
        score_view = get_score_view(score_tlui)
        rest_id = run_js(score_view.view.page(), "document.querySelector('g.rest').id")

        click(score_view, rest_id, double=True)

        # The rest is the second beat of measure 1, which starts at 0.
        assert wait_until(lambda: tilia_state.current_time == pytest.approx(1.0))


class TestScroll:
    def test_scroll_to_time_reports_visible_range(
        self, score_view, score_tlui, tilia_state
    ):
        show_narrow(score_view)
        first, *_, last = get_notes(score_tlui)

        commands.execute("media.seek", last.get_data("start"))

        assert wait_until(lambda: score_view.visible_times[0] > first.get_data("start"))
        start, end = score_view.visible_times
        assert start <= last.get_data("start") <= end

    def test_measure_tracker_shows_visible_range(
        self, score_view, score_tlui, tilia_state
    ):
        show_narrow(score_view)
        last = get_notes(score_tlui)[-1]

        commands.execute("media.seek", last.get_data("start"))

        assert wait_until(lambda: score_view.visible_times[0] > 0)
        assert score_tlui.measure_tracker.isVisible()
        assert (score_tlui.tracker_start, score_tlui.tracker_end) == pytest.approx(
            tuple(score_view.visible_times)
        )

    def test_hidden_viewer_leaves_measure_tracker_hidden(self, score_view, score_tlui):
        show_narrow(score_view)
        QApplication.sendEvent(score_view, QHideEvent())

        commands.execute("media.seek", get_notes(score_tlui)[-1].get_data("start"))

        let_page_report()
        assert not score_tlui.measure_tracker.isVisible()

    def test_showing_viewer_again_updates_measure_tracker(self, score_view, score_tlui):
        show_narrow(score_view)
        QApplication.sendEvent(score_view, QHideEvent())
        last = get_notes(score_tlui)[-1]
        commands.execute("media.seek", last.get_data("start"))

        QApplication.sendEvent(score_view, QShowEvent())

        assert wait_until(
            lambda: 0 < score_view.visible_times[0] <= last.get_data("start")
            and last.get_data("start") <= score_view.visible_times[1]
        )
        assert score_tlui.measure_tracker.isVisible()

    def test_score_fits_above_scrollbar(self, score_view):
        page = score_view.view.page()

        show_narrow(score_view, height=100)

        assert run_js(
            page,
            "document.querySelector('#score > svg').getBoundingClientRect().height"
            " <= scoreEl.clientHeight + 0.5",
        )


class TestColor:
    def test_colored_note_shows_its_color(self, score_view, score_tlui):
        note = get_notes(score_tlui)[2]
        element_id = score_view.get_element_id(note.id)

        set_color(note, "#123456")

        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(18, 52, 86)"
        )

    def test_reset_color(self, score_view, score_tlui):
        note = get_notes(score_tlui)[2]
        element_id = score_view.get_element_id(note.id)
        set_color(note, "#123456")

        commands.execute("timeline.component.reset_color")

        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(0, 0, 0)"
        )

    def test_undo_and_redo_color(self, score_view, score_tlui):
        note = get_notes(score_tlui)[2]
        element_id = score_view.get_element_id(note.id)

        with undoable():
            set_color(note, "#123456")

        # Undone and redone.
        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(18, 52, 86)"
        )
        commands.execute("edit.undo")

        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(0, 0, 0)"
        )

    def test_repeated_note_shows_color_of_occurrence_playing_now(self, score_tlui):
        add_repeated_beats()
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        first, _, second, _ = get_notes(score_tlui)
        element_id = score_view.get_element_id(first.id)
        assert score_view.get_element_id(second.id) == element_id
        set_color(first, "#ff0000")
        set_color(second, "#00ff00")

        commands.execute("media.seek", first.get_data("start"))
        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(255, 0, 0)"
        )

        commands.execute("media.seek", second.get_data("start"))
        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(0, 255, 0)"
        )

    def test_repeated_note_follows_seek_with_smooth_scrolling(
        self, smooth_scrolling, score_tlui
    ):
        add_repeated_beats()
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        first, _, second, _ = get_notes(score_tlui)
        element_id = score_view.get_element_id(first.id)
        set_color(first, "#ff0000")
        set_color(second, "#00ff00")

        commands.execute("media.seek", second.get_data("start"))

        assert wait_until(
            lambda: get_style(score_view, element_id, "fill") == "rgb(0, 255, 0)"
        )


class TestSelect:
    def test_click_selects_note(self, score_view, score_tlui):
        element_id = score_view.get_element_id(get_notes(score_tlui)[0].id)

        click(score_view, element_id)

        assert wait_until(lambda: score_view.selected_ids == [element_id])
        assert "drop-shadow" in get_marker(score_view, element_id)

    def test_click_another_note_moves_selection(self, score_view, score_tlui):
        first, second, *_ = get_notes(score_tlui)
        first_id = score_view.get_element_id(first.id)
        second_id = score_view.get_element_id(second.id)
        click(score_view, first_id)

        click(score_view, second_id)

        assert wait_until(lambda: score_view.selected_ids == [second_id])
        assert get_marker(score_view, first_id) == "none"

    def test_selected_note_keeps_its_color(self, score_view, score_tlui):
        note = get_notes(score_tlui)[0]
        element_id = score_view.get_element_id(note.id)
        set_color(note, "#123456")

        click(score_view, element_id)

        assert wait_until(lambda: score_view.selected_ids == [element_id])
        assert get_style(score_view, element_id, "fill") == "rgb(18, 52, 86)"


def has_highlights(score_view: ScoreView, *expected: dict) -> bool:
    # The beat timeline rounds metric positions to thousandths of a measure.
    highlights = get_highlights(score_view)
    return len(highlights) == len(expected) and all(
        highlight == pytest.approx(each, abs=0.01)
        for highlight, each in zip(highlights, expected, strict=True)
    )


def get_highlights(score_view: ScoreView) -> list[dict]:
    # The page hands arrays and objects back as empty strings.
    return json.loads(run_js(score_view.view.page(), "JSON.stringify(highlights)"))


def score_range(score_view: ScoreView, start: tuple, end: tuple) -> dict:
    # A range of the score, from a measure number and fraction to another.
    script = (
        f"JSON.stringify({{qStart: qAt({start[0]}, {start[1]}),"
        f" qEnd: qAt({end[0]}, {end[1]})}})"
    )
    return json.loads(run_js(score_view.view.page(), script))


def measure_of(time: float) -> int:
    beat_tl = get(Get.TIMELINE_COLLECTION).get_timelines_by_type(BeatTimeline)[0]
    return math.floor(beat_tl.get_metric_fraction_by_time(time))


def add_hierarchy(start: float, end: float):
    commands.execute("timelines.add.hierarchy", name="Form")
    commands.execute("timeline.hierarchy.add", start=start, end=end, level=1)
    tlui = next(t for t in get(Get.TIMELINE_UIS) if t.get_data("name") == "Form")
    # The new timeline also has a hierarchy as long as the media.
    return next(
        h for h in tlui if (h.get_data("start"), h.get_data("end")) == (start, end)
    )


def add_marker(time: float):
    commands.execute("timelines.add.marker", name="Cues")
    commands.execute("media.seek", time)
    commands.execute("timeline.marker.add")
    tlui = next(t for t in get(Get.TIMELINE_UIS) if t.get_data("name") == "Cues")
    return tlui[0]


class TestHighlightSelection:
    def test_selected_beat_shades_its_measure(self, score_view):
        beat_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)
        beat = beat_tlui[4]
        measure = measure_of(beat.get_data("time"))

        click_beat_ui(beat)

        expected = score_range(score_view, (measure, 0), (measure, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))
        assert (
            run_js(
                score_view.view.page(),
                "document.querySelectorAll('#tilia-highlights rect').length",
            )
            == 1
        )

    def test_selected_hierarchy_shades_its_range(self, score_view):
        # Beats 5 to 7 make a measure, 8 to 10 the next: the hierarchy ends on
        # a barline, so it ends with the measure before it.
        hierarchy = add_hierarchy(6, 11)
        first, last = measure_of(6), measure_of(10)

        click_timeline_ui_element_body(hierarchy)

        expected = score_range(score_view, (first, 1 / 3), (last, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_range_past_score_end_is_cut_at_it(self, score_view):
        # The score's last measure starts at beat 8; the beats go on to 11.
        hierarchy = add_hierarchy(9, 12)

        click_timeline_ui_element_body(hierarchy)

        measure = measure_of(8)
        expected = score_range(score_view, (measure, 1 / 3), (measure, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_repeated_measure_shades_the_measure_it_repeats(self, score_tlui):
        add_repeated_beats()
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        beat_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)
        second_pass = next(b for b in beat_tlui if b.get_data("time") == 7)

        click_beat_ui(second_pass)

        expected = score_range(score_view, (1, 0), (1, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_range_across_repeat_shades_both_sides(self, score_tlui):
        add_repeated_beats()
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        # From beat 2 of measure 2 to beat 3 of measure 1, played again.
        hierarchy = add_hierarchy(4, 8)

        click_timeline_ui_element_body(hierarchy)

        assert wait_until(
            lambda: has_highlights(
                score_view,
                score_range(score_view, (1, 0), (1, 2 / 3)),
                score_range(score_view, (2, 1 / 3), (2, 1)),
            )
        )

    def test_overlapping_selections_are_joined(self, score_view):
        hierarchy = add_hierarchy(5, 8)
        beat_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)
        measure = measure_of(5)

        click_timeline_ui_element_body(hierarchy)
        click_beat_ui(beat_tlui[1], modifier="ctrl")

        expected = score_range(score_view, (measure, 0), (measure, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_deselecting_clears_shading(self, score_view):
        beat_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)
        click_beat_ui(beat_tlui[4])
        assert wait_until(lambda: get_highlights(score_view))

        click_timeline_ui_view(beat_tlui.view, "left", 0, 0)

        assert wait_until(lambda: get_highlights(score_view) == [])
        assert not run_js(
            score_view.view.page(), "document.querySelector('#tilia-highlights')"
        )

    def test_selection_in_score_timeline_is_not_shaded(self, score_view, score_tlui):
        click_timeline_ui_element_body(get_notes(score_tlui)[0])

        let_page_report()
        assert get_highlights(score_view) == []

    def test_shading_out_of_view_scrolls_to_it(self, score_view):
        show_narrow(score_view)
        beat_tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", BeatTimeline)
        page = score_view.view.page()
        scroll = run_js(page, "scoreEl.scrollLeft")

        beat = next(beat for beat in beat_tlui if beat.get_data("time") == 9)

        click_beat_ui(beat)

        assert wait_until(lambda: run_js(page, "scoreEl.scrollLeft") > scroll)
        assert wait_until(lambda: score_view.visible_times[1] >= 9)

    def test_dragging_selected_marker_moves_shading(self, score_view):
        marker = add_marker(6)
        click_marker_ui(marker)
        expected = score_range(score_view, (measure_of(6), 0), (measure_of(6), 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(9), 0)

        expected = score_range(score_view, (measure_of(9), 0), (measure_of(9), 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_measure_played_twice_in_a_row_shades_it(self, score_tlui):
        # Measure 1 is played twice, then measure 2: numbered 1, 1, 2.
        beat_tlui = add_beat_timeline([3], range(9))
        click_beat_ui(beat_tlui[3])
        with Serve(Get.FROM_USER_INT, (True, 1)):
            commands.execute("timeline.beat.set_measure_number")
        import_score(add_measure_zero=False)
        score_view = get_score_view(score_tlui)
        # From beat 2 of the first time to beat 2 of the second.
        hierarchy = add_hierarchy(1, 4)

        click_timeline_ui_element_body(hierarchy)

        expected = score_range(score_view, (1, 0), (1, 1))
        assert wait_until(lambda: has_highlights(score_view, expected))

    def test_deleting_timeline_clears_shading(self, score_view):
        hierarchy = add_hierarchy(5, 8)
        click_timeline_ui_element_body(hierarchy)
        assert wait_until(lambda: get_highlights(score_view))

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.delete", hierarchy.timeline_ui)

        assert wait_until(lambda: get_highlights(score_view) == [])

    def test_dragging_selected_marker_does_not_scroll_back(self, score_view):
        show_narrow(score_view)
        marker = add_marker(5)
        click_marker_ui(marker)
        assert wait_until(lambda: get_highlights(score_view))
        page = score_view.view.page()
        run_js(page, "scoreEl.scrollLeft = scoreEl.scrollWidth")
        scroll = run_js(page, "scoreEl.scrollLeft")

        drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(5.5), 0)

        let_page_report()
        assert run_js(page, "scoreEl.scrollLeft") == scroll


class TestPage:
    def test_runs_no_inline_scripts(self, score_view):
        page = score_view.view.page()

        run_js(
            page,
            "document.body.insertAdjacentHTML('beforeend',"
            ' \'<img src="data:," onerror="window.ran = true">\')',
        )

        assert not wait_until(lambda: run_js(page, "window.ran === true"), 1)

    def test_bridge_offers_only_viewer_calls(self, score_view):
        names = run_js(
            score_view.view.page(),
            "JSON.stringify(Object.keys(bridge).filter("
            "(name) => typeof bridge[name] === 'function' && !name.includes('(')))",
        )

        # Besides the viewer's calls: qwebchannel.js's own helpers, and the
        # deleteLater that Qt publishes for every object.
        assert set(json.loads(names)) - {
            "propertyUpdate",
            "signalEmitted",
            "unwrapProperties",
            "unwrapQObject",
            "deleteLater",
        } == {
            "viewerReady",
            "onScoreLoaded",
            "onViewportChanged",
            "onSelectionChanged",
            "onElementDoubleClicked",
            "onError",
        }

    def test_has_no_context_menu(self, score_view):
        # Its Reload, Back and View Source would take the page off the score.
        assert score_view.view.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu

    def test_reloaded_page_shows_score_again(self, score_view):
        page = score_view.view.page()
        run_js(page, "window.beforeReload = true")

        page.triggerAction(QWebEnginePage.WebAction.Reload)

        assert wait_until(
            lambda: run_js(
                page,
                "window.beforeReload === undefined"
                " && document.querySelectorAll('g.note').length > 0",
            ),
            timeout=30,
        )
        assert score_view.is_score_loaded

    def test_stays_on_viewer(self, score_view):
        page = score_view.view.page()

        run_js(page, "location.href = 'https://example.com/'")

        let_page_report()
        assert page.url().isLocalFile()
        assert run_js(page, "document.querySelectorAll('g.note').length") > 0

    @pytest.mark.skipif(sys.platform != "win32", reason="drive letters")
    def test_accepts_viewer_with_other_drive_letter_case(self, score_view):
        path = str(VIEWER_PATH)
        url = QUrl.fromLocalFile(path[0].swapcase() + path[1:])

        assert score_view.view.page().acceptNavigationRequest(
            url, QWebEnginePage.NavigationType.NavigationTypeTyped, True
        )

    def test_shows_svg_without_scripts(self, score_view):
        page = score_view.view.page()
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<script>window.ran = true</script>"
            '<g id="x" onclick="window.ran = true"/><foreignObject/></svg>'
        )

        run_js(page, f"showSvg({json.dumps(svg)})")

        assert json.loads(
            run_js(
                page,
                "JSON.stringify([!!scoreEl.querySelector('script'),"
                " !!scoreEl.querySelector('foreignObject'),"
                " document.getElementById('x').hasAttribute('onclick')])",
            )
        ) == [False, False, False]

    def test_deleted_viewer_ignores_late_page_messages(self, score_view, score_tlui):
        bridge = score_view._bridge
        commands.execute("timeline.delete", score_tlui, confirm=False)

        # A message the page sent before the viewer was deleted.
        bridge.onViewportChanged(
            json.dumps(
                {
                    "start": {"measure": "1", "fraction": 0},
                    "end": {"measure": "2", "fraction": 0},
                }
            )
        )


class TestUndo:
    def test_undo_and_redo_import(self, score_tlui):
        add_beats()

        with undoable():
            import_score()

        viewer = get_score_view(score_tlui)
        commands.execute("edit.undo")
        assert viewer.isHidden()
        assert not viewer.is_score_loaded
        commands.execute("edit.redo")
        assert get_score_view(score_tlui) is viewer
        assert not viewer.isHidden()

    def test_undo_and_redo_import_over_another_score(self, score_tlui):
        add_beats()
        # Without its pick-up measure, then with it: two different scores.
        import_score(add_measure_zero=False)
        viewer = get_score_view(score_tlui)
        with patch_yes_or_no_dialog([True, True]):
            import_score_file()
        get_score_view(score_tlui)

        commands.execute("edit.undo")

        notes = get_notes(score_tlui)
        assert len(notes) == 2
        assert get_score_view(score_tlui) is viewer
        assert all(viewer.get_element_id(note.id) for note in notes)

        commands.execute("edit.redo")

        notes = get_notes(score_tlui)
        assert len(notes) == 4
        assert get_score_view(score_tlui) is viewer
        assert all(viewer.get_element_id(note.id) for note in notes)

    def test_undoing_clear_shows_score_again(self, score_view, score_tlui):
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)

        commands.execute("edit.undo")

        assert get_score_view(score_tlui) is score_view
        assert not score_view.isHidden()


class TestClear:
    def test_reimport_keeps_viewer_and_page(self, score_view, score_tlui):
        run_js(score_view.view.page(), "window.samePage = true")

        import_score()

        assert get_score_view(score_tlui) is score_view
        assert run_js(score_view.view.page(), "window.samePage === true")

    def test_reimport_keeps_viewer_where_it_was(self, score_view, score_tlui):
        main_window = get(Get.MAIN_WINDOW)
        main_window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, score_view)

        import_score()

        assert get_score_view(score_tlui) is score_view
        assert (
            main_window.dockWidgetArea(score_view)
            == Qt.DockWidgetArea.TopDockWidgetArea
        )

    def test_clearing_timeline_hides_viewer(self, score_view, score_tlui):
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)

        assert score_view.isHidden()
        assert not score_tlui.measure_tracker.isVisible()

    def test_deleting_timeline_deletes_viewer(self, score_view, score_tlui):
        commands.execute("timeline.delete", score_tlui, confirm=False)

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not shiboken6.isValid(score_view)


class TestSeveralScoreTimelines:
    def test_seek_with_a_timeline_without_score(self, score_view, tilia_state):
        add_score_timeline("Other")

        commands.execute("media.seek", 7)

        assert tilia_state.current_time == 7

    def test_each_timeline_has_its_own_viewer(self, score_tlui):
        other_tlui = add_score_timeline("Other")
        add_beats()

        import_score_into(score_tlui)
        import_score_into(other_tlui)

        viewer = get_score_view(score_tlui)
        other_viewer = get_score_view(other_tlui)
        assert viewer is not other_viewer
        assert viewer.timeline_id == score_tlui.id
        assert other_viewer.timeline_id == other_tlui.id

    def test_deleting_a_timeline_keeps_the_others_viewer(self, score_tlui):
        other_tlui = add_score_timeline("Other")
        add_beats()
        import_score_into(score_tlui)
        import_score_into(other_tlui)
        viewer = get_score_view(score_tlui)

        commands.execute("timeline.delete", other_tlui, confirm=False)

        assert score_tlui.svg_view is viewer


class TestSvgScores:
    def test_file_with_svg_score_opens_in_old_viewer(self, tluis, tmp_path):
        score_tlui = open_file_with_svg_score(tmp_path)

        assert isinstance(score_tlui.svg_view, SvgViewer)

    def test_old_viewer_moves_measure_tracker(self, tluis, tmp_path):
        score_tlui = open_file_with_svg_score(tmp_path)
        add_beats()
        viewer = score_tlui.svg_view

        # Paints the score, as showing it would.
        viewer.view.grab()

        assert viewer.visible_times[1] > 0
        assert score_tlui.measure_tracker.isVisible()
        assert (score_tlui.tracker_start, score_tlui.tracker_end) == pytest.approx(
            tuple(viewer.visible_times)
        )

    def test_import_replaces_svg_score(self, tluis, tmp_path):
        score_tlui = open_file_with_svg_score(tmp_path)
        add_beats()

        import_score()

        get_score_view(score_tlui)
        assert score_tlui.timeline.svg_data == ""

    def test_undo_and_redo_import_over_svg_score(self, tluis, tmp_path):
        score_tlui = open_file_with_svg_score(tmp_path)
        add_beats()

        with undoable():
            import_score()

        viewer = get_score_view(score_tlui)
        commands.execute("edit.undo")
        assert isinstance(score_tlui.svg_view, SvgViewer)
        commands.execute("edit.redo")
        assert get_score_view(score_tlui) is not viewer

    def test_undoing_clear_brings_back_svg_score_and_annotations(self, tluis, tmp_path):
        score_tlui = open_file_with_svg_score(tmp_path)
        add_svg_annotation(score_tlui.svg_view, "Cadence")
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score_tlui)
        assert score_tlui.svg_view is None

        commands.execute("edit.undo")

        viewer = score_tlui.svg_view
        assert isinstance(viewer, SvgViewer)
        assert [
            annotation["annotation"].text()
            for annotation in viewer.tla_annotations.values()
        ] == ["Cadence"]


class TestShortcuts:
    def test_app_shortcuts_work_after_click_on_score(self, score_view):
        ctrl = Qt.KeyboardModifier.ControlModifier
        shift = Qt.KeyboardModifier.ShiftModifier
        main_window = get(Get.MAIN_WINDOW)
        main_window.show()
        try:
            page_widget = score_view.view.focusProxy()
            # A click in the page gives it the keyboard focus.
            QTest.mouseClick(
                page_widget,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                page_widget.rect().center(),
            )
            # The page has nothing to edit, so it leaves these keys to the app.
            # Undo comes last, as undoing the import closes the viewer.
            for command, key, modifiers in [
                ("timeline.component.copy", "c", ctrl),
                ("timeline.component.paste", "v", ctrl),
                ("edit.redo", "z", ctrl | shift),
                ("edit.undo", "z", ctrl),
            ]:
                assert wait_until(lambda: QApplication.focusWidget() is page_widget)
                triggered = QSignalSpy(get_qaction(command).triggered)

                press_key(key, modifier=modifiers)

                assert triggered.count() == 1, command
        finally:
            main_window.hide()


class TestResize:
    @pytest.fixture
    def main_window(self, tluis):
        window = get(Get.MAIN_WINDOW)
        window.resize(1200, 900)
        window.show()
        yield window
        window.hide()

    @staticmethod
    def _separator(main_window, dock):
        central = main_window.centralWidget().geometry()
        top = dock.geometry().top()
        return QPoint(central.center().x(), (central.bottom() + top + 1) // 2)

    @pytest.fixture
    def dock(self, main_window):
        # Not a viewer: with a web view in a shown window, the offscreen platform
        # tests run on can crash, though a real one doesn't. All docks share the
        # main window's separators, so the viewer's own dock adds nothing here.
        dock = QDockWidget("Dock", main_window)
        dock.setWidget(QWidget())
        main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        yield dock
        main_window.removeDockWidget(dock)
        dock.deleteLater()

    def test_dragging_the_separator_resizes_a_dock(self, main_window, dock):
        assert QTest.qWaitForWindowExposed(main_window)
        QTest.qWait(100)  # The window lays out its docks after showing them.
        height = dock.height()
        start = self._separator(main_window, dock)
        end = start - QPoint(0, 100)

        QTest.mousePress(main_window, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(main_window, end)
        QTest.qWait(50)  # The window moves its separators on a timer.
        QTest.mouseRelease(main_window, Qt.MouseButton.LeftButton, pos=end)

        assert wait_until(lambda: dock.height() == height + 100)

    def test_new_viewer_asks_for_room_for_the_score(self, score_view):
        # Asserted on the hint as the main window is shared by the tests, and its
        # dock area keeps the height it had, as it does for a user.
        assert score_view.sizeHint().height() >= SCORE_INITIAL_HEIGHT


class TestDock:
    def test_viewer_can_float(self, score_view):
        assert score_view.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable

    @pytest.mark.parametrize(
        "area",
        [
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
            Qt.DockWidgetArea.TopDockWidgetArea,
            Qt.DockWidgetArea.BottomDockWidgetArea,
        ],
    )
    def test_viewer_docks_on_any_side(self, score_view, area):
        assert score_view.isAreaAllowed(area)
