"""
A cheat sheet of TiLiA's keyboard shortcuts, made from the command registry.

    python -m tilia.ui.shortcuts_sheet --out <folder>

builds the Qt interface without showing it, lists every command that has a
shortcut, and writes shortcuts.svg and shortcuts.md to <folder>. The release
workflow (.github/workflows/build.yml) attaches both files to every release, so
the sheet is never written by hand. Where there is no display, as on the
release workflow's runner, set QT_QPA_PLATFORM=offscreen. Don't on Windows:
Qt's offscreen platform finds no system fonts there, so text is measured with
TiLiA's music font and the columns come out too wide.

Each shortcut is listed with what it does (its command's text) and where to
find it: its menu path, its timeline kind's toolbar, or "anywhere" when no
menu or toolbar has it. Shortcuts are grouped by where they apply: Global,
then one group per timeline kind, in the order of the Timelines → Add menu.

Besides the registered shortcuts, the sheet lists the keys that
TiliaMainWindow.KEY_COMMANDS and TimelineView.ARROWS catch themselves. What an
arrow does comes from each timeline kind's ARROW_TEXTS and
CTRL_ARROW_COMMANDS; an arrow that every kind taking arrows describes the same
way is listed once, under Global.
"""

from __future__ import annotations

import argparse
import datetime
import functools
import html
import itertools
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication, QMenu, QMenuBar, QToolBar, QToolButton

import tilia.constants
from tilia.boot import setup_logic
from tilia.requests import stop_listening_to_all
from tilia.ui import commands
from tilia.ui.commands import CommandQAction
from tilia.ui.menus import AddTimelinesMenu, TimelinesMenu
from tilia.ui.qtui import QtUI, TiliaMainWindow
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.view import TimelineView

GLOBAL = "Global"
ANYWHERE = "anywhere"
IN_A_TIMELINE = "in a timeline"
ARROW = " → "
MAC_NOTE = "On macOS, Ctrl is ⌘ (Command) and Alt is ⌥ (Option)."
FILE_NAMES = ("shortcuts.svg", "shortcuts.md")


@dataclass(frozen=True)
class Shortcut:
    key: str  # PortableText, e.g. "Ctrl+Shift+S"
    text: str
    location: str
    command: str
    # Caught by a keyPressEvent instead of registered as a shortcut.
    caught: bool = False


@dataclass
class ShortcutGroup:
    title: str
    shortcuts: list[Shortcut] = field(default_factory=list)
    applies_everywhere: bool = False


class ShortcutClash(Exception):
    """Two commands that apply in the same context share a key."""


