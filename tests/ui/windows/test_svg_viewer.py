import pytest
from lxml import etree
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.mock import Serve
from tests.utils import undoable
from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.windows.svg_viewer import SvgStaveNote, SvgTlaAnnotation, SvgViewer


def _make_svg(*texts):
    """Build a tiny SVG containing the given <text> elements wrapped in
    `<g class="vf-text">`. Each `texts` entry is (font_size, text)."""
    root = etree.Element("svg")
    for font_size, text in texts:
        g = etree.SubElement(root, "g", attrib={"class": "vf-text"})
        t = etree.SubElement(g, "text", attrib={"font-size": font_size, "x": "0"})
        t.text = text
    return root


class TestStripBeatXMarkers:
    def test_removes_three_part_marker_with_zero_font(self):
        root = _make_svg(("0.000009999999999999999px", "1␟0␟32"))
        SvgViewer._strip_beat_x_markers(root)
        assert root.findall(".//g[@class='vf-text']") == []

    def test_removes_all_markers_from_fixture_shape(self):
        # Mirrors the actual file structure: many <g class='vf-text'> wrappers
        # around <text font-size='0.000009...'>m␟b␟max</text>.
        root = _make_svg(
            *[
                ("0.000009999999999999999px", f"{m}␟{b}␟32")
                for m in range(50)
                for b in range(8)
            ]
        )
        SvgViewer._strip_beat_x_markers(root)
        assert root.findall(".//g[@class='vf-text']") == []

    def test_keeps_text_with_normal_font_size(self):
        root = _make_svg(("15px", "regular text"))
        SvgViewer._strip_beat_x_markers(root)
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_bumps_font_size_for_tiny_non_marker_text(self):
        # Tiny font size but text is NOT a 3-part marker → bump to 15px,
        # keep the element so it renders at a sane size.
        root = _make_svg(("0.5px", "annotation"))
        SvgViewer._strip_beat_x_markers(root)
        kept = root.findall(".//g[@class='vf-text']")
        assert len(kept) == 1
        assert kept[0][0].attrib["font-size"] == "15px"

    def test_handles_missing_font_size_attribute(self):
        root = etree.Element("svg")
        g = etree.SubElement(root, "g", attrib={"class": "vf-text"})
        etree.SubElement(g, "text").text = "anything"  # no font-size attr
        SvgViewer._strip_beat_x_markers(root)
        # Should not raise; element kept since we can't tell what to do.
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_handles_unparseable_font_size(self):
        root = _make_svg(("not-a-number", "anything"))
        SvgViewer._strip_beat_x_markers(root)
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_handles_empty_g_wrapper(self):
        root = etree.Element("svg")
        etree.SubElement(root, "g", attrib={"class": "vf-text"})  # no children
        SvgViewer._strip_beat_x_markers(root)  # should not raise

    def test_mixed_content_keeps_only_real_glyphs(self):
        root = _make_svg(
            ("0.000009999999999999999px", "1␟0␟32"),  # marker, removed
            ("15px", "Allegro"),  # real text, kept
            ("0.5px", "annotation"),  # tiny non-marker, kept w/ 15px
            ("0.000009999999999999999px", "5␟4␟32"),  # marker, removed
        )
        SvgViewer._strip_beat_x_markers(root)
        kept = root.findall(".//g[@class='vf-text']")
        assert len(kept) == 2
        kept_texts = sorted(g[0].text for g in kept)
        assert kept_texts == ["Allegro", "annotation"]
        # The bumped one should now be 15px.
        font_sizes = sorted(g[0].attrib["font-size"] for g in kept)
        assert font_sizes == ["15px", "15px"]


SVG_WITHOUT_MARKERS = (
    "<svg><g class='vf-text'><text font-size='15px' x='0'>Allegro</text></g></svg>"
)
SVG_WITH_MARKERS = (
    "<svg>"
    "<g class='vf-text'><text font-size='0.00001px' x='100'>1␟0␟4</text></g>"
    "<g class='vf-text'><text font-size='0.00001px' x='150'>1␟2␟4</text></g>"
    "</svg>"
)


class TestLoadSvgData:
    def test_loads_svg_with_beat_markers(self, qtui, score_tl, tls, tluis):
        tls.set_timeline_data(score_tl.id, "svg_data", SVG_WITH_MARKERS)

        assert tluis.get_timeline_ui(score_tl.id).svg_view.is_svg_loaded
        assert score_tl.get_data("viewer_beat_x") == {1.0: 100.0, 1.5: 150.0}

    def test_displays_error_when_no_beat_positions_found(
        self, qtui, score_tl, tls, tluis, tilia_errors
    ):
        tls.set_timeline_data(score_tl.id, "svg_data", SVG_WITHOUT_MARKERS)

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("Beat positions not found")
        assert not tluis.get_timeline_ui(score_tl.id).svg_view.is_svg_loaded


