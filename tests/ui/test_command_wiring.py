"""Table-driven wiring tests for release-checklist rows that differ from a
sibling row only by the ROUTE used to reach a command (menu / submenu /
keyboard shortcut / context menu / toolbar button). Behaviour of each
command is tested elsewhere (see the per-kind UI test modules); this module
only asserts, per route:

1. presence  - the action/button/shortcut exists (shortcut strings are
   pinned, so an accidental rebind fails on purpose).
2. firing    - triggering the route runs the expected command.
3. completeness - test_guard_command_coverage requires every command
   reachable from any of: every main-window menu and submenu (File, Edit,
   View, Timelines -- including its Add-timeline and per-kind Import
   submenus -- Help), every timeline-kind toolbar (hierarchy, range,
   harmony, beat, marker, pdf, score, audiowave) and the player toolbar,
   every timeline-level and element-level context-menu class (all kinds),
   and every registered command with a shortcut, to appear somewhere in
   this table. Commands reachable from more than one of those routes (e.g.
   copy: Edit menu + Ctrl+C + several context menus) only need one table
   row -- COVERED_COMMANDS is a flat set, not a route-by-route tally.
   test_guard_no_ambiguous_shortcuts separately checks that no two
   registered shortcuts collide unresolvably.

   NOT_BACKED_BY_COMMAND documents controls that live on one of those
   surfaces but that the guard can't require, because they aren't a
   commands.get_qaction() CommandQAction the way this module's helpers
   (get_command_action/get_command_names) discover routes: a plain
   QAction/QPushButton/QSlider/QCheckBox wired straight to a Python method,
   or -- twice -- a CommandQAction whose command_name doesn't match the
   command its own click handler actually executes. No app code changes
   and no new commands were introduced to close those gaps.

Many rows on the manual release-checklist sheet collapse onto the same
(route, command) pair -- e.g. "paste multiple" vs "paste single", or "delete
one beat" vs "delete several beats" -- since that distinction is a
*behaviour* difference the callback handles, not a different route. Those
rows share one case. Some cases below cover a route that isn't on the sheet
at all, tested here anyway, plus the two completeness guards.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack, contextmanager, nullcontext
from typing import NamedTuple
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

import tilia.ui.commands as commands
from tests.mock import Serve, patch_yes_or_no_dialog
from tests.ui.timelines.interact import press_key
from tests.utils import (
    get_command_action,
    get_command_from_toolbar,
    get_command_names,
    get_main_window_menu,
    get_submenu,
)
from tilia.requests import Get
from tilia.ui.commands import CommandQAction
from tilia.ui.menus import (
    AddTimelinesMenu,
    BeatMenu,
    EditMenu,
    ExportMenu,
    FileMenu,
    HarmonyMenu,
    HelpMenu,
    HierarchyMenu,
    LoadMediaMenu,
    MarkerMenu,
    PdfMenu,
    RangeMenu,
    ScoreMenu,
    TimelinesMenu,
    ViewMenu,
)
from tilia.ui.timelines.base.context_menus import TimelineUIContextMenu
from tilia.ui.timelines.beat.context_menu import (
    BeatContextMenu,
    BeatTimelineUIContextMenu,
)
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.harmony.context_menu import (
    HarmonyContextMenu,
    HarmonyTimelineUIContextMenu,
    ModeContextMenu,
)
from tilia.ui.timelines.harmony.toolbar import HarmonyTimelineToolbar
from tilia.ui.timelines.hierarchy.context_menu import HierarchyContextMenu
from tilia.ui.timelines.hierarchy.toolbar import HierarchyTimelineToolbar
from tilia.ui.timelines.marker.context_menu import (
    MarkerContextMenu,
    MarkerTimelineUIContextMenu,
)
from tilia.ui.timelines.marker.toolbar import MarkerTimelineToolbar
from tilia.ui.timelines.pdf.context_menu import (
    PdfMarkerContextMenu,
    PdfTimelineUIContextMenu,
)
from tilia.ui.timelines.pdf.toolbar import PdfTimelineToolbar
from tilia.ui.timelines.range.context_menu import (
    RangeContextMenu,
    RangeTimelineContextMenu,
)
from tilia.ui.timelines.range.toolbar import RangeTimelineToolbar
from tilia.ui.timelines.score.context_menu import (
    NoteContextMenu,
    ScoreTimelineUIContextMenu,
)
from tilia.ui.windows import WindowKind

pytestmark = pytest.mark.usefixtures("qtui", "tluis")


# --------------------------------------------------------------------------
# Firing helpers
# --------------------------------------------------------------------------


@contextmanager
def spy_command(name: str):
    """Temporarily wrap the callback registered under `name` (see
    commands.execute -> _name_to_callback) with a Mock that still calls
    through. Behaviour is unaffected, but we can assert that a route
    resolved to *this* command specifically -- the thing a copy-pasted
    registration could get wrong.
    """
    original = commands._name_to_callback[name]
    mock = Mock(wraps=original)
    commands._name_to_callback[name] = mock
    try:
        yield mock
    finally:
        # Re-registration would already restore this, but tests can fail
        # before that happens; always leave the real callback in place.
        commands._name_to_callback[name] = original


def fire(action):
    """Trigger a QAction as a click would. Qt's .trigger() is a no-op on a
    disabled action, which would be a false negative for wiring purposes
    (enablement is application *behaviour*, tested elsewhere) -- so force
    it enabled first.
    """
    action.setEnabled(True)
    action.trigger()


@contextmanager
def spy_command_no_call_through(name: str):
    """Like spy_command, but the replacement does NOT call through to the
    real callback -- it only records that the route reached commands.execute
    with this name. Use for commands whose real effect is external (opens a
    browser or the OS file manager, quits the app) or would corrupt this
    module's shared state (qtui/tilia are module-scoped -- see conftest.py
    -- so e.g. really firing file.new would clear timelines every other
    test in this module still depends on).
    """
    original = commands._name_to_callback[name]
    mock = Mock()
    commands._name_to_callback[name] = mock
    try:
        yield mock
    finally:
        commands._name_to_callback[name] = original


@contextmanager
def fire_context(command: str, serves=(), call_through: bool = True):
    """Shared plumbing for routes that need Get.FROM_USER_* prompts served
    before firing, and/or a no-call-through spy. Yields the spy so callers
    can still do `spy.assert_called()` themselves.
    """
    with ExitStack() as stack:
        for request, value in serves:
            stack.enter_context(Serve(request, value))
        spy_cm = (
            spy_command(command)
            if call_through
            else spy_command_no_call_through(command)
        )
        yield stack.enter_context(spy_cm)


# --------------------------------------------------------------------------
# Context-menu routes: instantiate the element's context-menu class
# directly (CLAUDE.md: "Context menus: test both presence AND behavior"),
# find the action, fire it.
# --------------------------------------------------------------------------


class ContextMenuCase(NamedTuple):
    id: str
    kind: str  # "pdf" | "beat" | "hierarchy" | "score"
    command: str
    needs_selection: bool = False
    needs_int_dialog: bool = False
    needs_color_dialog: bool = False


CONTEXT_MENU_CASES = [
    ContextMenuCase("context-menu-pdf-paste", "pdf", "timeline.component.paste"),
    ContextMenuCase(
        "context-menu-pdf-inspect",
        "pdf",
        "timeline.element.inspect",
        needs_selection=True,
    ),
    ContextMenuCase("context-menu-beat-delete", "beat", "timeline.component.delete"),
    ContextMenuCase("context-menu-beat-distribute", "beat", "timeline.beat.distribute"),
    ContextMenuCase(
        "context-menu-hierarchy-copy", "hierarchy", "timeline.component.copy"
    ),
    ContextMenuCase(
        "context-menu-hierarchy-paste", "hierarchy", "timeline.component.paste"
    ),
    # No needs_selection here: NoteUI.on_select() dereferences a `.body`
    # that only exists once the score viewer has actually rendered SVG
    # note glyphs (see the note_ui fixture, which creates the backend
    # component only). That's unrelated to wiring: the spy below records
    # the call at commands.execute's boundary regardless of what
    # on_timeline_element_inspect's own selection guard then does with it.
    ContextMenuCase(
        "context-menu-score-inspect",
        "score",
        "timeline.element.inspect",
    ),
    # --- NEW: same menus as the rows above, remaining items -----------
    ContextMenuCase(
        "context-menu-hierarchy-set-color",
        "hierarchy",
        "timeline.component.set_color",
        needs_color_dialog=True,
    ),
    ContextMenuCase(
        "context-menu-hierarchy-reset-color",
        "hierarchy",
        "timeline.component.reset_color",
    ),
    ContextMenuCase(
        "context-menu-hierarchy-export-audio",
        "hierarchy",
        "timeline.hierarchy.export_audio",
    ),
    ContextMenuCase(
        "context-menu-hierarchy-add-pre-start",
        "hierarchy",
        "timeline.hierarchy.add_pre_start",
    ),
    ContextMenuCase(
        "context-menu-hierarchy-add-post-end",
        "hierarchy",
        "timeline.hierarchy.add_post_end",
    ),
    ContextMenuCase(
        "context-menu-beat-set-measure-number",
        "beat",
        "timeline.beat.set_measure_number",
        needs_int_dialog=True,
    ),
    ContextMenuCase(
        "context-menu-beat-reset-measure-number",
        "beat",
        "timeline.beat.reset_measure_number",
    ),
    ContextMenuCase(
        "context-menu-beat-set-amount-in-measure",
        "beat",
        "timeline.beat.set_amount_in_measure",
        needs_int_dialog=True,
    ),
    # --- NEW: harmony/mode/marker/range element context menus ----------
    # harmony, mode and marker only expose generic commands (inspect/copy/
    # paste/delete/set_color/reset_color) already covered above via other
    # kinds -- test_guard_command_coverage still walks their context
    # menus (below) to prove that, but no new row is needed for them.
    ContextMenuCase(
        "context-menu-range-add-pre-start",
        "range",
        "timeline.range.add_pre_start",
    ),
    ContextMenuCase(
        "context-menu-range-add-post-end",
        "range",
        "timeline.range.add_post_end",
    ),
]

_CONTEXT_MENU_CLASSES = {
    "pdf": PdfMarkerContextMenu,
    "beat": BeatContextMenu,
    "hierarchy": HierarchyContextMenu,
    "score": NoteContextMenu,
    "harmony": HarmonyContextMenu,
    "mode": ModeContextMenu,
    "marker": MarkerContextMenu,
    "range": RangeContextMenu,
}


def _build_element(
    kind,
    pdf_tlui,
    beat_tlui,
    hierarchy_tlui,
    note_ui,
    score_tlui,
    tilia_state,
    harmony_tlui=None,
    marker_tlui=None,
    range_tlui=None,
):
    """Return (tlui, element) for `kind`, with just enough state that the
    element's full, unconditional context-menu item set is present (in
    particular: hierarchy's add_pre_start/add_post_end, which only show up
    with room on both sides -- see HierarchyContextMenu.__init__).

    Deliberately leaves the element unselected and range's add_pre_start/
    add_post_end without a length: both hierarchy's and range's
    on_add_pre_start/on_add_post_end are @with_elements-guarded and return
    False before reaching Get.FROM_USER_FLOAT when nothing is selected, so
    firing them here (see CONTEXT_MENU_CASES above) safely proves wiring
    without needing to serve that prompt.
    """
    if kind == "pdf":
        commands.execute("timeline.pdf.add")
        return pdf_tlui, pdf_tlui[0]
    if kind == "beat":
        commands.execute("timeline.beat.add")
        return beat_tlui, beat_tlui[0]
    if kind == "hierarchy":
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=2)
        return hierarchy_tlui, hierarchy_tlui[0]
    if kind == "harmony":
        # on_add_harmony always prompts Get.FROM_USER_HARMONY_PARAMS once
        # component validation passes (unlike add_pre_start/add_post_end,
        # there's no empty-selection short-circuit before it) -- confirm
        # with no overrides so a real HarmonyUI comes out the other end.
        with Serve(Get.FROM_USER_HARMONY_PARAMS, (True, {})):
            commands.execute("timeline.harmony.add_harmony")
        return harmony_tlui, harmony_tlui.harmonies()[0]
    if kind == "mode":
        with Serve(Get.FROM_USER_MODE_PARAMS, (True, {})):
            commands.execute("timeline.harmony.add_mode")
        return harmony_tlui, harmony_tlui.modes()[0]
    if kind == "marker":
        commands.execute("timeline.marker.add")
        return marker_tlui, marker_tlui[0]
    if kind == "range":
        commands.execute("timeline.range.add_range", start=10, end=20)
        return range_tlui, range_tlui[0]
    assert kind == "score"
    return score_tlui, note_ui


@pytest.mark.parametrize(
    "case", CONTEXT_MENU_CASES, ids=[c.id for c in CONTEXT_MENU_CASES]
)
def test_context_menu_route(
    case,
    pdf_tlui,
    beat_tlui,
    hierarchy_tlui,
    note_ui,
    score_tlui,
    tilia_state,
    harmony_tlui,
    marker_tlui,
    range_tlui,
):
    tlui, element = _build_element(
        case.kind,
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
        harmony_tlui=harmony_tlui,
        marker_tlui=marker_tlui,
        range_tlui=range_tlui,
    )
    menu = _CONTEXT_MENU_CLASSES[case.kind](element)

    action = get_command_action(menu, case.command)
    assert action is not None, (
        f"{case.command!r} not found in {type(menu).__name__} "
        f"(items: {get_command_names(menu)})"
    )

    if case.needs_selection:
        tlui.select_element(element)

    if case.needs_int_dialog:
        dialog_ctx = Serve(Get.FROM_USER_INT, (True, 1))
    elif case.needs_color_dialog:
        dialog_ctx = Serve(Get.FROM_USER_COLOR, (True, QColor("#000000")))
    else:
        dialog_ctx = nullcontext()
    with dialog_ctx, spy_command(case.command) as spy:
        fire(action)
    spy.assert_called()


# --------------------------------------------------------------------------
# Timeline-level context-menu routes: TimelineUIContextMenu subclasses take
# (timeline_ui, x, y) rather than (element,), so CONTEXT_MENU_CASES/
# test_context_menu_route above (built around _build_element's element
# construction) can't express these -- a small parallel table+test instead.
# Only kinds/commands not already covered elsewhere are listed: every
# TimelineUIContextMenu subclass also unconditionally adds Delete/Clear
# (add_default_actions) and, unless overridden, Set name/Set height (base
# `items`) -- see test_guard_command_coverage, which walks all of them.
# --------------------------------------------------------------------------


class TimelineContextMenuCase(NamedTuple):
    id: str
    kind: str  # "hierarchy" | "harmony"
    command: str
    serves: tuple[tuple[Get, object], ...] = ()


TIMELINE_CONTEXT_MENU_CASES = [
    # Hierarchy doesn't override CONTEXT_MENU_CLASS, so it gets the base
    # TimelineUIContextMenu's items unmodified -- the only kind (with
    # audiowave) that still has "Set height" (every other kind's
    # TimelineUIContextMenu subclass drops it; range replaces it with "Set
    # default row height", a plain QAction -- see NOT_BACKED_BY_COMMAND).
    TimelineContextMenuCase(
        "timeline-context-menu-hierarchy-set-name",
        "hierarchy",
        "timeline.set_name",
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    TimelineContextMenuCase(
        "timeline-context-menu-hierarchy-set-height",
        "hierarchy",
        "timeline.set_height",
        serves=((Get.FROM_USER_INT, (False, 0)),),
    ),
    TimelineContextMenuCase(
        "timeline-context-menu-hierarchy-clear",
        "hierarchy",
        "timeline.clear",
        # hierarchy_tlui is fresh/empty here: on_timeline_clear's
        # `if timeline_ui.is_empty: return False` guard fires before the
        # yes/no confirmation, so no dialog is reached. (timeline.delete
        # is already covered by test_manage_timelines_delete.)
    ),
    TimelineContextMenuCase(
        "timeline-context-menu-harmony-show-keys",
        "harmony",
        "timeline.harmony.show_keys",
    ),
    TimelineContextMenuCase(
        "timeline-context-menu-harmony-hide-keys",
        "harmony",
        "timeline.harmony.hide_keys",
    ),
]

_TIMELINE_CONTEXT_MENU_CLASSES = {
    "hierarchy": TimelineUIContextMenu,
    "harmony": HarmonyTimelineUIContextMenu,
}


@pytest.mark.parametrize(
    "case",
    TIMELINE_CONTEXT_MENU_CASES,
    ids=[c.id for c in TIMELINE_CONTEXT_MENU_CASES],
)
def test_timeline_context_menu_route(case, hierarchy_tlui, harmony_tlui):
    tlui = {"hierarchy": hierarchy_tlui, "harmony": harmony_tlui}[case.kind]
    menu = _TIMELINE_CONTEXT_MENU_CLASSES[case.kind](tlui, 0, 0)

    action = get_command_action(menu, case.command)
    assert action is not None, (
        f"{case.command!r} not found in {type(menu).__name__} "
        f"(items: {get_command_names(menu)})"
    )

    with fire_context(case.command, case.serves) as spy:
        fire(action)
    spy.assert_called()


# --------------------------------------------------------------------------
# Keyboard-shortcut routes (main-window scoped: Ctrl+C/V, Ctrl+Shift+V, g).
# Shortcut strings are pinned via QKeySequence equality.
# --------------------------------------------------------------------------


class ShortcutCase(NamedTuple):
    id: str
    key: str
    modifier: Qt.KeyboardModifier
    command: str
    shortcut_text: str


SHORTCUT_CASES = [
    ShortcutCase(
        "shortcut-paste",
        "v",
        Qt.KeyboardModifier.ControlModifier,
        "timeline.component.paste",
        "Ctrl+V",
    ),
    ShortcutCase(
        "shortcut-copy",
        "c",
        Qt.KeyboardModifier.ControlModifier,
        "timeline.component.copy",
        "Ctrl+C",
    ),
    ShortcutCase(
        "shortcut-paste-complete",
        "v",
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "timeline.component.paste_complete",
        "Ctrl+Shift+V",
    ),
    ShortcutCase(
        "shortcut-group",
        "g",
        Qt.KeyboardModifier.NoModifier,
        "timeline.hierarchy.group",
        "g",
    ),
]


@pytest.mark.parametrize("case", SHORTCUT_CASES, ids=[c.id for c in SHORTCUT_CASES])
def test_shortcut_route(case, hierarchy_tlui):
    action = commands.get_qaction(case.command)
    assert action.shortcut() == QKeySequence(case.shortcut_text)

    # A selected hierarchy element gives every one of these commands a
    # valid target (copy/paste/paste_complete/group all act on selection).
    commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
    hierarchy_tlui.select_element(hierarchy_tlui[0])

    action.setEnabled(True)
    with spy_command(case.command) as spy:
        press_key(case.key, modifier=case.modifier)
    spy.assert_called()


def test_shortcut_increase_level(hierarchy_tlui):
    """Ctrl+Up has no QAction shortcut. increase_level/decrease_level are
    dispatched from TimelineView.keyPressEvent via
    Post.TIMELINE_KEY_PRESS_CTRL_UP/DOWN (see hierarchy/timeline.py
    register_commands: attaching them to the QAction as well would trigger
    Qt's "Ambiguous shortcut overload"). There is no separate static
    structure to assert "presence" against, so presence and firing are
    asserted together by sending the real key event to the timeline view.
    """
    commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
    hierarchy_tlui.select_element(hierarchy_tlui[0])

    with spy_command("timeline.hierarchy.increase_level") as spy:
        QTest.keyClick(
            hierarchy_tlui.view, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier
        )
    spy.assert_called()


RANGE_CTRL_ARROW_CASES = [
    (
        "shortcut-range-move-to-row-above",
        Qt.Key.Key_Up,
        "timeline.range.move_to_row_above",
    ),
    (
        "shortcut-range-move-to-row-below",
        Qt.Key.Key_Down,
        "timeline.range.move_to_row_below",
    ),
]


@pytest.mark.parametrize(
    "test_id,key,command",
    RANGE_CTRL_ARROW_CASES,
    ids=[c[0] for c in RANGE_CTRL_ARROW_CASES],
)
def test_shortcut_range_move_to_row(test_id, key, command, range_tlui):
    """Same mechanism as test_shortcut_increase_level above, but for
    range: TimelineUIs.on_ctrl_arrow_press dispatches a Ctrl+Up/Down key
    event to every *kind* that ACCEPTS_VERTICAL_ARROWS (not just the
    "current"/focused one -- see on_ctrl_arrow_press's seen_kinds loop), so
    range's move_to_row_above/below fire from the same global key event
    regardless of which view it was sent to. Like increase/decrease_level,
    neither has a QAction shortcut (same "Ambiguous shortcut" reason), so
    this is the only way to assert presence+firing for them; RangeContextMenu
    only shows them with >= 2 rows and a target that isn't in the first/
    last row, a state test_guard_command_coverage's single-row element
    doesn't reach either (see its docstring).
    """
    with spy_command(command) as spy:
        QTest.keyClick(range_tlui.view, key, Qt.KeyboardModifier.ControlModifier)
    spy.assert_called()


# --------------------------------------------------------------------------
# Main-window menu routes (Edit / View / Timelines).
# --------------------------------------------------------------------------


class MenuCase(NamedTuple):
    id: str
    menu_name: str
    command: str
    submenu_path: tuple[str, ...] = ()
    serves: tuple[tuple[Get, object], ...] = ()
    call_through: bool = True


MENU_CASES = [
    MenuCase("edit-menu-paste", "Edit", "timeline.component.paste"),
    MenuCase("menu-bar-zoom-in", "View", "view.zoom.in"),
    MenuCase("menu-bar-zoom-out", "View", "view.zoom.out"),
    MenuCase("edit-menu-undo", "Edit", "edit.undo"),
    MenuCase("edit-menu-redo", "Edit", "edit.redo"),
    MenuCase("edit-menu-open-settings", "Edit", "window.open.settings"),
    MenuCase(
        "timelines-menu-open-manage-timelines",
        "Timelines",
        "window.open.manage_timelines",
    ),
    # --- NEW: rest of the File menu, including its submenus ------------
    MenuCase(
        "file-menu-new",
        "File",
        "file.new",
        call_through=False,
        # on_request_new_file -> on_close_modified_file always ends in
        # post(APP_CLEAR)/post(APP_SETUP_FILE) once the save-changes
        # prompt is answered (unlike file.open below, there's no later
        # "cancel" point) -- qtui/tilia are module-scoped (conftest.py),
        # so that would wipe every timeline other tests in this module
        # still depend on.
    ),
    MenuCase(
        "file-menu-open",
        "File",
        "file.open",
        serves=(
            (Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            (Get.FROM_USER_TILIA_FILE_PATH, (False, "")),
        ),
        # First prompt (is_file_modified() is almost certainly True this
        # deep into the module): proceed without saving. Second prompt:
        # cancel the path picker -- on_open returns before on_clear(), so
        # nothing is actually replaced.
    ),
    MenuCase(
        "file-menu-save",
        "File",
        "file.save",
        serves=((Get.FROM_USER_SAVE_PATH_TILIA, (False, "")),),
        # No file_path yet in this module's shared session, so
        # on_save_request delegates to on_save_as_request; cancelling the
        # path prompt means nothing is written to disk.
    ),
    MenuCase(
        "file-menu-save-as",
        "File",
        "file.save_as",
        serves=((Get.FROM_USER_SAVE_PATH_TILIA, (False, "")),),
    ),
    MenuCase(
        "file-menu-export-json",
        "File",
        "file.export.json",
        submenu_path=("Export...",),
        serves=((Get.FROM_USER_EXPORT_PATH, (False, "")),),
    ),
    MenuCase(
        "file-menu-export-img",
        "File",
        "file.export.img",
        submenu_path=("Export...",),
        serves=((Get.FROM_USER_EXPORT_PATH, (False, "")),),
    ),
    MenuCase(
        "file-menu-load-media-local",
        "File",
        "media.load.local",
        submenu_path=("Load media",),
        serves=((Get.FROM_USER_MEDIA_PATH, (False, "")),),
    ),
    MenuCase(
        "file-menu-load-media-youtube",
        "File",
        "media.load.youtube",
        submenu_path=("Load media",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase("file-menu-open-metadata", "File", "window.open.metadata"),
    MenuCase(
        "file-menu-open-autosaves-folder",
        "File",
        "folder.open.autosaves",
        call_through=False,  # opens a real OS file-manager window
    ),
    # --- NEW: rest of the Timelines menu (clear all, Add submenu, and
    # every per-kind Import submenu) -------------------------------------
    MenuCase(
        "timelines-menu-clear-all",
        "Timelines",
        "timelines.clear_all",
        call_through=False,
        # For real, clears every clearable timeline in the module-shared
        # collection -- would corrupt fixtures other tests in this module
        # still rely on (same reasoning as file.new above).
    ),
    MenuCase(
        "timelines-add-hierarchy",
        "Timelines",
        "timelines.add.hierarchy",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-marker",
        "Timelines",
        "timelines.add.marker",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-beat",
        "Timelines",
        "timelines.add.beat",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-harmony",
        "Timelines",
        "timelines.add.harmony",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-pdf",
        "Timelines",
        "timelines.add.pdf",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-range",
        "Timelines",
        "timelines.add.range",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-score",
        "Timelines",
        "timelines.add.score",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-add-audiowave",
        "Timelines",
        "timelines.add.audiowave",
        submenu_path=("Add",),
        serves=((Get.FROM_USER_STRING, (False, "")),),
    ),
    MenuCase(
        "timelines-import-hierarchy",
        "Timelines",
        "timelines.import.hierarchy",
        submenu_path=("Hierarchy",),
        call_through=False,
        # Whether _on_import_to_timeline reaches "choose a timeline" (>1
        # existing timeline of this kind), an overwrite confirmation
        # (exactly 1, non-empty), or a real per-kind file picker (exactly
        # 1, empty) depends on how many timelines of this kind earlier
        # tests in this module have already created -- order-sensitive,
        # and every branch but "none exist yet" can reach a blocking
        # dialog.
    ),
    MenuCase(
        "timelines-import-marker",
        "Timelines",
        "timelines.import.marker",
        submenu_path=("Marker",),
        call_through=False,
    ),
    MenuCase(
        "timelines-import-beat",
        "Timelines",
        "timelines.import.beat",
        submenu_path=("Beat",),
        call_through=False,
    ),
    MenuCase(
        "timelines-import-harmony",
        "Timelines",
        "timelines.import.harmony",
        submenu_path=("Harmony",),
        call_through=False,
    ),
    MenuCase(
        "timelines-import-pdf",
        "Timelines",
        "timelines.import.pdf",
        submenu_path=("PDF",),
        call_through=False,
    ),
    MenuCase(
        "timelines-import-range",
        "Timelines",
        "timelines.import.range",
        submenu_path=("Range",),
        call_through=False,
    ),
    MenuCase(
        "timelines-import-score",
        "Timelines",
        "timelines.import.score",
        submenu_path=("Score",),
        call_through=False,
    ),
    MenuCase(
        "timelines-beat-menu-fill",
        "Timelines",
        "timeline.beat.fill",
        submenu_path=("Beat",),
        serves=((Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, (False, None)),),
    ),
    # --- NEW: Help menu --------------------------------------------------
    MenuCase("help-menu-about", "Help", "window.open.about"),
    MenuCase(
        "help-menu-website",
        "Help",
        "open_website_help",
        call_through=False,  # opens a real web browser
    ),
    MenuCase(
        "help-menu-check-for-updates",
        "Help",
        "help.check_for_updates",
        call_through=False,  # checks for updates over the network
    ),
    # Not offered on Windows, where Velopack's Add/Remove Programs entry
    # uninstalls TiLiA (see tilia/ui/menus.py::_help_menu_items).
    *(
        [
            MenuCase(
                "help-menu-uninstall",
                "Help",
                "help.uninstall",
                call_through=False,  # would really uninstall TiLiA
            )
        ]
        if sys.platform != "win32"
        else []
    ),
]


@pytest.mark.parametrize("case", MENU_CASES, ids=[c.id for c in MENU_CASES])
def test_main_window_menu_route(case, qtui):
    menu = get_main_window_menu(qtui, case.menu_name)
    for submenu_name in case.submenu_path:
        menu = get_submenu(menu, submenu_name)
        assert menu is not None, (
            f"{submenu_name!r} submenu not found under {case.menu_name!r} "
            f"(path to {case.command!r})"
        )

    action = get_command_action(menu, case.command)
    assert action is not None, (
        f"{case.command!r} not found in {case.menu_name!r} menu "
        f"(items: {get_command_names(menu)})"
    )

    with fire_context(case.command, case.serves, case.call_through) as spy:
        fire(action)
    spy.assert_called()


# --------------------------------------------------------------------------
# Toolbar-button routes (per-timeline-kind toolbar).
# --------------------------------------------------------------------------

TOOLBAR_CASES = [
    ("toolbar-hierarchy-split", "timeline.hierarchy.split"),
    ("toolbar-hierarchy-merge", "timeline.hierarchy.merge"),
    ("toolbar-hierarchy-decrease-level", "timeline.hierarchy.decrease_level"),
    ("toolbar-hierarchy-create-child", "timeline.hierarchy.create_child"),
]


@pytest.mark.parametrize(
    "test_id,command", TOOLBAR_CASES, ids=[c[0] for c in TOOLBAR_CASES]
)
def test_hierarchy_toolbar_route(test_id, command, hierarchy_tlui):
    # Two adjacent level-1 elements: a valid target for split/merge/
    # decrease_level/create_child regardless of which one this case fires.
    commands.execute("timeline.hierarchy.add", start=0, end=1, level=2)
    commands.execute("timeline.hierarchy.add", start=1, end=2, level=2)
    hierarchy_tlui.select_element(hierarchy_tlui[0])
    hierarchy_tlui.select_element(hierarchy_tlui[1])

    action = get_command_from_toolbar(hierarchy_tlui, command)
    assert action is not None, f"{command!r} not found on HierarchyTimelineToolbar"

    with spy_command(command) as spy:
        fire(action)
    spy.assert_called()


# --------------------------------------------------------------------------
# Toolbar-button routes for the remaining timeline-kind toolbars, plus the
# player toolbar. Unlike HierarchyTimelineToolbar above (which needs two
# selected, adjacent elements so split/merge/decrease_level/create_child
# all have a valid target), every command exercised here is safe to fire
# with nothing selected: each callback is @with_elements/@with_row-guarded
# (returns False on an empty selection/row before doing anything real) or,
# for the "add" commands, only reads Get.SELECTED_TIME or falls back to a
# default target. Firing still proves the wiring either way -- the spy
# records the call regardless of what the guarded body then does with it.
# --------------------------------------------------------------------------


def _find_toolbar_command_action(toolbar, command_name: str):
    """Like get_command_action, but also looks inside a QToolButton's own
    popup menu. RangeTimelineToolbar groups related commands (e.g. join/
    merge ranges) under one dropdown button added via QToolBar.addWidget()
    -- get_command_action's QWidgetAction branch expects that widget to be
    a *container* of QToolButtons (ribbon-style), not a QToolButton itself,
    so it can't see a command that's only in that button's own .menu().
    """
    action = get_command_action(toolbar, command_name)
    if action is not None:
        return action
    for button in toolbar.findChildren(QToolButton):
        menu = button.menu()
        if menu is None:
            continue
        for candidate in menu.actions():
            if (
                isinstance(candidate, CommandQAction)
                and candidate.command_name == command_name
            ):
                return candidate
    return None


def _toolbar_command_names(toolbar) -> set[str]:
    """get_command_names(toolbar), plus commands nested in a QToolButton's
    own popup menu (see _find_toolbar_command_action). Used by the coverage
    guard so RangeTimelineToolbar's dropdown-grouped commands are actually
    required, not a silent blind spot.
    """
    names = set(get_command_names(toolbar))
    for button in toolbar.findChildren(QToolButton):
        menu = button.menu()
        if menu is not None:
            names |= set(get_command_names(menu))
    return names


class ToolbarCase(NamedTuple):
    id: str
    kind: str  # "beat" | "harmony" | "marker" | "pdf" | "range" | "player"
    command: str
    serves: tuple[tuple[Get, object], ...] = ()


TOOLBAR_ROUTE_CASES = [
    ToolbarCase("toolbar-beat-add", "beat", "timeline.beat.add"),
    ToolbarCase("toolbar-beat-distribute", "beat", "timeline.beat.distribute"),
    ToolbarCase(
        "toolbar-beat-set-measure-number",
        "beat",
        "timeline.beat.set_measure_number",
    ),
    ToolbarCase(
        "toolbar-beat-reset-measure-number",
        "beat",
        "timeline.beat.reset_measure_number",
    ),
    ToolbarCase(
        "toolbar-harmony-add-harmony",
        "harmony",
        "timeline.harmony.add_harmony",
        # Unlike hierarchy/range's add_pre_start/add_post_end, on_add_
        # harmony has no empty-selection short-circuit before Get.FROM_
        # USER_HARMONY_PARAMS -- it prompts unconditionally once component
        # validation passes.
        serves=((Get.FROM_USER_HARMONY_PARAMS, (False, {})),),
    ),
    ToolbarCase(
        "toolbar-harmony-add-mode",
        "harmony",
        "timeline.harmony.add_mode",
        serves=((Get.FROM_USER_MODE_PARAMS, (False, {})),),
    ),
    ToolbarCase(
        "toolbar-harmony-display-as-roman",
        "harmony",
        "timeline.harmony.component.display_as_roman",
    ),
    ToolbarCase(
        "toolbar-harmony-display-as-letter",
        "harmony",
        "timeline.harmony.component.display_as_letter",
    ),
    ToolbarCase("toolbar-marker-add", "marker", "timeline.marker.add"),
    ToolbarCase("toolbar-pdf-add", "pdf", "timeline.pdf.add"),
    ToolbarCase("toolbar-range-add-range", "range", "timeline.range.add_range"),
    ToolbarCase("toolbar-range-join-ranges", "range", "timeline.range.join_ranges"),
    ToolbarCase("toolbar-range-merge-ranges", "range", "timeline.range.merge_ranges"),
    ToolbarCase(
        "toolbar-range-separate-ranges", "range", "timeline.range.separate_ranges"
    ),
    ToolbarCase("toolbar-range-split-range", "range", "timeline.range.split_range"),
    ToolbarCase("toolbar-range-add-row-above", "range", "timeline.range.add_row_above"),
    ToolbarCase("toolbar-range-add-row-below", "range", "timeline.range.add_row_below"),
    ToolbarCase("toolbar-player-stop", "player", "media.stop"),
]

_TOOLBAR_CLASSES = {
    "beat": BeatTimelineToolbar,
    "harmony": HarmonyTimelineToolbar,
    "marker": MarkerTimelineToolbar,
    "pdf": PdfTimelineToolbar,
    "range": RangeTimelineToolbar,
}


@pytest.mark.parametrize(
    "case", TOOLBAR_ROUTE_CASES, ids=[c.id for c in TOOLBAR_ROUTE_CASES]
)
def test_toolbar_route(
    case, qtui, beat_tlui, harmony_tlui, marker_tlui, pdf_tlui, range_tlui
):
    # Every *_tlui fixture above is requested (not just the one `case.kind`
    # needs) so TimelineSelector.FIRST/Get.SELECTED_TIME-based callbacks
    # always have a timeline of that kind to resolve to, regardless of
    # parametrize order -- same reasoning as test_context_menu_route's
    # _build_element fixture list.
    toolbar = (
        qtui.player_toolbar if case.kind == "player" else _TOOLBAR_CLASSES[case.kind]()
    )
    action = _find_toolbar_command_action(toolbar, case.command)
    assert action is not None, f"{case.command!r} not found on {case.kind!r} toolbar"

    with fire_context(case.command, case.serves) as spy:
        fire(action)
    spy.assert_called()


# --------------------------------------------------------------------------
# Manage Timelines window (a plain QPushButton, not a QAction/shortcut).
# --------------------------------------------------------------------------


def test_manage_timelines_delete(hierarchy_tlui, qtui):
    commands.execute("window.open.manage_timelines")
    dialog = qtui._windows[WindowKind.MANAGE_TIMELINES]
    list_widget = dialog.list_widget

    for i in range(list_widget.count()):
        if list_widget.item(i).timeline_ui == hierarchy_tlui:
            list_widget.setCurrentRow(i)
            break
    else:
        pytest.fail("hierarchy timeline not listed in Manage Timelines")

    assert dialog.delete_button.isEnabled()
    with patch_yes_or_no_dialog(True), spy_command("timeline.delete") as spy:
        QTest.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)
    spy.assert_called()


# --------------------------------------------------------------------------
# Score viewer: a per-instance toolbar (QToolButtons in a QVBoxLayout, not
# a QToolBar/QMenu, so get_command_action doesn't apply directly) plus two
# real QAction shortcuts scoped to the viewer widget.
# --------------------------------------------------------------------------


def _find_toolbutton(svg_viewer, command_name):
    for button in svg_viewer.findChildren(QToolButton):
        action = button.defaultAction()
        if isinstance(action, CommandQAction) and action.command_name == command_name:
            return button
    return None


SCORE_VIEWER_TOOLBAR_CASES = [
    ("score-viewer-add", "timeline.score.add"),
    ("score-viewer-delete", "timeline.score.delete"),
    ("score-viewer-edit", "timeline.score.edit"),
]


@pytest.mark.parametrize(
    "test_id,command",
    SCORE_VIEWER_TOOLBAR_CASES,
    ids=[c[0] for c in SCORE_VIEWER_TOOLBAR_CASES],
)
def test_score_viewer_toolbar_route(test_id, command, score_tlui):
    svg_viewer = score_tlui.get_or_create_svg_view()
    button = _find_toolbutton(svg_viewer, command)
    assert button is not None, f"{command!r} not found on score viewer toolbar"

    with spy_command(command) as spy:
        button.defaultAction().setEnabled(True)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    spy.assert_called()


SCORE_VIEWER_SHORTCUT_CASES = [
    ("score-viewer-font-inc", "timeline.score.font_inc", "Shift+Up"),
    ("score-viewer-font-dec", "timeline.score.font_dec", "Shift+Down"),
]


@pytest.mark.parametrize(
    "test_id,command,shortcut_text",
    SCORE_VIEWER_SHORTCUT_CASES,
    ids=[c[0] for c in SCORE_VIEWER_SHORTCUT_CASES],
)
def test_score_viewer_shortcut_route(test_id, command, shortcut_text, score_tlui):
    action = commands.get_qaction(command)
    assert action.shortcut() == QKeySequence(shortcut_text)

    svg_viewer = score_tlui.get_or_create_svg_view()
    # The viewer is built lazily (get_or_create_svg_view) and, unlike
    # ManageTimelines/other windows, isn't shown or docked as a side
    # effect -- an invisible/windowless widget never becomes Qt's "active
    # window", so its WindowShortcut-context action never activates.
    svg_viewer.show()
    QApplication.processEvents()

    key = shortcut_text.rsplit("+", 1)[-1]
    action.setEnabled(True)
    with spy_command(command) as spy:
        QTest.keyClick(
            svg_viewer, getattr(Qt.Key, f"Key_{key}"), Qt.KeyboardModifier.ShiftModifier
        )
    spy.assert_called()


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------

# Controls that live on a surface test_guard_command_coverage walks (a
# main-window menu/submenu, a timeline-kind/player toolbar, or a context
# menu) but that aren't a commands.get_qaction() CommandQAction the way
# get_command_action/get_command_names/_find_toolbar_command_action look
# for a route -- either a plain QAction/QPushButton/QSlider/QCheckBox wired
# straight to a Python method (never shows up in get_command_names() at
# all, so listing it here is documentation, not something the guard
# actually needs subtracted), or -- the two "timeline.move_*" entries -- a
# CommandQAction that *does* show up, but under a command_name that doesn't
# match what its own click handler executes (so this module's
# find-by-name-then-spy-that-name pattern can't line the two up without
# inventing a mismatched-name special case). No app code changes and no
# new commands were added to close any of these; the guard instead
# subtracts these keys from `required`.
NOT_BACKED_BY_COMMAND = {
    "timeline.move_up": (
        "TimelineUIContextMenu.check_move_up builds its own CommandQAction "
        "labelled 'timeline.move_up', wired to a closure that calls "
        "commands.execute('timelines.permute_ordinal', ...) instead."
    ),
    "timeline.move_down": (
        "Same as timeline.move_up (check_move_down), for the neighbour below."
    ),
    "RangeTimelineContextMenu: Set default row height": (
        "Plain QAction (not CommandQAction), wired to a lambda that calls "
        "commands.execute('timeline.range.set_row_height') directly."
    ),
    "RangeTimelineContextMenu: row actions": (
        "_add_row_actions()'s Add row above/below, Rename row, Set/Reset "
        "row color, Set/Reset row height and Move row up/down items are "
        "all plain QAction wired to per-instance closures (on_add_row_"
        "above, on_rename_row, ...), not CommandQAction."
    ),
    "RangeTimelineToolbar: split-mode toggle": (
        "A plain checkable QToolButton (_build_split_mode_button), wired "
        "to _on_split_mode_toggled(), which calls commands.execute(...) "
        "by name directly -- not a CommandQAction."
    ),
    "ViewMenu: per-window checkable items": (
        "ViewMenu._get_action builds a plain checkable QAction per open "
        "window, wired to post(Post.WINDOW_UPDATE_REQUEST, ...) -- no "
        "command at all, and the item set changes as windows open/close."
    ),
    "FileMenu > Open Recent file: per-file items": (
        "RecentFilesMenu._get_action builds a plain QAction per recent "
        "file, wired to commands.execute('file.open', file) directly -- "
        "not CommandQAction, and the item set depends on user history."
    ),
    "PlayerToolbar: toggle play/pause": (
        "Plain checkable QAction (play_toggle_action), wired to "
        "commands.execute('media.toggle_play', checked). Its Space "
        "shortcut (player.py) is set directly on that QAction too, so it "
        "isn't in commands._shortcut_to_commands either."
    ),
    "PlayerToolbar: volume slider": (
        "Plain QSlider (volume_slider), wired via valueChanged to "
        "commands.execute('media.volume.change', value)."
    ),
    "PlayerToolbar: mute toggle": (
        "Plain checkable QAction (volume_toggle_action), wired to "
        "commands.execute('media.volume.mute', checked)."
    ),
    "PlayerToolbar: playback rate spinbox": (
        "Plain QDoubleSpinBox (playback_rate_spinbox), wired via "
        "valueChanged to commands.execute('media.playback_rate.try', rate)."
    ),
    "PlayerToolbar: loop toggle": (
        "Plain QAction with no backing command at all -- wired straight "
        "to post(Post.PLAYER_TOGGLE_LOOP, checked)."
    ),
}

# Every command name this module already fires and asserts on, above.
COVERED_COMMANDS = (
    {c.command for c in CONTEXT_MENU_CASES}
    | {c.command for c in TIMELINE_CONTEXT_MENU_CASES}
    | {c.command for c in SHORTCUT_CASES}
    | {c.command for c in MENU_CASES}
    | {command for _, command in TOOLBAR_CASES}
    | {c.command for c in TOOLBAR_ROUTE_CASES}
    | {command for _, command in SCORE_VIEWER_TOOLBAR_CASES}
    | {command for _, command, _ in SCORE_VIEWER_SHORTCUT_CASES}
    | {command for _, _, command in RANGE_CTRL_ARROW_CASES}
    | {"timeline.hierarchy.increase_level", "timeline.delete"}
)


def test_guard_command_coverage(
    pdf_tlui,
    beat_tlui,
    hierarchy_tlui,
    note_ui,
    score_tlui,
    tilia_state,
    harmony_tlui,
    marker_tlui,
    range_tlui,
    audiowave_tlui,
    qtui,
):
    """Every command reachable from a main-window menu/submenu, a
    timeline-kind or player toolbar, a timeline-level or element-level
    context menu (any kind), or carrying a registered keyboard shortcut,
    must appear in COVERED_COMMANDS above (minus NOT_BACKED_BY_COMMAND). A
    future command added to any of these surfaces without a matching table
    row makes this fail and names the gap.
    """
    required: set[str] = set()

    # Every main-window menu and submenu.
    required |= set(get_command_names(FileMenu()))
    required |= set(get_command_names(ExportMenu()))
    required |= set(get_command_names(LoadMediaMenu()))
    required |= set(get_command_names(EditMenu()))
    required |= set(get_command_names(ViewMenu()))
    required |= set(get_command_names(TimelinesMenu()))
    required |= set(get_command_names(AddTimelinesMenu()))
    required |= set(get_command_names(HierarchyMenu()))
    required |= set(get_command_names(MarkerMenu()))
    required |= set(get_command_names(BeatMenu()))
    required |= set(get_command_names(HarmonyMenu()))
    required |= set(get_command_names(PdfMenu()))
    required |= set(get_command_names(RangeMenu()))
    required |= set(get_command_names(ScoreMenu()))
    required |= set(get_command_names(HelpMenu()))

    # Element-level context menus, every kind.
    tlui, pdf_element = _build_element(
        "pdf", pdf_tlui, beat_tlui, hierarchy_tlui, note_ui, score_tlui, tilia_state
    )
    required |= set(get_command_names(PdfMarkerContextMenu(pdf_element)))

    _, beat_element = _build_element(
        "beat", pdf_tlui, beat_tlui, hierarchy_tlui, note_ui, score_tlui, tilia_state
    )
    required |= set(get_command_names(BeatContextMenu(beat_element)))

    _, hierarchy_element = _build_element(
        "hierarchy",
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
    )
    required |= set(get_command_names(HierarchyContextMenu(hierarchy_element)))
    required |= set(get_command_names(HierarchyTimelineToolbar()))

    required |= set(get_command_names(NoteContextMenu(note_ui)))

    _, harmony_element = _build_element(
        "harmony",
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
        harmony_tlui=harmony_tlui,
    )
    required |= set(get_command_names(HarmonyContextMenu(harmony_element)))

    _, mode_element = _build_element(
        "mode",
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
        harmony_tlui=harmony_tlui,
    )
    required |= set(get_command_names(ModeContextMenu(mode_element)))

    _, marker_element = _build_element(
        "marker",
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
        marker_tlui=marker_tlui,
    )
    required |= set(get_command_names(MarkerContextMenu(marker_element)))

    _, range_element = _build_element(
        "range",
        pdf_tlui,
        beat_tlui,
        hierarchy_tlui,
        note_ui,
        score_tlui,
        tilia_state,
        range_tlui=range_tlui,
    )
    required |= set(get_command_names(RangeContextMenu(range_element)))

    # Timeline-level context menus, every kind. Hierarchy and audiowave use
    # the base TimelineUIContextMenu directly (the only two still exposing
    # "Set height" -- see TIMELINE_CONTEXT_MENU_CASES). BeatTimelineUIContext
    # Menu and PdfTimelineUIContextMenu declare their one item as
    # `(MenuItemKind, "timeline.set_name")` -- a typo for
    # `MenuItemKind.COMMAND` (maintainer decision, left alone). TiliaMenu.
    # add_item's `if kind == SEPARATOR / elif kind == SUBMENU / else
    # add_action` still takes the `else` branch for the bare `MenuItemKind`
    # class -- it's neither member -- so the action is added exactly as it
    # would be if written correctly; discovery below is unaffected.
    required |= set(get_command_names(TimelineUIContextMenu(hierarchy_tlui, 0, 0)))
    required |= set(get_command_names(TimelineUIContextMenu(audiowave_tlui, 0, 0)))
    required |= set(get_command_names(BeatTimelineUIContextMenu(beat_tlui, 0, 0)))
    required |= set(get_command_names(MarkerTimelineUIContextMenu(marker_tlui, 0, 0)))
    required |= set(get_command_names(PdfTimelineUIContextMenu(pdf_tlui, 0, 0)))
    required |= set(get_command_names(ScoreTimelineUIContextMenu(score_tlui, 0, 0)))
    required |= set(get_command_names(HarmonyTimelineUIContextMenu(harmony_tlui, 0, 0)))
    required |= set(get_command_names(RangeTimelineContextMenu(range_tlui, 0, 0)))

    # Every timeline-kind toolbar, plus the player toolbar.
    required |= _toolbar_command_names(BeatTimelineToolbar())
    required |= _toolbar_command_names(HarmonyTimelineToolbar())
    required |= _toolbar_command_names(MarkerTimelineToolbar())
    required |= _toolbar_command_names(PdfTimelineToolbar())
    required |= _toolbar_command_names(RangeTimelineToolbar())
    required |= _toolbar_command_names(qtui.player_toolbar)

    svg_viewer = score_tlui.get_or_create_svg_view()
    for button in svg_viewer.findChildren(QToolButton):
        action = button.defaultAction()
        if isinstance(action, CommandQAction):
            required.add(action.command_name)

    # Every registered command with a shortcut. commands._shortcut_to_
    # commands is populated at commands.register() time and, unlike a
    # shared-shortcut command's own QAction.shortcut(), still lists its
    # name after setup_shortcuts() strips the individual QAction binding
    # in favour of one shared QShortcut (see commands.py).
    for names in commands._shortcut_to_commands.values():
        required |= set(names)

    required -= set(NOT_BACKED_BY_COMMAND)

    missing = required - COVERED_COMMANDS
    assert not missing, f"commands missing a wiring test: {sorted(missing)}"


def test_guard_no_ambiguous_shortcuts():
    """No two actions active in the same window may share a live Qt
    shortcut -- Qt silently ignores the ambiguous one. The app already
    resolves *known* cross-kind collisions (e.g. hierarchy vs range both
    binding "s" to split) into a single QShortcut dispatched by
    TimelineUIs.on_shared_shortcut_fired, which itself refuses to dispatch
    (AMBIGUOUS_SHORTCUT) unless every bound name is `timeline.<kind>.*`
    with a distinct <kind>. This mirrors that same validation statically,
    across every registered shortcut, so a genuinely new collision fails
    here instead of silently misfiring at runtime.
    """
    for shortcut, names in commands._shortcut_to_commands.items():
        if len(names) <= 1:
            continue
        seen_kind_prefixes: dict[str, str] = {}
        for name in names:
            assert name.startswith("timeline."), (
                f"Shortcut {shortcut!r} bound to a non-timeline command "
                f"among a collision: {names}"
            )
            kind_prefix = ".".join(name.split(".", 2)[:2])
            assert kind_prefix not in seen_kind_prefixes, (
                f"Shortcut {shortcut!r} bound to two commands of the same "
                f"kind (unresolvable -- no 'most recently clicked' "
                f"tiebreaker applies): {names}"
            )
            seen_kind_prefixes[kind_prefix] = name