def collect(qtui: QtUI) -> list[ShortcutGroup]:
    """Lists every key TiLiA handles, grouped by where it applies.

    Groups without shortcuts are left out.
    """
    menu_paths = _menu_paths(qtui.main_window.menuBar())
    kind_titles = _timeline_kind_titles(qtui)
    ui_classes = _timeline_ui_classes()
    toolbars = _toolbar_locations(kind_titles, ui_classes)
    # Menus first, in menu-bar order, then toolbars, in kind order.
    places = list(menu_paths) + list(toolbars)

    global_group = ShortcutGroup(GLOBAL, applies_everywhere=True)
    groups = {kind: ShortcutGroup(f"{title} timeline") for kind, title in kind_titles}

    def add(group: ShortcutGroup, shortcut: Shortcut) -> None:
        # A key can be both registered and caught (Ctrl+C): list it once.
        listed = {(s.key, s.command) for s in group.shortcuts}
        if (shortcut.key, shortcut.command) not in listed:
            group.shortcuts.append(shortcut)

    def add_command(
        key: str, name: str, fallback: str = ANYWHERE, caught: bool = False
    ) -> None:
        group = groups.get(_timeline_kind(name), global_group)
        location = menu_paths.get(name) or toolbars.get(name) or fallback
        text = _clean(commands.get_qaction(name).text())
        add(group, Shortcut(key, text, location, name, caught))

    for key, names in commands.get_shortcuts().items():
        for name in names:
            add_command(key, name)
    for combination, name in TiliaMainWindow.KEY_COMMANDS:
        add_command(commands.normalize_shortcut(combination), name, caught=True)

    # Which kinds an arrow reaches follows TimelineUIs.on_arrow_press and
    # on_ctrl_arrow_press.
    arrow_kinds = [
        kind
        for kind, _ in kind_titles
        if ui_classes[kind].ACCEPTS_HORIZONTAL_ARROWS
        or ui_classes[kind].ACCEPTS_VERTICAL_ARROWS
    ]
    vertical_kinds = [k for k in arrow_kinds if ui_classes[k].ACCEPTS_VERTICAL_ARROWS]
    for qt_key, direction in TimelineView.ARROWS.items():
        if direction in ("left", "right"):
            kinds = [k for k in arrow_kinds if ui_classes[k].ACCEPTS_HORIZONTAL_ARROWS]
        else:
            kinds = vertical_kinds
        key = commands.normalize_shortcut(QKeyCombination(qt_key))
        texts = {ui_classes[k].ARROW_TEXTS[direction] for k in kinds}
        command = f"{direction} arrow"
        if kinds == arrow_kinds and len(texts) == 1:
            add(global_group, Shortcut(key, texts.pop(), IN_A_TIMELINE, command, True))
        else:
            for kind in kinds:
                text = ui_classes[kind].ARROW_TEXTS[direction]
                add(groups[kind], Shortcut(key, text, IN_A_TIMELINE, command, True))
        if direction in TimelineView.CTRL_ARROW_POSTS:
            ctrl_key = commands.normalize_shortcut(
                QKeyCombination(Qt.KeyboardModifier.ControlModifier, qt_key)
            )
            for kind in vertical_kinds:
                name = ui_classes[kind].CTRL_ARROW_COMMANDS[direction]
                add_command(ctrl_key, name, fallback=IN_A_TIMELINE, caught=True)

    def place(shortcut: Shortcut) -> int:
        if shortcut.command in places:
            return places.index(shortcut.command)
        return len(places)  # after the others, in the order they were added

    result = [global_group, *groups.values()]
    for group in result:
        group.shortcuts.sort(key=place)
    return [group for group in result if group.shortcuts]


def check_clashes(groups: list[ShortcutGroup]) -> None:
    """Raises ShortcutClash if two commands that apply in the same context share a
    key.

    This follows TimelineUIs.on_shared_shortcut_fired: a key shared by two
    timeline kinds is fine, as TiLiA runs the command of the kind clicked last
    (merge is E in both the hierarchy and the range timelines). Global
    shortcuts apply everywhere, so they clash with any other command on their
    key. A key that a keyPressEvent catches clashes with a registered shortcut
    on it in any group: the shortcut takes the key first.
    """
    everywhere = [s for g in groups if g.applies_everywhere for s in g.shortcuts]
    registered = [s for g in groups for s in g.shortcuts if not s.caught]
    clashes: list[str] = []
    for group in groups:
        in_context = (
            group.shortcuts
            if group.applies_everywhere
            else everywhere + group.shortcuts
        )
        for key in sorted({s.key for s in group.shortcuts}):
            sharing = [s for s in in_context if s.key == key]
            if any(s.caught for s in sharing):
                sharing += [s for s in registered if s.key == key and s not in sharing]
            names = [s.command for s in sharing]
            if len(names) > 1:
                clashes.append(f"  {key} in {group.title}: {', '.join(names)}")
    if clashes:
        raise ShortcutClash(
            "Commands that apply in the same context share a key:\n"
            + "\n".join(clashes)
        )