# --- Score/"VexFlow" viewer regression tests --------------------------
#
# These drive the real SvgViewer end to end: toolbar commands via
# commands.execute(...), keyboard shortcuts via QTest.keyClick, and mouse/
# wheel input via real Qt events on the view's viewport. They sidestep only
# the MusicXML -> SVG render step (tilia/parsers/score/musicxml_to_svg.py,
# which drives a QWebEngineView through VexFlow) by loading a hand-built SVG
# directly through SvgViewer.load_svg_data -- the same method the app calls
# once that pipeline hands back its result. This mirrors how this file's own
# _make_svg already stands in for real VexFlow output further up.

NOTE_SEEK_XS = [10.0, 100.0, 200.0]


def _make_score_svg(note_ids=("note0", "note1", "note2")):
    """A minimal SVG with one <g class="vf-stavenote"> per note, each with
    real geometry so QSvgRenderer.boundsOnElement resolves a rect. This is
    enough for SvgViewer.create_stavenotes to build real SvgStaveNote items."""
    notes = "".join(
        f'<g class="vf-stavenote" id="{note_id}">'
        f'<rect x="{x}" y="40" width="8" height="10"/></g>'
        for note_id, x in zip(note_ids, NOTE_SEEK_XS, strict=True)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" '
        f'width="400" height="120">{notes}</svg>'
    )


@pytest.fixture
def scored_beat_tl(beat_tl):
    """Backend beat timeline with 3 beats at t=0,1,2 (measures 0-2, one beat
    each), so the viewer's scene-x -> time math resolves to a single,
    predictable time per note instead of an empty/ambiguous mapping."""
    beat_tl.beat_pattern = [1]
    for i in range(3):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [0, 1, 2]
    beat_tl.recalculate_measures()
    return beat_tl


@pytest.fixture
def svg_viewer(score_tlui, score_tl, scored_beat_tl):
    """The real SvgViewer, loaded with synthetic-but-valid SVG data (see
    _make_score_svg) instead of a real MusicXML/VexFlow render."""
    score_tl.set_data(
        "viewer_beat_x", dict(zip([0.0, 1.0, 2.0], NOTE_SEEK_XS, strict=True))
    )
    viewer = score_tlui.get_or_create_svg_view()
    viewer.load_svg_data(_make_score_svg())
    # The dock widget's own isVisible() (and WindowShortcut-context actions
    # like "Shift+Return") depend on the *main window* being shown too, not
    # just the viewer itself -- mirrors tests.ui.timelines.interact.get_focused_widget.
    get(Get.MAIN_WINDOW).show()
    viewer.show()
    QApplication.processEvents()
    # Loading synthetic SVG data (above) mutates timeline.svg_data outside of
    # any commands.execute(...) call, so it never reaches the undo manager's
    # history. Without this record, undoable() in the tests below would diff
    # its own fresh "before" snapshot against the undo manager's stale
    # pre-fixture one (empty svg_data) and either crash re-parsing "" as SVG
    # or fail the state comparison.
    post(Post.APP_STATE_RECORD, "svg_viewer fixture")
    return viewer


def _stavenotes(viewer: SvgViewer) -> list[SvgStaveNote]:
    return sorted(
        (i for i in viewer.scene.items() if isinstance(i, SvgStaveNote)),
        key=lambda i: i.x(),
    )


def _annotations(viewer: SvgViewer) -> list[SvgTlaAnnotation]:
    return [i for i in viewer.scene.items() if isinstance(i, SvgTlaAnnotation)]


def _add_annotation_via_toolbar(viewer: SvgViewer, text="Allegro") -> SvgTlaAnnotation:
    _stavenotes(viewer)[0].setSelected(True)
    with Serve(Get.FROM_USER_STRING, (True, text)):
        commands.execute("timeline.score.add")
    return _annotations(viewer)[0]


