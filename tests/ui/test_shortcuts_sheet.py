"""The keyboard shortcuts sheet is made for every release from the command
registry (see .github/workflows/build.yml), so these tests build it from the
real registry: a change that breaks the sheet fails here, not at release time.
"""

import datetime
import xml.etree.ElementTree as ElementTree

import pytest

import tilia.settings
from tests.utils import get_main_window_menu, get_submenu
from tilia.ui import commands, shortcuts_sheet
from tilia.ui.qtui import TiliaMainWindow
from tilia.ui.shortcuts_sheet import Shortcut, ShortcutClash

SVG = "{http://www.w3.org/2000/svg}"


def get_group(groups, title):
    return next(group for group in groups if group.title == title)


def keys_and_commands(group):
    return {(shortcut.key, shortcut.command) for shortcut in group.shortcuts}


@pytest.fixture
def register_with_shortcut():
    """Registers a command the way TiLiA's code does, as a developer adding a
    shortcut would."""
    registered = []

    def _register(name, shortcut):
        # Teardown can't remove a command, only take its key away, so a real
        # command's name would leave that command broken.
        assert name.endswith(".new_command"), "use a name no real command has"
        commands.register(name, lambda: None, text="New command", shortcut=shortcut)
        registered.append(name)

    yield _register
    for name in registered:
        # Registering again without a shortcut takes the command off its key.
        commands.register(name, lambda: None)


