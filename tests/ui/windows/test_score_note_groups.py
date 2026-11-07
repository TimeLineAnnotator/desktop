import csv
import json

import pytest
from lxml import etree
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.constants import EXAMPLE_QUARTER_TONES_MUSICXML_PATH
from tests.mock import Serve, patch_file_dialog, patch_yes_or_no_dialog
from tests.ui.timelines.interact import press_key
from tests.utils import run_js, save_and_reopen, undoable, wait_until
from tilia.requests import Get, Post, get, post
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands
from tilia.ui.windows.score.score_view import ScoreView

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def delete_web_views():
    yield
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def get_loaded_view(score_tlui) -> ScoreView:
    viewer = score_tlui.svg_view
    assert isinstance(viewer, ScoreView)
    assert wait_until(lambda: viewer.is_score_loaded, timeout=30)
    return viewer


@pytest.fixture
def score_tlui(tluis):
    commands.execute("timelines.add.score", name="Score")
    return next(t for t in get(Get.TIMELINE_UIS) if t.get_data("name") == "Score")


@pytest.fixture
def score_view(score_tlui):
    with Serve(Get.FROM_USER_BEAT_PATTERN, (True, [4])):
        commands.execute("timelines.add.beat", name="Beats")
    for time in range(17):
        commands.execute("timeline.beat.add", time=time)
    with patch_yes_or_no_dialog(False), patch_file_dialog(
        True, [EXAMPLE_QUARTER_TONES_MUSICXML_PATH]
    ):
        commands.execute("timelines.import.score")
    view = get_loaded_view(score_tlui)
    size_score_box(view)
    return view


def size_score_box(view):
    # A page that was never shown gets a tiny viewport, so the box is sized in
    # the page, as in test_score_view.py.
    page = view.view.page()
    run_js(
        page,
        "scoreEl.style.cssText = 'right: auto; bottom: auto; width: 1200px;"
        " height: 500px'; window.dispatchEvent(new Event('resize'))",
    )
    assert wait_until(lambda: run_js(page, "scoreEl.clientWidth") == 1200)


def notes_of(tlui):
    return [e for e in tlui if e.kind == ComponentKind.NOTE]


def groups_of(tlui):
    return [e for e in tlui if e.kind == ComponentKind.NOTE_GROUP]


def element_at(tlui, start, staff_index):
    """The first note's element at a time, on a staff: 0 flute, 1 clarinet,
    2 viola, 3 cello. Beats last 1 s."""
    return next(
        n.get_data("element_id")
        for n in sorted(notes_of(tlui), key=lambda n: n.get_data("pitch"))
        if n.get_data("start") == start and n.get_data("staff_index") == staff_index
    )


def wait_for_selection(view, ids):
    assert wait_until(
        lambda: sorted(view.selected_note_ids) == sorted(ids)
    ), f"Selected {view.selected_note_ids}, not {ids}"


def click_note(view, element_id, modifier=False):
    run_js(
        view.view.page(),
        f"""document.getElementById({json.dumps(element_id)})
            .querySelector('.notehead').dispatchEvent(new MouseEvent('click',
            {{bubbles: true, ctrlKey: {str(modifier).lower()}}}))""",
    )


def select_notes(view, ids):
    for i, element_id in enumerate(ids):
        click_note(view, element_id, modifier=i > 0)
    wait_for_selection(view, ids)


def note_rect(view, element_id):
    return json.loads(
        run_js(
            view.view.page(),
            f"""(() => {{
                const r = document.getElementById({json.dumps(element_id)})
                    .querySelector('.notehead').getBoundingClientRect();
                return JSON.stringify([r.left, r.top, r.right, r.bottom]);
            }})()""",
        )
    )


def drag(view, start, end, modifier=False):
    run_js(
        view.view.page(),
        f"""(() => {{
            const options = (x, y) => ({{bubbles: true, clientX: x, clientY: y,
                                         button: 0, ctrlKey: {str(modifier).lower()}}});
            scoreEl.dispatchEvent(new MouseEvent('mousedown', options({start[0]}, {start[1]})));
            window.dispatchEvent(new MouseEvent('mousemove', options({end[0]}, {end[1]})));
            window.dispatchEvent(new MouseEvent('mouseup', options({end[0]}, {end[1]})));
            scoreEl.dispatchEvent(new MouseEvent('click', options({end[0]}, {end[1]})));
        }})()""",
    )


