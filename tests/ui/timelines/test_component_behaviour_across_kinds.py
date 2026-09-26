"""Cross-kind component behaviour contract.

The marker timeline has thorough coverage for copy/paste, color and the
inspector (see `tests/ui/timelines/marker/test_marker_timeline_ui.py`, the
gold reference). This module runs the same user-level checks for every other
component kind that offers the operation, parametrized over kinds, so a gap
in one kind's implementation shows up as a single failing/xfail parameter
instead of silently missing coverage.

Kinds and what they offer (see `tilia.timelines.base.timeline.TimelineFlag`
and each kind's `*TimelineUI.paste_*` methods):

- marker, range: color + copy/paste into element and into timeline (full).
- hierarchy: color; copy/paste but only *single* into a *selected element*
  (`HierarchyTimelineUI` defines `paste_single_into_selected_elements` only
  -- no `paste_multiple_into_selected_elements` and no `paste_*_into_timeline`
  at all via the plain "paste" command; the richer nested-paste story lives
  behind the separate "paste complete" command, out of scope here).
- pdf, harmony, mode: copy/paste into element and into timeline (full); no
  color (not in `TimelineFlag.COMPONENTS_COLORED`).
- beat: copy/paste but only *into timeline* (`BeatTimelineUI` defines only
  `paste_single_into_timeline`/`paste_multiple_into_timeline` -- consistent
  with beats having no copyable value attributes, `DEFAULT_COPY_ATTRIBUTES
  .values == []`); no color.

Inspector open/close (Enter/Escape) is generic (`tilia/ui/qtui.py`,
`tilia/ui/windows/inspect.py`) and offered by every kind.
"""

from unittest.mock import patch

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog

from tests.mock import Serve
from tests.ui.timelines.beat.interact import click_beat_ui
from tests.ui.timelines.harmony.interact import click_harmony_ui, click_mode_ui
from tests.ui.timelines.interact import (
    click_timeline_ui,
    click_timeline_ui_element_body,
    drag_mouse_in_timeline_view,
    press_key,
)
from tests.ui.timelines.marker.interact import click_marker_ui
from tests.ui.timelines.range.interact import click_range_ui
from tests.utils import undoable
from tilia.requests import Get, Post, post
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.windows import WindowKind


def _id(kind: str, suffix: str) -> str:
    return f"{kind}-{suffix}"


def _set_color(click, element, hex_color):
    click(element)
    with Serve(Get.FROM_USER_COLOR, (True, QColor(hex_color))):
        commands.execute("timeline.component.set_color")


def create_marker(tlui, time, attr_value=None):
    commands.execute("media.seek", time)
    commands.execute("timeline.marker.add")
    element = tlui[-1]
    if attr_value is not None:
        _set_color(click_marker_ui, element, attr_value)
    return element


def create_hierarchy(tlui, time, attr_value=None):
    kwargs = {"color": attr_value} if attr_value is not None else {}
    commands.execute(
        "timeline.hierarchy.add", start=time, end=time + 1, level=1, **kwargs
    )
    return tlui[-1]


def create_pdf_marker(tlui, time, attr_value=None):
    kwargs = {"page_number": attr_value} if attr_value is not None else {}
    commands.execute("timeline.pdf.add", time=time, **kwargs)
    return tlui[-1]


def create_harmony(tlui, time, attr_value=None):
    quality = attr_value if attr_value is not None else "major"
    commands.execute("media.seek", time)
    with Serve(
        Get.FROM_USER_HARMONY_PARAMS,
        (True, {"step": 0, "accidental": 0, "quality": quality}),
    ):
        commands.execute("timeline.harmony.add_harmony")
    return tlui[-1]


def create_mode(tlui, time, attr_value=None):
    mode_type = attr_value if attr_value is not None else "major"
    commands.execute("media.seek", time)
    with Serve(
        Get.FROM_USER_MODE_PARAMS,
        (True, {"step": 0, "accidental": 0, "type": mode_type}),
    ):
        commands.execute("timeline.harmony.add_mode")
    return tlui[-1]


def create_beat(tlui, time, attr_value=None):
    commands.execute("media.seek", time)
    commands.execute("timeline.beat.add")
    return tlui[-1]