class TestCollect:
    def test_menu_shortcut_has_its_menu_path(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        assert (
            Shortcut("Ctrl+S", "Save", "File → Save", "file.save")
            in get_group(groups, "Global").shortcuts
        )

    def test_submenu_shortcut_has_its_full_path(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        assert (
            Shortcut(
                "Ctrl+Shift+L", "Local", "File → Load media → Local", "media.load.local"
            )
            in get_group(groups, "Global").shortcuts
        )

    @pytest.mark.parametrize(
        "key,command,group,location",
        [
            ("B", "timeline.beat.add", "Beat timeline", "Beat toolbar"),
            (
                "H",
                "timeline.harmony.add_harmony",
                "Harmony timeline",
                "Harmony toolbar",
            ),
            (
                "G",
                "timeline.hierarchy.group",
                "Hierarchy timeline",
                "Hierarchy toolbar",
            ),
            ("M", "timeline.marker.add", "Marker timeline", "Marker toolbar"),
            ("P", "timeline.pdf.add", "PDF timeline", "PDF toolbar"),
            ("R", "timeline.range.add_range", "Range timeline", "Range toolbar"),
        ],
    )
    def test_timeline_kind_shortcut_is_in_its_group(
        self, qtui, key, command, group, location
    ):
        groups = shortcuts_sheet.collect(qtui)

        [shortcut] = [
            s for s in get_group(groups, group).shortcuts if s.command == command
        ]
        assert (shortcut.key, shortcut.location) == (key, location)

    def test_every_registered_shortcut_is_on_the_sheet(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        on_sheet = set().union(*(keys_and_commands(group) for group in groups))
        registered = {
            (key, name)
            for key, names in commands.get_shortcuts().items()
            for name in names
        }
        assert registered <= on_sheet

    def test_global_comes_first_then_kinds_in_add_timeline_menu_order(self, qtui):
        add_menu = get_submenu(get_main_window_menu(qtui, "Timelines"), "Add")
        kinds = [action.text().replace("&", "") for action in add_menu.actions()]

        titles = [group.title for group in shortcuts_sheet.collect(qtui)]

        assert titles[0] == "Global"
        assert titles[1:] == [
            f"{kind} timeline" for kind in kinds if f"{kind} timeline" in titles
        ]

    def test_key_shared_by_two_kinds_is_in_both_groups(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        hierarchy_merge = Shortcut(
            "E", "Merge", "Hierarchy toolbar", "timeline.hierarchy.merge"
        )
        range_merge = Shortcut(
            "E", "Merge ranges", "Range toolbar", "timeline.range.merge_ranges"
        )
        assert hierarchy_merge in get_group(groups, "Hierarchy timeline").shortcuts
        assert range_merge in get_group(groups, "Range timeline").shortcuts


class TestCaughtKeys:
    """Keys TiliaMainWindow and TimelineView catch themselves, instead of
    registering them as shortcuts."""

    @pytest.mark.parametrize(
        "shortcut",
        [
            Shortcut("Del", "Delete", "anywhere", "timeline.component.delete", True),
            Shortcut("Return", "Inspect", "anywhere", "timeline.element.inspect", True),
            Shortcut("Enter", "Inspect", "anywhere", "timeline.element.inspect", True),
        ],
    )
    def test_main_window_key_is_global(self, qtui, shortcut):
        groups = shortcuts_sheet.collect(qtui)

        assert shortcut in get_group(groups, "Global").shortcuts

    def test_every_key_the_main_window_catches_is_on_the_sheet(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        on_sheet = set().union(*(keys_and_commands(group) for group in groups))
        caught = {
            (commands.normalize_shortcut(combination), name)
            for combination, name in TiliaMainWindow.KEY_COMMANDS
        }
        assert caught <= on_sheet

    def test_key_both_registered_and_caught_is_listed_once(self, qtui):
        groups = shortcuts_sheet.collect(qtui)

        copies = [
            s
            for s in get_group(groups, "Global").shortcuts
            if s.command == "timeline.component.copy"
        ]
        assert [s.key for s in copies] == ["Ctrl+C"]

    @pytest.mark.parametrize(
        "shortcut",
        [
            Shortcut(
                "Left",
                "Select the previous element",
                "in a timeline",
                "left arrow",
                True,
            ),
            Shortcut(
                "Right", "Select the next element", "in a timeline", "right arrow", True
            ),
        ],
    )
    def test_arrow_every_kind_takes_alike_is_listed_once_under_global(
        self, qtui, shortcut
    ):
        groups = shortcuts_sheet.collect(qtui)

        assert shortcut in get_group(groups, "Global").shortcuts
        assert [
            group.title
            for group in groups
            if shortcut.key in {s.key for s in group.shortcuts}
        ] == ["Global"]

    @pytest.mark.parametrize(
        "group,up,down",
        [
            ("Hierarchy timeline", "Select the parent", "Select the first child"),
            (
                "Range timeline",
                "Select a range in the row above",
                "Select a range in the row below",
            ),
        ],
    )
    def test_up_and_down_are_in_the_kinds_that_take_them(self, qtui, group, up, down):
        groups = shortcuts_sheet.collect(qtui)

        shortcuts = get_group(groups, group).shortcuts
        assert Shortcut("Up", up, "in a timeline", "up arrow", True) in shortcuts
        assert Shortcut("Down", down, "in a timeline", "down arrow", True) in shortcuts
        assert {g.title for g in groups if "Up" in {s.key for s in g.shortcuts}} == {
            "Hierarchy timeline",
            "Range timeline",
        }

    @pytest.mark.parametrize(
        "group,shortcut",
        [
            (
                "Hierarchy timeline",
                Shortcut(
                    "Ctrl+Up",
                    "Move up a level",
                    "Hierarchy toolbar",
                    "timeline.hierarchy.increase_level",
                    True,
                ),
            ),
            (
                "Hierarchy timeline",
                Shortcut(
                    "Ctrl+Down",
                    "Move down a level",
                    "Hierarchy toolbar",
                    "timeline.hierarchy.decrease_level",
                    True,
                ),
            ),
            (
                "Range timeline",
                Shortcut(
                    "Ctrl+Up",
                    "Move to row above",
                    "in a timeline",
                    "timeline.range.move_to_row_above",
                    True,
                ),
            ),
            (
                "Range timeline",
                Shortcut(
                    "Ctrl+Down",
                    "Move to row below",
                    "in a timeline",
                    "timeline.range.move_to_row_below",
                    True,
                ),
            ),
        ],
    )
    def test_ctrl_arrow_runs_its_kinds_command(self, qtui, group, shortcut):
        groups = shortcuts_sheet.collect(qtui)

        assert shortcut in get_group(groups, group).shortcuts


class TestCheckClashes:
    def test_todays_shortcuts_pass(self, qtui):
        shortcuts_sheet.check_clashes(shortcuts_sheet.collect(qtui))

    @pytest.mark.parametrize(
        "name,shortcut,clashes_with",
        [
            ("timeline.marker.new_command", "m", "timeline.marker.add"),
            ("view.new_command", "m", "timeline.marker.add"),
            ("view.new_command", "Ctrl+S", "file.save"),
            ("timeline.marker.new_command", "Up", "up arrow"),
            ("view.new_command", "Left", "left arrow"),
        ],
        ids=[
            "same timeline kind",
            "global and timeline kind",
            "both global",
            "registered in one kind, caught in another",
            "registered and caught, both global",
        ],
    )
    def test_two_commands_with_one_key_in_one_context_fail(
        self, qtui, register_with_shortcut, name, shortcut, clashes_with
    ):
        register_with_shortcut(name, shortcut)

        with pytest.raises(ShortcutClash) as error:
            shortcuts_sheet.check_clashes(shortcuts_sheet.collect(qtui))

        assert name in str(error.value)
        assert clashes_with in str(error.value)

    def test_one_key_in_two_timeline_kinds_passes(self, qtui, register_with_shortcut):
        register_with_shortcut("timeline.hierarchy.new_command", "m")

        shortcuts_sheet.check_clashes(shortcuts_sheet.collect(qtui))


class TestWrite:
    DATE = datetime.date(2026, 10, 14)

    def test_writes_svg(self, qtui, tmp_path):
        shortcuts_sheet.write_sheet(qtui, tmp_path, "1.2.3", self.DATE)

        svg = ElementTree.parse(tmp_path / "shortcuts.svg").getroot()
        texts = ["".join(element.itertext()) for element in svg.iter(f"{SVG}text")]
        assert svg.find(f"{SVG}title").text == (
            "TiLiA 1.2.3 keyboard shortcuts (2026-10-14)"
        )
        assert "TiLiA 1.2.3 keyboard shortcuts 2026-10-14" in texts
        assert "Ctrl+S" in texts
        assert "File → Save" in texts

    def test_writes_markdown(self, qtui, tmp_path):
        shortcuts_sheet.write_sheet(qtui, tmp_path, "1.2.3", self.DATE)

        markdown = (tmp_path / "shortcuts.md").read_text(encoding="utf-8")
        assert markdown.startswith("# TiLiA 1.2.3 keyboard shortcuts (2026-10-14)\n")
        assert "## Hierarchy timeline" in markdown
        assert "| <kbd>Ctrl+S</kbd> | Save | File → Save |" in markdown

    def test_writes_nothing_when_shortcuts_clash(
        self, qtui, tmp_path, register_with_shortcut
    ):
        register_with_shortcut("timeline.marker.new_command", "m")

        with pytest.raises(ShortcutClash):
            shortcuts_sheet.write_sheet(qtui, tmp_path, "1.2.3", self.DATE)

        assert not list(tmp_path.iterdir())


class TestCommandLine:
    """main() runs in this process, where isolate_settings keeps the settings
    off the developer's own store; a subprocess would open that store."""

    @pytest.fixture(autouse=True)
    def use_the_tests_ui(self, qtui, monkeypatch):
        monkeypatch.setattr(shortcuts_sheet, "_build_qtui", lambda: qtui)

    def test_writes_both_files(self, tmp_path, capsys):
        shortcuts_sheet.main(["--out", str(tmp_path)])

        paths = [tmp_path / "shortcuts.svg", tmp_path / "shortcuts.md"]
        assert all(path.stat().st_size > 0 for path in paths)
        assert capsys.readouterr().out.splitlines() == [str(path) for path in paths]

    def test_opens_no_settings_store(self, tmp_path, monkeypatch):
        def open_store(*args, **kwargs):
            raise AssertionError(f"The sheet opened a settings store: {args}")

        monkeypatch.setattr(tilia.settings, "QSettings", open_store)

        shortcuts_sheet.main(["--out", str(tmp_path)])