def drawn_groups(view):
    return json.loads(
        run_js(
            view.view.page(),
            """JSON.stringify([...document.querySelectorAll('#tilia-groups g.blob')]
                .map((blob) => ({
                    id: blob.dataset.group,
                    circles: blob.querySelectorAll('circle').length,
                    lines: blob.querySelectorAll('line').length,
                    fill: blob.getAttribute('fill'),
                    active: blob.classList.contains('active'),
                })))""",
        )
    )


def drawn_labels(view):
    return json.loads(
        run_js(
            view.view.page(),
            "JSON.stringify([...document.querySelectorAll('#tilia-group-labels text')]"
            ".map((t) => t.textContent))",
        )
    )


def click_at(view, point):
    # Beside a notehead, so that the click lands on the blob alone.
    run_js(
        view.view.page(),
        f"""scoreEl.dispatchEvent(new MouseEvent('click',
            {{bubbles: true, clientX: {point[0]}, clientY: {point[1]}}}))""",
    )


def label_boxes(view):
    return json.loads(
        run_js(
            view.view.page(),
            """JSON.stringify([...document.querySelectorAll('#tilia-group-labels text')]
                .map((t) => {
                    const b = t.getBBox();
                    return [b.x, b.y, b.x + b.width, b.y + b.height];
                }))""",
        )
    )


class TestScoreWithoutKeySignature:
    def test_imports_and_shows_its_notes(self, score_tlui, tmp_path):
        with Serve(Get.FROM_USER_BEAT_PATTERN, (True, [4])):
            commands.execute("timelines.add.beat", name="Beats")
        for time in range(17):
            commands.execute("timeline.beat.add", time=time)

        score = etree.parse(EXAMPLE_QUARTER_TONES_MUSICXML_PATH)
        for key in score.findall(".//key"):
            key.getparent().remove(key)
        path = tmp_path / "atonal.musicxml"
        score.write(path)

        with patch_yes_or_no_dialog(False), patch_file_dialog(True, [str(path)]):
            commands.execute("timelines.import.score")

        view = get_loaded_view(score_tlui)
        assert notes_of(score_tlui)
        assert not [e for e in score_tlui if e.kind == ComponentKind.KEY_SIGNATURE]
        select_notes(view, [element_at(score_tlui, 0, 0)])
        assert view.selected_note_ids


class TestImportedPitches:
    def test_quarter_tones_are_kept(self, score_view, score_tlui):
        accidentals = {n.get_data("accidental") for n in notes_of(score_tlui)}
        assert {0.5, 1.5, -0.5, -1.5} <= accidentals

    def test_sounding_pitch_classes(self, score_view, score_tlui):
        # Flute, first measure: C, D quarter-sharp, F, E quarter-flat.
        flute = [element_at(score_tlui, t, 0) for t in range(4)]
        analysis = score_tlui.timeline.analyse_elements(flute)
        assert analysis.pitch_classes == (0, 5, 7, 10)

    def test_transposing_instrument_sounds_lower(self, score_view, score_tlui):
        # Clarinet in B flat, first measure: written E, F three-quarters-sharp,
        # G, A quarter-flat, sounding a major second lower.
        clarinet = [element_at(score_tlui, t, 1) for t in range(4)]
        analysis = score_tlui.timeline.analyse_elements(clarinet)
        assert analysis.pitch_classes == (4, 9, 10, 13)

    def test_viewer_shows_quarter_tone_accidentals(self, score_view):
        assert run_js(
            score_view.view.page(), "document.querySelectorAll('g.accid').length"
        )
        assert 'accid="1qs"' in score_view.mei

    def test_timeline_draws_notes_without_quarter_tone_icon(
        self, score_view, score_tlui
    ):
        quarter_tone = next(
            n for n in notes_of(score_tlui) if n.get_data("accidental") == 0.5
        )
        assert quarter_tone.accidental is None