def create_range(tlui, time, attr_value=None):
    commands.execute("timeline.range.add_range", start=time, end=time + 1)
    element = tlui[-1]
    if attr_value is not None:
        _set_color(click_range_ui, element, attr_value)
    return element


# kind id -> tlui fixture name, click helper, position attribute ("time" for
# point components, "start" for interval ones), component-creation helper,
# and (attribute name, two distinct values) used to prove a copy happened.
KIND_TABLE = {
    "marker": dict(
        tlui_fixture="marker_tlui",
        click=click_marker_ui,
        time_attr="time",
        create=create_marker,
        attr="color",
        values=("#ff0000", "#00ff00"),
    ),
    "hierarchy": dict(
        tlui_fixture="hierarchy_tlui",
        click=click_timeline_ui_element_body,
        time_attr="start",
        create=create_hierarchy,
        attr="color",
        values=("#ff0000", "#00ff00"),
    ),
    "pdf": dict(
        tlui_fixture="pdf_tlui",
        click=click_timeline_ui_element_body,
        time_attr="time",
        create=create_pdf_marker,
        attr="page_number",
        values=(3, 7),
    ),
    "harmony": dict(
        tlui_fixture="harmony_tlui",
        click=click_harmony_ui,
        time_attr="time",
        create=create_harmony,
        attr="quality",
        values=("major", "minor"),
    ),
    "mode": dict(
        tlui_fixture="harmony_tlui",
        click=click_mode_ui,
        time_attr="time",
        create=create_mode,
        attr="type",
        values=("major", "minor"),
    ),
    "beat": dict(
        tlui_fixture="beat_tlui",
        click=click_beat_ui,
        time_attr="time",
        create=create_beat,
        attr=None,
        values=(None, None),
    ),
    "range": dict(
        tlui_fixture="range_tlui",
        click=click_range_ui,
        time_attr="start",
        create=create_range,
        attr="color",
        values=("#ff0000", "#00ff00"),
    ),
}


def _tlui(request, kind_id):
    # Callers must also declare `tluis` as an ordinary fixture parameter (not
    # just reach it transitively through this helper): `tluis` must already
    # be constructed -- so qtui is listening -- before this dynamic
    # getfixturevalue() triggers the underlying timeline's creation, or the
    # new timeline ends up with no UI (see tests/test_export.py's identical
    # `tluis` comment for the same gotcha).
    return request.getfixturevalue(KIND_TABLE[kind_id]["tlui_fixture"])


# ---------------------------------------------------------------------------
# Copy/paste into a selected element
# ---------------------------------------------------------------------------

# hierarchy: only `paste_single_into_selected_elements` exists, so "single"
# runs but "several" is skipped. beat: no `paste_*_into_selected_elements`
# at all, skipped entirely (see module docstring).
PASTE_SINGLE_INTO_ELEMENT_KINDS = [
    pytest.param("marker", id=_id("marker", "paste-single-into-element")),
    pytest.param("hierarchy", id=_id("hierarchy", "paste-single-into-element")),
    pytest.param("pdf", id=_id("pdf", "paste-single-into-element")),
    pytest.param("harmony", id=_id("harmony", "paste-single-into-element")),
    pytest.param("mode", id=_id("mode", "paste-single-into-element")),
    pytest.param("range", id=_id("range", "paste-single-into-element")),
]