def write_sheet(
    qtui: QtUI,
    folder: Path,
    version: str = tilia.constants.VERSION,
    date: datetime.date | None = None,
) -> list[Path]:
    """Writes shortcuts.svg and shortcuts.md to folder, or nothing if shortcuts
    clash."""
    groups = collect(qtui)
    check_clashes(groups)
    date = date or datetime.date.today()
    title = f"TiLiA {version} keyboard shortcuts"

    svg = to_svg(groups, title, date)
    markdown = to_markdown(groups, title, date)

    folder.mkdir(parents=True, exist_ok=True)
    svg_path, md_path = (folder / name for name in FILE_NAMES)
    svg_path.write_text(svg, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return [svg_path, md_path]


def _menu_paths(menu_bar: QMenuBar) -> dict[str, str]:
    """Maps each command in the menu bar to its menu path, in menu-bar order."""
    paths: dict[str, str] = {}

    def walk(menu: QMenu, path: list[str]) -> None:
        for action in menu.actions():
            if submenu := action.menu():
                walk(submenu, [*path, _clean(submenu.title())])
            elif isinstance(action, CommandQAction):
                item_path = ARROW.join([*path, _clean(action.text())])
                paths.setdefault(action.command_name, item_path)

    for action in menu_bar.actions():
        if menu := action.menu():
            walk(menu, [_clean(menu.title())])
    return paths


def _timeline_kind_titles(qtui: QtUI) -> list[tuple[str, str]]:
    """Returns (kind, title) for each timeline kind, in the order of the
    Timelines → Add menu, then the kinds it doesn't offer."""
    add_menu = qtui.menu_bar.get_menu(TimelinesMenu).get_submenu(AddTimelinesMenu)
    titles = {}
    for action in add_menu.actions():
        if isinstance(action, CommandQAction):
            kind = action.command_name.removeprefix("timelines.add.")
            titles[kind] = _clean(action.text())
    for ui_class in TimelineUI.subclasses():
        type_name = ui_class.timeline_class.type_name()
        titles.setdefault(type_name.lower(), type_name)
    return list(titles.items())


def _timeline_ui_classes() -> dict[str, type[TimelineUI]]:
    return {
        ui_class.timeline_class.type_name().lower(): ui_class
        for ui_class in TimelineUI.subclasses()
    }


def _timeline_kind(command: str) -> str | None:
    """Returns the kind of a command registered by
    TimelineUI.register_timeline_command ("timeline.<kind>.<name>")."""
    parts = command.split(".")
    return parts[1] if len(parts) > 2 and parts[0] == "timeline" else None


def _toolbar_locations(
    kind_titles: list[tuple[str, str]], ui_classes: dict[str, type[TimelineUI]]
) -> dict[str, str]:
    """Maps each command on a timeline kind's toolbar to "<Kind> toolbar"."""
    locations: dict[str, str] = {}
    for kind, title in kind_titles:
        if toolbar_class := ui_classes[kind].TOOLBAR_CLASS:
            for name in _toolbar_commands(toolbar_class):
                locations.setdefault(name, f"{title} toolbar")
    return locations


# The app only builds a kind's toolbar once a timeline of that kind exists, so
# each toolbar is built here, once. It is kept: RangeTimelineToolbar connects
# the shared range commands' actions to its own buttons, and deleting it would
# leave those connections pointing at deleted buttons.
_built_toolbars: list[QToolBar] = []


@functools.cache
def _toolbar_commands(toolbar_class: type[QToolBar]) -> tuple[str, ...]:
    """Returns the commands on a toolbar, including those in its buttons' menus."""
    toolbar = toolbar_class()
    stop_listening_to_all(toolbar)
    _built_toolbars.append(toolbar)
    names = []
    for action in toolbar.actions():
        button = toolbar.widgetForAction(action)
        if isinstance(button, QToolButton) and button.menu():
            actions = button.menu().actions()
        else:
            actions = [action]
        names += [a.command_name for a in actions if isinstance(a, CommandQAction)]
    return tuple(names)


def _clean(text: str) -> str:
    """Returns a menu text as shown to users: without "&" accelerators, without
    the key hint setup_shortcuts adds after a tab, and without a trailing "..."."""
    text = text.split("\t")[0]
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    return text.strip().removesuffix("...").removesuffix("…").strip()


# --- SVG ---

WIDTH = 1000
MARGIN = 32
GUTTER = 28
# TiLiA uses the platform's UI font. Text is measured with the font Qt picks
# for this value. The release workflow's Linux runner has none of these fonts
# and falls back to its default sans-serif font, usually DejaVu Sans, which is
# wider than all of them: text that fits there fits in a browser too.
FONT_FAMILY = "system-ui, Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"

TEXT_COLOR = "#1f1f1f"
MUTED_COLOR = "#666666"
ACCENT_COLOR = "#f1592a"  # TiLiA's logo (tilia/ui/icons/hicolor/apps/256/tilia.svg)
KEY_FILL = "#f4f4f4"
KEY_STROKE = "#bdbdbd"
BACKGROUND = "#ffffff"

TITLE_SIZE = 26
DATE_SIZE = 18
NOTE_SIZE = 14
HEADING_SIZE = 17
TEXT_SIZE = 14
LOCATION_SIZE = 12
KEY_SIZE = 13

KEY_HEIGHT = 24
KEY_PADDING = 8
KEY_GAP = 12
HEADING_HEIGHT = 40
ROW_HEIGHT = 46
GROUP_GAP = 20
COLUMNS_TOP = MARGIN + 92


def to_svg(groups: list[ShortcutGroup], title: str, date: datetime.date) -> str:
    columns, column_width = _layout(groups)
    height = COLUMNS_TOP + max(_column_height(c) for c in columns) + MARGIN
    title_baseline = MARGIN + 24
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}"'
        f' viewBox="0 0 {WIDTH} {height}">',
        f"<title>{_escape(title)} ({date.isoformat()})</title>",
        f'<rect width="{WIDTH}" height="{height}" fill="{BACKGROUND}"/>',
        f'<rect width="{WIDTH}" height="6" fill="{ACCENT_COLOR}"/>',
        f'<g font-family="{FONT_FAMILY}">',
        f'<text x="{MARGIN}" y="{title_baseline}" font-size="{TITLE_SIZE}"'
        f' font-weight="bold" fill="{TEXT_COLOR}">{_escape(title)} <tspan'
        f' font-size="{DATE_SIZE}" font-weight="normal" fill="{MUTED_COLOR}">'
        f"{date.isoformat()}</tspan></text>",
        _text(MARGIN, title_baseline + 30, MAC_NOTE, NOTE_SIZE, color=MUTED_COLOR),
    ]
    for index, column in enumerate(columns):
        x = MARGIN + index * (column_width + GUTTER)
        key_width = _column_key_width(column)
        y = COLUMNS_TOP
        for group in column:
            parts += _group_svg(group, x, y, column_width, key_width)
            y += _group_height(group) + GROUP_GAP
    parts += ["</g>", "</svg>", ""]
    return "\n".join(parts)