class TestSelection:
    def test_panel_shows_analysis_of_selection(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, t, 0) for t in range(3)])
        text = score_view.group_panel.analysis_label.text()
        # C, D quarter-sharp, F.
        assert "Prime form (0 5 10)" in text
        assert "Cardinality: 3" in text

    def test_panel_shows_forte_name_of_12_note_set(self, score_view, score_tlui):
        # Cello: C, G; viola: B flat. Pitch classes in semitones: 0, 7, 10.
        ids = [
            element_at(score_tlui, 0, 3),
            element_at(score_tlui, 2, 3),
            element_at(score_tlui, 2, 2),
        ]
        select_notes(score_view, ids)
        assert "Forte: 3-7" in score_view.group_panel.analysis_label.text()

    def test_panel_says_a_mixed_set_has_no_forte_name(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, t, 0) for t in range(3)])
        assert "none" in score_view.group_panel.analysis_label.text()

    def test_buttons_follow_selection(self, score_view, score_tlui):
        panel = score_view.group_panel
        assert not panel.create_button.isEnabled()
        select_notes(score_view, [element_at(score_tlui, 0, 0)])
        assert panel.create_button.isEnabled()
        assert not panel.update_button.isEnabled()
        assert not panel.delete_button.isEnabled()

    def test_drag_selects_notes_in_box(self, score_view, score_tlui):
        first = element_at(score_tlui, 0, 0)
        second = element_at(score_tlui, 1, 0)
        a, b = note_rect(score_view, first), note_rect(score_view, second)
        drag(score_view, (a[0] - 1, a[1] - 1), (b[2] + 1, b[3] + 1))
        assert wait_until(lambda: {first, second} <= set(score_view.selected_note_ids))

    def test_drag_with_ctrl_adds(self, score_view, score_tlui):
        first = element_at(score_tlui, 0, 0)
        other = element_at(score_tlui, 3, 3)
        select_notes(score_view, [first])
        r = note_rect(score_view, other)
        drag(score_view, (r[0] - 1, r[1] - 1), (r[2] + 1, r[3] + 1), modifier=True)
        assert wait_until(lambda: {first, other} <= set(score_view.selected_note_ids))

    def test_short_drag_is_a_click(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, 0, 0)])
        r = note_rect(score_view, element_at(score_tlui, 3, 3))
        run_js(
            score_view.view.page(),
            f"""(() => {{
                const o = {{bubbles: true, clientX: {r[0] + 1}, clientY: {r[1] + 1}, button: 0}};
                document.getElementById({json.dumps(element_at(score_tlui, 3, 3))})
                    .querySelector('.notehead').dispatchEvent(new MouseEvent('mousedown', o));
                window.dispatchEvent(new MouseEvent('mouseup', o));
                document.getElementById({json.dumps(element_at(score_tlui, 3, 3))})
                    .querySelector('.notehead').dispatchEvent(new MouseEvent('click', o));
            }})()""",
        )
        wait_for_selection(score_view, [element_at(score_tlui, 3, 3)])

    def test_selecting_a_chord_selects_its_notes(self, score_view, score_tlui):
        run_js(
            score_view.view.page(),
            """document.querySelector('g.chord').dispatchEvent(
                new MouseEvent('click', {bubbles: true}))""",
        )
        assert wait_until(lambda: len(score_view.selected_note_ids) == 2)

    def test_ctrl_wheel_zooms(self, score_view):
        page = score_view.view.page()
        width = run_js(
            page, "scoreEl.querySelector('svg').getBoundingClientRect().width"
        )
        run_js(
            page,
            """scoreEl.dispatchEvent(new WheelEvent('wheel',
                {bubbles: true, cancelable: true, ctrlKey: true, deltaY: -100}))""",
        )
        assert wait_until(
            lambda: run_js(
                page, "scoreEl.querySelector('svg').getBoundingClientRect().width"
            )
            > width
        )