@pytest.mark.parametrize("kind_id", PASTE_SINGLE_INTO_ELEMENT_KINDS)
def test_paste_single_into_element(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    attr = spec["attr"]
    v1, v2 = spec["values"]

    source = spec["create"](tlui, 0, attr_value=v1)
    target = spec["create"](tlui, 10, attr_value=v2)

    click(source)
    commands.execute("timeline.component.copy")
    click(target)

    with undoable():
        commands.execute("timeline.component.paste")
        assert target.get_data(attr) == v1


PASTE_SEVERAL_INTO_ELEMENT_KINDS = [
    pytest.param("marker", id=_id("marker", "paste-several-into-element")),
    pytest.param("pdf", id=_id("pdf", "paste-several-into-element")),
    pytest.param("harmony", id=_id("harmony", "paste-several-into-element")),
    pytest.param("mode", id=_id("mode", "paste-several-into-element")),
    pytest.param("range", id=_id("range", "paste-several-into-element")),
]


@pytest.mark.parametrize("kind_id", PASTE_SEVERAL_INTO_ELEMENT_KINDS)
def test_paste_several_into_element(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    attr = spec["attr"]
    v1, v2 = spec["values"]

    src_a = spec["create"](tlui, 0, attr_value=v1)
    src_b = spec["create"](tlui, 10, attr_value=v2)
    target = spec["create"](tlui, 50, attr_value=None)

    click(src_a)
    click(src_b, modifier="ctrl")
    commands.execute("timeline.component.copy")

    click(target)
    initial_len = len(tlui)

    with undoable():
        commands.execute("timeline.component.paste")
        # First copied component overwrites the selected target in place;
        # the rest are newly created -- net +1 for 2 copied components.
        assert len(tlui) == initial_len + 1
        assert target.get_data(attr) == v1


# ---------------------------------------------------------------------------
# Copy/paste into the timeline (at the playback/selected time)
# ---------------------------------------------------------------------------

# hierarchy: no `paste_*_into_timeline` at all via the plain "paste" command
# -- skipped entirely (see module docstring).
PASTE_SINGLE_INTO_TIMELINE_KINDS = [
    pytest.param("marker", id=_id("marker", "paste-single-into-timeline")),
    pytest.param("pdf", id=_id("pdf", "paste-single-into-timeline")),
    pytest.param("harmony", id=_id("harmony", "paste-single-into-timeline")),
    pytest.param("mode", id=_id("mode", "paste-single-into-timeline")),
    pytest.param("beat", id=_id("beat", "paste-single-into-timeline")),
    pytest.param("range", id=_id("range", "paste-single-into-timeline")),
]


@pytest.mark.parametrize("kind_id", PASTE_SINGLE_INTO_TIMELINE_KINDS)
def test_paste_single_into_timeline(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    time_attr = spec["time_attr"]

    source = spec["create"](tlui, 0)
    click(source)
    commands.execute("timeline.component.copy")

    click_timeline_ui(tlui, 90)  # click empty space: deselect
    commands.execute("media.seek", 40)

    initial_len = len(tlui)
    with undoable():
        commands.execute("timeline.component.paste")
        assert len(tlui) == initial_len + 1
        assert tlui[-1].get_data(time_attr) == pytest.approx(40)


PASTE_SEVERAL_INTO_TIMELINE_KINDS = [
    pytest.param("marker", id=_id("marker", "paste-several-into-timeline")),
    pytest.param("pdf", id=_id("pdf", "paste-several-into-timeline")),
    pytest.param("harmony", id=_id("harmony", "paste-several-into-timeline")),
    pytest.param("mode", id=_id("mode", "paste-several-into-timeline")),
    pytest.param("beat", id=_id("beat", "paste-several-into-timeline")),
    pytest.param("range", id=_id("range", "paste-several-into-timeline")),
]


@pytest.mark.parametrize("kind_id", PASTE_SEVERAL_INTO_TIMELINE_KINDS)
def test_paste_several_into_timeline(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    time_attr = spec["time_attr"]

    source_a = spec["create"](tlui, 0)
    source_b = spec["create"](tlui, 10)
    click(source_a)
    click(source_b, modifier="ctrl")
    commands.execute("timeline.component.copy")

    click_timeline_ui(tlui, 90)  # click empty space: deselect
    commands.execute("media.seek", 40)

    initial_len = len(tlui)
    with undoable():
        commands.execute("timeline.component.paste")
        assert len(tlui) == initial_len + 2
        times = sorted([tlui[-2].get_data(time_attr), tlui[-1].get_data(time_attr)])
        assert times == [pytest.approx(40), pytest.approx(50)]


def test_paste_harmony_and_mode_together_into_timeline(harmony_tlui):
    """Paste modes and harmonies together (most plausible reading: into the
    timeline, mirroring the sibling single-kind paste-into-timeline tests)."""
    harmony_el = create_harmony(harmony_tlui, 0)
    mode_el = create_mode(harmony_tlui, 5)

    click_harmony_ui(harmony_el)
    click_mode_ui(mode_el, modifier="ctrl")
    commands.execute("timeline.component.copy")

    click_timeline_ui(harmony_tlui, 90)
    commands.execute("media.seek", 40)

    initial_len = len(harmony_tlui)
    with undoable():
        commands.execute("timeline.component.paste")
        assert len(harmony_tlui) == initial_len + 2


# ---------------------------------------------------------------------------
# Color: set (dialog accepted), cancel (dialog rejected), reset
# ---------------------------------------------------------------------------

# pdf, harmony, mode, beat: not in TimelineFlag.COMPONENTS_COLORED (no
# `timeline.component.set_color`/`reset_color` in their context menus) --
# skipped entirely.
COLOR_KINDS = [
    pytest.param("marker", id=_id("marker", "set-color")),
    pytest.param("hierarchy", id=_id("hierarchy", "set-color")),
    pytest.param("range", id=_id("range", "set-color")),
]


@pytest.mark.parametrize("kind_id", COLOR_KINDS)
def test_set_color(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    element = spec["create"](tlui, 0)

    click(element)
    with undoable():
        with Serve(Get.FROM_USER_COLOR, (True, QColor("#123456"))):
            commands.execute("timeline.component.set_color")
        assert element.get_data("color") == "#123456"


CANCEL_COLOR_KINDS = [
    pytest.param("marker", id=_id("marker", "cancel-color-dialog")),
    pytest.param("hierarchy", id=_id("hierarchy", "cancel-color-dialog")),
    pytest.param("range", id=_id("range", "cancel-color-dialog")),
]


@pytest.mark.parametrize("kind_id", CANCEL_COLOR_KINDS)
def test_cancel_color_dialog(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    element = spec["create"](tlui, 0)

    click(element)
    with patch.object(QColorDialog, "getColor", return_value=QColor("invalid")):
        commands.execute("timeline.component.set_color")

    # Uncolored defaults differ by kind (Marker/Range default to `None`,
    # Hierarchy defaults to `""` -- see tilia/timelines/hierarchy/components.py
    # vs tilia/timelines/marker/components.py); either is "no color set".
    assert not element.get_data("color")


RESET_COLOR_KINDS = [
    pytest.param("marker", id=_id("marker", "reset-color")),
    pytest.param("hierarchy", id=_id("hierarchy", "reset-color")),
    pytest.param("range", id=_id("range", "reset-color")),
]


@pytest.mark.parametrize("kind_id", RESET_COLOR_KINDS)
def test_reset_color(kind_id, request, tluis):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    element = spec["create"](tlui, 0, attr_value="#123456")

    click(element)
    with undoable():
        commands.execute("timeline.component.reset_color")
        assert element.get_data("color") is None


# ---------------------------------------------------------------------------
# Inspector open/close (Enter to open, Enter/Escape to close) -- generic,
# offered by every kind.
# ---------------------------------------------------------------------------

# NOTE: pdf is deliberately NOT included here -- see
# `test_open_close_inspector_pdf` at the bottom of this module, which covers
# the same open/close behaviour but is kept as the very last test in the file
# for a documented reason (it corrupts qtui's focus/window state for whatever
# runs after it).
INSPECTOR_KINDS = [
    pytest.param("marker", id=_id("marker", "inspector-open-close")),
    pytest.param("hierarchy", id=_id("hierarchy", "inspector-open-close")),
    pytest.param("harmony", id=_id("harmony", "inspector-open-close")),
    pytest.param("mode", id=_id("mode", "inspector-open-close")),
    pytest.param("beat", id=_id("beat", "inspector-open-close")),
    pytest.param("range", id=_id("range", "inspector-open-close")),
]


@pytest.mark.parametrize("kind_id", INSPECTOR_KINDS)
def test_open_close_inspector(kind_id, request, qtui):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    element = spec["create"](tlui, 0)

    click(element)
    press_key("Enter")  # open inspector via shortcut
    assert qtui.is_window_open(WindowKind.INSPECT)

    press_key("Enter")  # close inspector via shortcut
    assert not qtui.is_window_open(WindowKind.INSPECT)


# ---------------------------------------------------------------------------
# Paste into the timeline while the playback slider is being dragged: the
# pasted component should land at the slider's current (live, unreleased)
# time -- tilia.ui.timelines.collection.collection.py's `on_slider_drag`
# updates `Get.SELECTED_TIME` immediately on every drag tick, independently
# of the actual media seek (which only commits on release).
# ---------------------------------------------------------------------------

DRAG_PASTE_KINDS = [
    pytest.param(
        "marker",
        id=_id("marker", "paste-single-into-timeline-while-dragging"),
    ),
    pytest.param("pdf", id=_id("pdf", "paste-single-into-timeline-while-dragging")),
    pytest.param(
        "harmony",
        id=_id("harmony", "paste-single-into-timeline-while-dragging"),
    ),
    pytest.param("mode", id=_id("mode", "paste-single-into-timeline-while-dragging")),
    pytest.param(
        "beat",
        id=_id("beat", "paste-single-into-timeline-while-dragging"),
        marks=pytest.mark.xfail(
            strict=True,
            reason=(
                "BeatTimelineUI.paste_multiple_into_timeline reads "
                "Get.MEDIA_CURRENT_TIME (tilia/ui/timelines/beat/timeline.py:245), "
                "the actual player position which is only updated on drag "
                "release, instead of the live Get.SELECTED_TIME that "
                "TimelineUIs.on_slider_drag keeps updated during the drag itself "
                "(tilia/ui/timelines/collection/collection.py:1491-1493). Every "
                "other pasteable kind's paste_multiple_into_timeline reads "
                "Get.SELECTED_TIME, so a beat pasted mid-drag lands at the "
                "pre-drag time instead of the slider's current position."
            ),
        ),
    ),
    pytest.param("range", id=_id("range", "paste-single-into-timeline-while-dragging")),
]


@pytest.mark.parametrize("kind_id", DRAG_PASTE_KINDS)
def test_paste_single_into_timeline_while_dragging_slider(
    kind_id, request, slider_tlui
):
    spec = KIND_TABLE[kind_id]
    tlui = _tlui(request, kind_id)
    click = spec["click"]
    time_attr = spec["time_attr"]

    source = spec["create"](tlui, 0)
    click(source)
    commands.execute("timeline.component.copy")
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)  # release before clicking elsewhere
    click_timeline_ui(tlui, 90)  # deselect, without moving playback time
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

    y = slider_tlui.trough.pos().y()
    click_timeline_ui(slider_tlui, 0, y=y)
    target_x = time_x_converter.get_x_by_time(60)
    drag_mouse_in_timeline_view(target_x, y, release=False)

    commands.execute("timeline.component.paste")

    assert tlui[-1].get_data(time_attr) == pytest.approx(60)


# ---------------------------------------------------------------------------
# pdf inspector open/close: separate from `test_open_close_inspector` because
# the PDF timeline needs the main window re-activated first (see below).
@pytest.mark.skip(
    reason=(
        "Passes, but when it runs after the other inspector and paste "
        "tests in this module, a later test in the same process dies with a "
        "Windows heap-corruption error (0xc0000374), e.g. "
        "tests/ui/timelines/beat/test_beat_timeline_ui.py::TestLoadFromFile::"
        "test_measure_numbers_are_loaded. Skipped until the cause is found, "
        "since it could take down unrelated tests in a pytest-xdist worker."
    )
)
def test_open_close_inspector_pdf(request, qtui):
    spec = KIND_TABLE["pdf"]
    tlui = _tlui(request, "pdf")
    element = spec["create"](tlui, 0)

    spec["click"](element)
    # A PDF timeline opens its own top-level PDF window. In the offscreen test
    # session that leaves no focused widget, so the Enter key would go nowhere;
    # in the app, clicking the marker re-activates the main window. Do that.
    qtui.main_window.activateWindow()
    tlui.view.setFocus()
    press_key("Enter")  # open inspector via shortcut
    assert qtui.is_window_open(WindowKind.INSPECT)

    press_key("Enter")  # close inspector via shortcut
    assert not qtui.is_window_open(WindowKind.INSPECT)