def _group_svg(
    group: ShortcutGroup, x: float, y: float, width: float, key_width: float
) -> list[str]:
    parts = [
        _text(x, y + 17, group.title, HEADING_SIZE, bold=True),
        f'<rect x="{x:.1f}" y="{y + 26:.1f}" width="{width:.1f}" height="2"'
        f' fill="{ACCENT_COLOR}"/>',
    ]
    text_x = x + key_width + KEY_GAP
    row_y = y + HEADING_HEIGHT
    for shortcut in group.shortcuts:
        cap_width = _key_width(shortcut.key)
        cap_x = text_x - KEY_GAP - cap_width
        parts += [
            f'<rect x="{cap_x:.1f}" y="{row_y:.1f}" width="{cap_width:.1f}"'
            f' height="{KEY_HEIGHT}" rx="4" fill="{KEY_FILL}" stroke="{KEY_STROKE}"/>',
            _text(
                cap_x + cap_width / 2,
                row_y + 17,
                shortcut.key,
                KEY_SIZE,
                bold=True,
                anchor="middle",
            ),
            _text(text_x, row_y + 17, shortcut.text, TEXT_SIZE),
            _text(
                text_x, row_y + 35, shortcut.location, LOCATION_SIZE, color=MUTED_COLOR
            ),
        ]
        row_y += ROW_HEIGHT
    return parts