class TestGroups:
    def test_create_from_selection(self, score_view, score_tlui):
        ids = [element_at(score_tlui, t, 0) for t in range(3)]
        select_notes(score_view, ids)
        with undoable():
            commands.execute("timeline.score.group.create")
        assert groups_of(score_tlui)[0].get_data("element_ids") == ids

    def test_create_draws_blob_with_label(self, score_view, score_tlui):
        ids = [element_at(score_tlui, t, 0) for t in range(3)]
        commands.execute("timeline.score.group.create", element_ids=ids)
        assert wait_until(lambda: drawn_groups(score_view))
        blob = drawn_groups(score_view)[0]
        assert blob["circles"] == 3
        assert blob["lines"] == 2
        assert blob["fill"].startswith("#")
        assert blob["active"]
        assert drawn_labels(score_view) == ["(0 5 10)"]

    def test_new_group_has_no_name(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, t, 0) for t in range(3)])
        score_view.group_panel.create_button.click()
        assert groups_of(score_tlui)[0].get_data("label") == ""
        assert wait_until(lambda: score_view.group_panel.label_edit.isEnabled())
        assert score_view.group_panel.label_edit.text() == ""
        assert drawn_labels(score_view) == ["(0 5 10)"]

    def test_single_note_makes_a_blob(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        assert wait_until(lambda: drawn_groups(score_view))
        assert drawn_groups(score_view)[0]["lines"] == 0

    def test_create_without_notes_does_nothing(self, score_view, score_tlui):
        commands.execute("timeline.score.group.create")
        assert not groups_of(score_tlui)

    def test_create_ignores_unknown_elements(self, score_view, score_tlui):
        commands.execute("timeline.score.group.create", element_ids=["nope"])
        assert not groups_of(score_tlui)

    def test_create_through_button(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, 0, 0)])
        QTest.mouseClick(
            score_view.group_panel.create_button, Qt.MouseButton.LeftButton
        )
        assert len(groups_of(score_tlui)) == 1

    def test_shortcut_groups_after_click_in_page(self, score_view, score_tlui):
        select_notes(score_view, [element_at(score_tlui, 0, 0)])
        main_window = get(Get.MAIN_WINDOW)
        main_window.show()
        try:
            page_widget = score_view.view.focusProxy()
            page_widget.setFocus()
            assert wait_until(lambda: QApplication.focusWidget() is page_widget)
            press_key("g", modifier=Qt.KeyboardModifier.ControlModifier)
        finally:
            main_window.hide()
        assert len(groups_of(score_tlui)) == 1

    def test_groups_get_different_colors(self, score_view, score_tlui):
        for t in range(2):
            commands.execute(
                "timeline.score.group.create",
                element_ids=[element_at(score_tlui, t, 0)],
            )
        assert wait_until(lambda: len(drawn_groups(score_view)) == 2)
        assert len({g["fill"] for g in drawn_groups(score_view)}) == 2

    def test_a_note_can_be_in_two_groups(self, score_view, score_tlui):
        shared = element_at(score_tlui, 0, 0)
        commands.execute("timeline.score.group.create", element_ids=[shared])
        commands.execute(
            "timeline.score.group.create",
            element_ids=[shared, element_at(score_tlui, 1, 0)],
        )
        assert wait_until(lambda: len(drawn_groups(score_view)) == 2)

    def test_click_on_blob_activates_group(self, score_view, score_tlui):
        ids = [element_at(score_tlui, 0, 0), element_at(score_tlui, 1, 0)]
        commands.execute("timeline.score.group.create", element_ids=ids)
        group_id = groups_of(score_tlui)[0].id
        select_notes(score_view, [element_at(score_tlui, 3, 3)])
        assert score_view.active_group_id is None
        rect = note_rect(score_view, ids[0])
        # Off the notehead, still on the blob.
        click_at(score_view, ((rect[0] + rect[2]) / 2, rect[1] - 2))
        assert wait_until(lambda: score_view.active_group_id == group_id)
        wait_for_selection(score_view, ids)
        assert score_view.group_panel.delete_button.isEnabled()

    def test_click_on_empty_space_deactivates(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        assert wait_until(lambda: score_view.active_group_id is not None)
        click_at(score_view, (1, 1))
        assert wait_until(lambda: score_view.active_group_id is None)
        wait_for_selection(score_view, [])

    def test_update_notes(self, score_view, score_tlui):
        first = element_at(score_tlui, 0, 0)
        commands.execute("timeline.score.group.create", element_ids=[first])
        group = groups_of(score_tlui)[0]
        new_ids = [first, element_at(score_tlui, 1, 0)]
        with undoable():
            commands.execute(
                "timeline.score.group.set_notes", group_id=group.id, element_ids=new_ids
            )
        assert groups_of(score_tlui)[0].get_data("element_ids") == new_ids

    def test_set_label(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        group = groups_of(score_tlui)[0]
        with undoable():
            commands.execute(
                "timeline.score.group.set_label", "Motif a", group_id=group.id
            )
        assert group.get_data("label") == "Motif a"
        assert wait_until(lambda: drawn_labels(score_view) == ["Motif a: (0)"])

    def test_label_through_panel(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        panel = score_view.group_panel
        assert wait_until(lambda: panel.label_edit.isEnabled())
        panel.label_edit.setText("Motif b")
        panel.label_edit.editingFinished.emit()
        assert groups_of(score_tlui)[0].get_data("label") == "Motif b"

    def test_delete(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        group = groups_of(score_tlui)[0]
        with undoable():
            commands.execute("timeline.score.group.delete", group_id=group.id)
        assert not groups_of(score_tlui)
        assert wait_until(lambda: not drawn_groups(score_view))

    def test_undo_create_removes_blob(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        assert wait_until(lambda: drawn_groups(score_view))
        commands.execute("edit.undo")
        assert wait_until(lambda: not drawn_groups(score_view))
        commands.execute("edit.redo")
        assert wait_until(lambda: drawn_groups(score_view))

    def test_clearing_timeline_removes_groups(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        score_tlui.timeline.clear()
        assert not groups_of(score_tlui)

    def test_score_elements_of_timeline_are_not_disturbed(self, score_view, score_tlui):
        # A group has no time, and scaling the timeline mustn't ask for one.
        commands.execute(
            "timeline.score.group.create", element_ids=[element_at(score_tlui, 0, 0)]
        )
        score_tlui.timeline.component_manager.scale(2)
        assert len(groups_of(score_tlui)) == 1


class TestLabels:
    def test_labels_of_groups_on_one_note_do_not_overlap(self, score_view, score_tlui):
        note = element_at(score_tlui, 0, 0)
        for label in ["First group", "Second group", "Third group"]:
            commands.execute("timeline.score.group.create", [note], label)
        assert wait_until(lambda: len(drawn_labels(score_view)) == 3)

        boxes = label_boxes(score_view)
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                assert not overlap, (a, b)


class TestSaveAndReopen:
    def test_score_and_groups_survive(self, score_view, score_tlui, tmp_path):
        ids = [element_at(score_tlui, t, 0) for t in range(3)]
        commands.execute("timeline.score.group.create", element_ids=ids, label="Motif")
        color = groups_of(score_tlui)[0].get_data("color")

        save_and_reopen(tmp_path)

        tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        viewer = get_loaded_view(tlui)
        group = groups_of(tlui)[0]
        assert group.get_data("element_ids") == ids
        assert group.get_data("label") == "Motif"
        assert group.get_data("color") == color
        assert wait_until(lambda: drawn_labels(viewer) == ["Motif: (0 5 10)"])
        assert wait_until(lambda: drawn_groups(viewer)[0]["circles"] == 3)

    def test_quarter_tones_survive(self, score_view, score_tlui, tmp_path):
        expected = sorted(
            n.get_data("sounding_pitch_class_24") for n in notes_of(score_tlui)
        )
        save_and_reopen(tmp_path)
        tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        get_loaded_view(tlui)
        assert (
            sorted(n.get_data("sounding_pitch_class_24") for n in notes_of(tlui))
            == expected
        )

    def test_viewer_still_seeks_after_reopening(self, score_view, score_tlui, tmp_path):
        save_and_reopen(tmp_path)
        tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        viewer = get_loaded_view(tlui)
        beat_tl = get(
            Get.TIMELINE_COLLECTION
        ).get_beat_timeline_for_measure_calculation()
        assert isinstance(beat_tl, BeatTimeline)
        note = notes_of(tlui)[0]
        assert viewer.get_element_id(note.id) == note.get_data("element_id")


def table_rows(view):
    table = view.group_table_window.table
    return [
        [table.item(row, column).text() for column in range(table.columnCount())]
        for row in range(table.rowCount())
    ]


def table_column(view, column):
    return [row[column] for row in table_rows(view)]


def row_of_group(view, group_id):
    table = view.group_table_window.table
    return next(r for r in range(table.rowCount()) if table.group_id_at(r) == group_id)


class TestGroupTable:
    GROUP, MEASURE, PRIME, FORTE, CARDINALITY, NORMAL, PITCHES, VECTOR = range(8)

    def _flute(self, score_tlui):
        # Pitch classes 0 5 10, in measure 1.
        return [element_at(score_tlui, t, 0) for t in range(3)]

    def _last_measure(self, score_tlui):
        # One note, in measure 4.
        return [element_at(score_tlui, 12, 0)]

    def _make_groups(self, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=self._last_measure(score_tlui)
        )
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        return groups_of(score_tlui)

    def test_starts_hidden(self, score_view):
        assert score_view.group_table_window.isHidden()
        assert not score_view.group_panel.table_button.isChecked()

    def test_button_shows_and_hides_it(self, score_view):
        button = score_view.group_panel.table_button
        button.click()
        assert not score_view.group_table_window.isHidden()
        assert button.isChecked()
        button.click()
        assert score_view.group_table_window.isHidden()
        assert not button.isChecked()

    def test_command_shows_it(self, score_view):
        commands.execute("timeline.score.group.toggle_table")
        assert not score_view.group_table_window.isHidden()
        assert score_view.group_panel.table_button.isChecked()

    def test_closing_the_window_unchecks_the_button(self, score_view):
        score_view.group_panel.table_button.click()
        score_view.group_table_window.close()
        assert score_view.group_table_window.isHidden()
        assert not score_view.group_panel.table_button.isChecked()

    def test_escape_closes_the_window(self, score_view):
        window = score_view.group_table_window
        score_view.group_panel.table_button.click()
        assert QTest.qWaitForWindowExposed(window)
        QTest.keyClick(window.table, Qt.Key.Key_Escape)
        assert window.isHidden()
        assert not score_view.group_panel.table_button.isChecked()

    def test_windows_menu_request_checks_the_button(self, score_view):
        window = score_view.group_table_window
        window.show()
        window.close()
        post(Post.WINDOW_UPDATE_REQUEST, window.id, True)
        assert not window.isHidden()
        assert score_view.group_panel.table_button.isChecked()

    def test_opening_leaves_the_score_its_width(self, score_view):
        width = score_view.view.width()
        score_view.group_panel.table_button.click()
        assert score_view.view.width() == width

    def test_window_closes_with_the_score(self, score_view, score_tlui):
        window = score_view.group_table_window
        score_view.group_panel.table_button.click()
        score_view.clear_score()
        assert window.isHidden()

    def test_shows_a_groups_analysis(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        assert table_rows(score_view) == [
            ["", "1", "(0 5 10)", "", "3", "[0 5 10]", "{0 5 10}", "<000020000100>"]
        ]

    def test_shows_forte_name_of_12_note_set(self, score_view, score_tlui):
        ids = [
            element_at(score_tlui, 0, 3),
            element_at(score_tlui, 2, 3),
            element_at(score_tlui, 2, 2),
        ]
        commands.execute("timeline.score.group.create", element_ids=ids)
        assert table_column(score_view, self.FORTE) == ["3-7"]

    def test_group_across_measures(self, score_view, score_tlui):
        ids = [element_at(score_tlui, 3, 0), element_at(score_tlui, 4, 0)]
        commands.execute("timeline.score.group.create", element_ids=ids)
        assert table_column(score_view, self.MEASURE) == ["1–2"]

    def test_shows_label_and_color(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create",
            element_ids=self._flute(score_tlui),
            label="Motif",
        )
        assert table_column(score_view, self.GROUP) == ["Motif"]
        swatch = score_view.group_table_window.table.item(0, 0).data(
            Qt.ItemDataRole.DecorationRole
        )
        assert swatch.name() == groups_of(score_tlui)[0].get_data("color")

    def test_follows_changes_to_a_group(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        group = groups_of(score_tlui)[0]
        commands.execute("timeline.score.group.set_label", "Motif", group_id=group.id)
        assert table_column(score_view, self.GROUP) == ["Motif"]
        commands.execute(
            "timeline.score.group.set_notes",
            group_id=group.id,
            element_ids=self._flute(score_tlui)[:2],
        )
        assert table_column(score_view, self.CARDINALITY) == ["2"]
        commands.execute("timeline.score.group.delete", group_id=group.id)
        assert table_rows(score_view) == []

    def test_follows_undo_and_redo(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        assert wait_until(lambda: drawn_groups(score_view))
        commands.execute("edit.undo")
        assert table_rows(score_view) == []
        commands.execute("edit.redo")
        assert table_column(score_view, self.PRIME) == ["(0 5 10)"]

    def test_survives_reopening_the_file(self, score_view, score_tlui, tmp_path):
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        save_and_reopen(tmp_path)
        tlui = get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)
        viewer = get_loaded_view(tlui)
        assert wait_until(lambda: table_column(viewer, self.PRIME) == ["(0 5 10)"])

    def test_starts_in_score_order(self, score_view, score_tlui):
        self._make_groups(score_tlui)
        assert table_column(score_view, self.MEASURE) == ["1", "4"]

    def test_sorts_prime_forms_by_cardinality_first(self, score_view, score_tlui):
        self._make_groups(score_tlui)
        table = score_view.group_table_window.table
        table.sortItems(self.PRIME, Qt.SortOrder.AscendingOrder)
        assert table_column(score_view, self.PRIME) == ["(0)", "(0 5 10)"]
        table.sortItems(self.PRIME, Qt.SortOrder.DescendingOrder)
        assert table_column(score_view, self.PRIME) == ["(0 5 10)", "(0)"]

    def test_stays_sorted_when_a_group_is_added(self, score_view, score_tlui):
        self._make_groups(score_tlui)
        table = score_view.group_table_window.table
        table.sortItems(self.PRIME, Qt.SortOrder.DescendingOrder)
        commands.execute(
            "timeline.score.group.create",
            element_ids=[element_at(score_tlui, t, 0) for t in range(2)],
        )
        assert table_column(score_view, self.CARDINALITY) == ["3", "2", "1"]

    def test_clicking_a_row_selects_the_group(self, score_view, score_tlui):
        groups = self._make_groups(score_tlui)
        score_view.group_panel.table_button.click()
        assert QTest.qWaitForWindowExposed(score_view.group_table_window)
        table = score_view.group_table_window.table
        group = next(g for g in groups if len(g.get_data("element_ids")) == 3)
        row = row_of_group(score_view, group.id)
        QTest.mouseClick(
            table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=table.visualItemRect(table.item(row, self.PRIME)).center(),
        )
        assert wait_until(lambda: score_view.active_group_id == group.id)
        wait_for_selection(score_view, group.get_data("element_ids"))
        assert score_view.group_panel.delete_button.isEnabled()
        assert table.selected_group_id() == group.id

    def test_selecting_a_row_is_not_an_undo_step(self, score_view, score_tlui):
        groups = self._make_groups(score_tlui)
        table = score_view.group_table_window.table
        table.selectRow(row_of_group(score_view, groups[0].id))
        assert wait_until(lambda: score_view.active_group_id == groups[0].id)
        commands.execute("edit.undo")
        assert len(groups_of(score_tlui)) == 1

    def test_selected_row_follows_sorting(self, score_view, score_tlui):
        groups = self._make_groups(score_tlui)
        table = score_view.group_table_window.table
        table.sortItems(self.PRIME, Qt.SortOrder.DescendingOrder)
        table.selectRow(0)
        expected = table.group_id_at(0)
        assert wait_until(lambda: score_view.active_group_id == expected)
        assert expected == next(
            g.id for g in groups if len(g.get_data("element_ids")) == 3
        )

    def test_click_on_blob_selects_the_row(self, score_view, score_tlui):
        ids = [element_at(score_tlui, 0, 0), element_at(score_tlui, 1, 0)]
        commands.execute("timeline.score.group.create", element_ids=ids)
        group_id = groups_of(score_tlui)[0].id
        select_notes(score_view, [element_at(score_tlui, 3, 3)])
        table = score_view.group_table_window.table
        assert wait_until(lambda: table.selected_group_id() is None)
        rect = note_rect(score_view, ids[0])
        click_at(score_view, ((rect[0] + rect[2]) / 2, rect[1] - 2))
        assert wait_until(lambda: table.selected_group_id() == group_id)

    def test_click_on_empty_space_clears_the_row(self, score_view, score_tlui):
        commands.execute(
            "timeline.score.group.create", element_ids=self._flute(score_tlui)
        )
        table = score_view.group_table_window.table
        assert wait_until(lambda: table.selected_group_id() is not None)
        click_at(score_view, (1, 1))
        assert wait_until(lambda: table.selected_group_id() is None)

    def _narrow_score(self, view):
        page = view.view.page()
        run_js(
            page,
            "scoreEl.style.width = '300px'; window.dispatchEvent(new Event('resize'))",
        )
        assert wait_until(lambda: run_js(page, "scoreEl.clientWidth") == 300)
        assert run_js(page, "scoreEl.scrollWidth") > 300

    def test_selecting_a_row_scrolls_to_the_group(self, score_view, score_tlui):
        groups = self._make_groups(score_tlui)
        self._narrow_score(score_view)
        run_js(score_view.view.page(), "scoreEl.scrollLeft = 0")
        group = next(g for g in groups if len(g.get_data("element_ids")) == 1)
        score_view.group_table_window.table.selectRow(
            row_of_group(score_view, group.id)
        )
        note = group.get_data("element_ids")[0]
        box = json.loads(
            run_js(
                score_view.view.page(),
                """(() => {
                    const r = scoreEl.getBoundingClientRect();
                    return JSON.stringify([r.left, r.right]);
                })()""",
            )
        )

        def is_in_view():
            rect = note_rect(score_view, note)
            return box[0] <= rect[0] and rect[2] <= box[1]

        assert wait_until(is_in_view)

    def test_group_in_view_does_not_scroll(self, score_view, score_tlui):
        groups = self._make_groups(score_tlui)
        page = score_view.view.page()
        run_js(page, "scoreEl.scrollLeft = 0")
        group = next(g for g in groups if len(g.get_data("element_ids")) == 3)
        score_view.group_table_window.table.selectRow(
            row_of_group(score_view, group.id)
        )
        assert wait_until(lambda: score_view.active_group_id == group.id)
        assert run_js(page, "scoreEl.scrollLeft") == 0


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.reader(file))


class TestExportTable:
    HEADER = [
        "Group",
        "Measure",
        "Prime form",
        "Forte",
        "Cardinality",
        "Normal form",
        "Pitch classes",
        "Interval-class vector",
    ]

    def _make_groups(self, score_tlui):
        commands.execute(
            "timeline.score.group.create",
            element_ids=[element_at(score_tlui, 12, 0)],
            label="Last",
        )
        commands.execute(
            "timeline.score.group.create",
            element_ids=[element_at(score_tlui, t, 0) for t in range(3)],
        )

    def test_button_is_off_without_groups(self, score_view, score_tlui):
        button = score_view.group_table_window.export_button
        assert not button.isEnabled()
        self._make_groups(score_tlui)
        assert button.isEnabled()
        commands.execute("edit.undo")
        commands.execute("edit.undo")
        assert wait_until(lambda: not button.isEnabled())

    def test_button_saves_the_path_chosen(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        path = tmp_path / "groups.csv"
        with patch_file_dialog(True, [str(path)]):
            score_view.group_table_window.export_button.click()
        assert read_csv(path) == [self.HEADER] + table_rows(score_view)

    def test_values(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        path = tmp_path / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        rows = read_csv(path)
        assert [row[0] for row in rows[1:]] == ["", "Last"]
        assert rows[1][1] == "1"
        assert rows[1][2] == "(0 5 10)"
        assert rows[1][4] == "3"
        assert rows[1][6] == "{0 5 10}"

    def test_range_of_measures(self, score_view, score_tlui, tmp_path):
        commands.execute(
            "timeline.score.group.create",
            element_ids=[element_at(score_tlui, t, 0) for t in (0, 12)],
        )
        path = tmp_path / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        assert read_csv(path)[1][1] == "1\u20134"

    def test_keeps_the_order_of_the_table(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        table = score_view.group_table_window.table
        table.sortByColumn(TestGroupTable.PRIME, Qt.SortOrder.AscendingOrder)
        by_prime_form = table_column(score_view, TestGroupTable.PRIME)
        table.sortByColumn(TestGroupTable.PRIME, Qt.SortOrder.DescendingOrder)
        assert table_column(score_view, TestGroupTable.PRIME) == by_prime_form[::-1]
        path = tmp_path / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        assert [row[2] for row in read_csv(path)[1:]] == by_prime_form[::-1]

    def test_works_with_the_window_closed(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        assert score_view.group_table_window.isHidden()
        path = tmp_path / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        assert len(read_csv(path)) == 3

    def test_adds_the_extension(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        with patch_file_dialog(True, [str(tmp_path / "groups")]):
            commands.execute("timeline.score.group.export_table")
        assert (tmp_path / "groups.csv").exists()

    def test_cancelling_writes_nothing(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        with patch_file_dialog(False, [str(tmp_path / "groups.csv")]):
            commands.execute("timeline.score.group.export_table")
        assert not list(tmp_path.iterdir())

    def test_failure_is_reported(self, score_view, score_tlui, tmp_path, tilia_errors):
        self._make_groups(score_tlui)
        path = tmp_path / "missing" / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        tilia_errors.assert_in_error_title("Export note groups")
        tilia_errors.assert_in_error_message("groups.csv")

    def test_no_groups_writes_nothing(self, score_view, tmp_path):
        path = tmp_path / "groups.csv"
        commands.execute("timeline.score.group.export_table", path=str(path))
        assert not path.exists()

    def test_is_not_an_undo_step(self, score_view, score_tlui, tmp_path):
        self._make_groups(score_tlui)
        commands.execute(
            "timeline.score.group.export_table", path=str(tmp_path / "groups.csv")
        )
        commands.execute("edit.undo")
        assert len(groups_of(score_tlui)) == 1