class TestAnnotations:
    def test_create_annotation_shortcut(self, svg_viewer):
        _stavenotes(svg_viewer)[0].setSelected(True)
        with undoable(), Serve(Get.FROM_USER_STRING, (True, "Allegro")):
            QTest.keyClick(svg_viewer, Qt.Key.Key_Return)
            annotations = _annotations(svg_viewer)
            assert len(annotations) == 1
            assert annotations[0].text() == "Allegro"

    def test_delete_annotation_shortcut(self, svg_viewer):
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        with undoable():
            QTest.keyClick(svg_viewer, Qt.Key.Key_Delete)
            assert _annotations(svg_viewer) == []

    def test_edit_annotation_shortcut(self, svg_viewer):
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        with undoable(), Serve(Get.FROM_USER_STRING, (True, "Andante")):
            QTest.keyClick(
                svg_viewer, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier
            )
            assert annotation.text() == "Andante"

    def test_move_annotation_with_mouse(self, svg_viewer):
        annotation = _add_annotation_via_toolbar(svg_viewer)
        view = svg_viewer.view
        press_pt = view.mapFromScene(annotation.sceneBoundingRect().center())
        release_pt = press_pt + QPoint(40, 15)
        before = (annotation.x(), annotation.y())
        with undoable():
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=press_pt)
            QTest.mouseMove(view.viewport(), pos=release_pt)
            QTest.mouseRelease(
                view.viewport(), Qt.MouseButton.LeftButton, pos=release_pt
            )
            after = (annotation.x(), annotation.y())
            assert after != before

    def test_edit_annotation_to_empty_deletes_it_toolbar(self, svg_viewer):
        # Reading: clearing the text hits the "no text inputted" prompt;
        # confirming it deletes the annotation.
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        with (
            undoable(),
            Serve(Get.FROM_USER_STRING, (True, "")),
            Serve(Get.FROM_USER_YES_OR_NO, True),
        ):
            commands.execute("timeline.score.edit")
            assert _annotations(svg_viewer) == []

    def test_edit_annotation_to_empty_kept_if_declined_toolbar(self, svg_viewer):
        # Same flow, declining the confirmation: annotation must survive.
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        with (
            Serve(Get.FROM_USER_STRING, (True, "")),
            Serve(Get.FROM_USER_YES_OR_NO, False),
        ):
            commands.execute("timeline.score.edit")
        assert _annotations(svg_viewer) == [annotation]

    def test_increase_annotation_font_toolbar(self, svg_viewer):
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        size_before = annotation.font().pointSize()
        with undoable():
            commands.execute("timeline.score.font_inc")
            assert annotation.font().pointSize() == size_before * 2

    def test_decrease_annotation_font_toolbar(self, svg_viewer):
        annotation = _add_annotation_via_toolbar(svg_viewer)
        annotation.setSelected(True)
        size_before = annotation.font().pointSize()
        with undoable():
            commands.execute("timeline.score.font_dec")
            assert annotation.font().pointSize() == size_before // 2


class TestWindowLifecycle:
    def test_close_viewer(self, svg_viewer):
        assert svg_viewer.isVisible()
        svg_viewer.close()
        assert not svg_viewer.isVisible()

    def test_reopen_viewer(self, svg_viewer):
        # Mirrors TestViewWindow.test_video_window_reopens_on_show_request in
        # test_windows.py: closing only hides (ViewWidget.closeEvent ignores
        # the event), and the window menu reopens it via WINDOW_UPDATE_REQUEST.
        svg_viewer.close()
        assert not svg_viewer.isVisible()
        post(Post.WINDOW_UPDATE_REQUEST, svg_viewer.id, True)
        assert svg_viewer.isVisible()


class TestNoteInteraction:
    def test_click_note_seeks_playback(self, svg_viewer, tilia_state):
        tilia_state.current_time = 0
        note = _stavenotes(svg_viewer)[1]  # seek_x=100 -> beat 1 -> t=1.0
        view = svg_viewer.view
        pos = view.mapFromScene(note.sceneBoundingRect().center())
        QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        assert tilia_state.current_time == pytest.approx(1.0)

    def test_select_one_note(self, svg_viewer):
        notes = _stavenotes(svg_viewer)
        view = svg_viewer.view
        pos = view.mapFromScene(notes[0].sceneBoundingRect().center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        assert svg_viewer.scene.selectedItems() == [notes[0]]

    def test_select_several_notes(self, svg_viewer):
        # Reading: ctrl-click extends the selection, as for any other
        # QGraphicsScene item -- there is no separate "select all" gesture
        # for stave notes.
        notes = _stavenotes(svg_viewer)
        view = svg_viewer.view
        pos0 = view.mapFromScene(notes[0].sceneBoundingRect().center())
        pos1 = view.mapFromScene(notes[1].sceneBoundingRect().center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos0)
        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            pos1,
        )
        assert set(svg_viewer.scene.selectedItems()) == {notes[0], notes[1]}


class TestZoom:
    @staticmethod
    def _wheel_zoom(view, angle_delta_y: int) -> None:
        center = view.viewport().rect().center()
        event = QWheelEvent(
            QPointF(center),
            QPointF(view.viewport().mapToGlobal(center)),
            QPoint(0, 0),
            QPoint(0, angle_delta_y),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(view.viewport(), event)

    def test_zoom_in(self, svg_viewer):
        view = svg_viewer.view
        scale_before = view.transform().m11()
        self._wheel_zoom(view, 120)
        assert view.transform().m11() > scale_before

    def test_zoom_out(self, svg_viewer):
        view = svg_viewer.view
        scale_before = view.transform().m11()
        self._wheel_zoom(view, -120)
        assert view.transform().m11() < scale_before