def _layout(groups: list[ShortcutGroup]) -> tuple[list[list[ShortcutGroup]], float]:
    """Splits the groups, in order and keeping each whole, into as many columns as
    fit, with the tallest column as short as possible. Returns the columns and
    their width."""
    for count in range(len(groups), 1, -1):
        width = (WIDTH - 2 * MARGIN - (count - 1) * GUTTER) / count
        best: list[list[ShortcutGroup]] = []
        best_height = float("inf")
        for cuts in itertools.combinations(range(1, len(groups)), count - 1):
            bounds = zip((0, *cuts), (*cuts, len(groups)), strict=True)
            columns = [groups[start:end] for start, end in bounds]
            if any(_column_width(column) > width for column in columns):
                continue
            height = max(_column_height(column) for column in columns)
            if height < best_height:
                best, best_height = columns, height
        if best:
            return best, width
    return [groups], WIDTH - 2 * MARGIN


def _column_width(column: list[ShortcutGroup]) -> float:
    """Returns the width the column's longest key and longest text need."""
    shortcuts = [s for g in column for s in g.shortcuts]
    text_width = max(
        [_text_width(g.title, HEADING_SIZE, bold=True) for g in column]
        + [_text_width(s.text, TEXT_SIZE) for s in shortcuts]
        + [_text_width(s.location, LOCATION_SIZE) for s in shortcuts]
    )
    return _column_key_width(column) + KEY_GAP + text_width


def _column_key_width(column: list[ShortcutGroup]) -> float:
    return max(_key_width(s.key) for g in column for s in g.shortcuts)


def _column_height(column: list[ShortcutGroup]) -> float:
    return sum(_group_height(g) for g in column) + GROUP_GAP * (len(column) - 1)


def _group_height(group: ShortcutGroup) -> float:
    return HEADING_HEIGHT + ROW_HEIGHT * len(group.shortcuts)


def _key_width(key: str) -> float:
    return max(KEY_HEIGHT, _text_width(key, KEY_SIZE, bold=True) + 2 * KEY_PADDING)


@functools.cache
def _text_width(text: str, size: int, bold: bool = False) -> float:
    font = QFont()
    font.setFamily(FONT_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return QFontMetricsF(font).horizontalAdvance(text)


def _text(
    x: float,
    y: float,
    text: str,
    size: int,
    color: str = TEXT_COLOR,
    bold: bool = False,
    anchor: str = "start",
) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{weight} fill="{color}"'
        f' text-anchor="{anchor}">{_escape(text)}</text>'
    )


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


# --- Markdown ---


def to_markdown(groups: list[ShortcutGroup], title: str, date: datetime.date) -> str:
    lines = [f"# {title} ({date.isoformat()})", "", MAC_NOTE, ""]
    for group in groups:
        lines += [
            f"## {group.title}",
            "",
            "| Key | Action | Where to find it |",
            "| --- | --- | --- |",
        ]
        lines += [
            f"| <kbd>{_cell(s.key)}</kbd> | {_cell(s.text)} | {_cell(s.location)} |"
            for s in group.shortcuts
        ]
        lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return _escape(text).replace("|", "\\|")


# --- Command line ---


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tilia.ui.shortcuts_sheet",
        description="Write TiLiA's keyboard shortcuts as shortcuts.svg and "
        "shortcuts.md.",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="folder to write the files to"
    )
    args = parser.parse_args(argv)

    q_application = QApplication.instance() or QApplication(sys.argv[:1])
    setup_logic(autosaver=False)
    qtui = QtUI(q_application, TiliaMainWindow())
    for path in write_sheet(qtui, args.out):
        print(path)


if __name__ == "__main__":
    main()
