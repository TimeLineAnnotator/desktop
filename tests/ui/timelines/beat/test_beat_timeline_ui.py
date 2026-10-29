import json
from fractions import Fraction as F
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.mock import Serve, patch_ask_for_int_dialog, patch_yes_or_no_dialog
from tests.ui.timelines.beat.interact import (
    click_beat_ui,
    click_time_signature_label,
    edit_bars_dialog_cell,
    hover_time_signature_label,
    patch_bars_dialog,
    patch_beat_pattern_dialog,
    patch_beat_unit_scope_prompt,
    patch_fill_beat_timeline_dialog,
)
from tests.ui.timelines.interact import drag_mouse_in_timeline_view, press_key
from tests.utils import (
    get_command_action,
    get_command_names,
    reloadable,
    save_and_reopen,
    save_tilia_to_tmp_path,
    undoable,
)
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.beat.units import format_units
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia.ui.commands import get_qaction
from tilia.ui.coords import time_x_converter
from tilia.ui.strings import BEAT_UNIT_AMBIGUOUS_TOOLTIP, BEAT_UNIT_ASSUMED_TOOLTIP
from tilia.ui.timelines.beat.context_menu import (
    BeatContextMenu,
    BeatTimelineUIContextMenu,
    BeatUnitContextMenu,
)
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.time_signature import (
    ASSUMED_OPACITY,
    TIME_SIGNATURE_BAND_HEIGHT,
    LabelState,
)
from tilia.ui.windows import WindowKind
from tilia.ui.windows.beat_pattern import (
    BARS_COLUMN,
    TAPS_COLUMN,
    TIME_SIGNATURE_COLUMN,
)


def save_as_file_with_measure_lists(
    tmp_path,
    beats_in_measure: list[int] | None = None,
    measure_numbers: list[int] | None = None,
    measures_to_force_display: list[int] | None = None,
) -> str:
    """
    Saves the current state as a file from before measures were marked on
    their beats, which kept them in lists by measure on the beat timeline. A
    list left out is written as the measures the timeline has now.
    """
    path = save_tilia_to_tmp_path(tmp_path, "measure_lists")
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    for timeline in data["timelines"].values():
        if timeline["kind"] != "BEAT_TIMELINE" and timeline["kind"] != "Beat":
            continue
        starts, numbers, always_shown = [], [], []
        for component in timeline["components"].values():
            if component["kind"] != "BEAT":
                continue
            if component.pop("is_first_in_measure"):
                starts.append(component["time"])
                override = component["measure_number_override"]
                numbers.append(
                    override if override is not None else (numbers or [0])[-1] + 1
                )
                if component["measure_number_always_shown"]:
                    always_shown.append(len(numbers) - 1)
            component.pop("measure_number_override")
            component.pop("measure_number_always_shown")
        times = sorted(
            c["time"] for c in timeline["components"].values() if c["kind"] == "BEAT"
        )
        indices = [times.index(t) for t in starts] + [len(times)]
        counts = [
            end - start for start, end in zip(indices[:-1], indices[1:], strict=True)
        ]
        timeline["beats_in_measure"] = (
            counts if beats_in_measure is None else beats_in_measure
        )
        timeline["measure_numbers"] = (
            numbers if measure_numbers is None else measure_numbers
        )
        timeline["measures_to_force_display"] = (
            always_shown
            if measures_to_force_display is None
            else measures_to_force_display
        )
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file)
    post(Post.APP_CLEAR)
    return path


def get_displayed_measure_number(beat_ui):
    if beat_ui.label.isVisible():
        return beat_ui.label.toPlainText()
    else:
        return ""


class TestLoadFromFile:
    def test_measure_numbers_are_loaded(self, beat_tl, tluis, tmp_path):
        beat_tl.beat_pattern = [1]

        beat_tl.create_beat(0)
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.create_beat(3)

        beat_tl.recalculate_measures()

        beat_tl.set_measure_number(0, 1)
        beat_tl.set_measure_number(1, 3)
        beat_tl.set_measure_number(2, 5)
        beat_tl.set_measure_number(3, 7)

        tmp_file = tmp_path / "test.tla"

        post(Post.REQUEST_SAVE_TO_PATH, tmp_file)

        commands.execute("file.open", tmp_file)

        assert [x.label.toPlainText() for x in tluis[0]] == ["1", "3", "5", "7"]

    def test_file_with_measures_to_force_display(
        self, beat_tlui, tluis, tmp_path, use_test_settings
    ):
        settings.set("beat_timeline", "display_measure_periodicity", 2)

        beat_tlui.timeline.beat_pattern = [1]
        for i in range(8):
            beat_tlui.create_beat(i)

        for i in [1, 3, 5, 7]:
            beat_tlui.timeline.force_display_measure_number(i)

        save_and_reopen(tmp_path)

        assert [x.label.toPlainText() for x in tluis[0]] == [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
        ]

    def test_duplicate_and_out_of_range_forced_measures_are_dropped(
        self, beat_tlui, tluis, tmp_path
    ):
        # Files from before measures were marked on their beats could save
        # such a list.
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")
        path = save_as_file_with_measure_lists(
            tmp_path, measures_to_force_display=[1, 6, 1, 2]
        )
        commands.execute("file.open", path)

        reopened = tluis[0]
        reopened.select_element(reopened[1])
        commands.execute("timeline.beat.reset_measure_number")
        # A duplicate would need a second reset to hide the label.
        assert get_displayed_measure_number(reopened[1]) == ""

        for i in range(4, 7):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")
        # An out-of-range index would force measure 7's label once it exists.
        assert get_displayed_measure_number(reopened[6]) == ""


class TestFileWithMeasureLists:
    """Files from before measures were marked on their beats keep them in
    lists by measure, fitted to the beats when the file is opened."""

    @staticmethod
    def open_file_with(tmp_path, times, **lists):
        for time in times:
            commands.execute("media.seek", time)
            commands.execute("timeline.beat.add")
        commands.execute(
            "file.open", save_as_file_with_measure_lists(tmp_path, **lists)
        )

    def test_measures_are_marked_on_their_first_beats(self, beat_tlui, tluis, tmp_path):
        self.open_file_with(
            tmp_path, range(8), beats_in_measure=[3, 3, 2], measure_numbers=[1, 2, 3]
        )

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [3, 3, 2]
        assert [b.is_first_in_measure for b in timeline] == [
            True,
            False,
            False,
            True,
            False,
            False,
            True,
            False,
        ]

    def test_numbers_that_break_the_count_are_kept(self, beat_tlui, tluis, tmp_path):
        self.open_file_with(
            tmp_path,
            range(6),
            beats_in_measure=[2, 2, 2],
            measure_numbers=[1, 2, 1],
        )

        timeline = tluis[0].timeline
        assert timeline.measure_numbers == [1, 2, 1]
        assert [b.measure_number_override for b in timeline] == [
            None,
            None,
            None,
            None,
            1,
            None,
        ]

    def test_missing_measures_are_made_from_the_pattern(
        self, beat_tlui, tluis, tmp_path
    ):
        self.open_file_with(
            tmp_path, range(10), beats_in_measure=[3], measure_numbers=[5]
        )

        timeline = tluis[0].timeline
        # The incomplete last measure is filled first.
        assert timeline.beats_in_measure == [4, 4, 2]
        assert timeline.measure_numbers == [5, 6, 7]

    def test_surplus_measures_are_dropped(self, beat_tlui, tluis, tmp_path):
        self.open_file_with(
            tmp_path,
            range(5),
            beats_in_measure=[4, 4, 4],
            measure_numbers=[1, 2, 3],
        )

        assert tluis[0].timeline.beats_in_measure == [4, 1]

    def test_forced_display_is_kept(self, beat_tlui, tluis, tmp_path):
        settings.set("beat_timeline", "display_measure_periodicity", 10)
        self.open_file_with(
            tmp_path,
            range(4),
            beats_in_measure=[1, 1, 1, 1],
            measure_numbers=[1, 2, 3, 4],
            measures_to_force_display=[2],
        )

        assert [get_displayed_measure_number(b) for b in tluis[0]] == [
            "1",
            "",
            "3",
            "",
        ]

    def test_saving_again_keeps_the_measures(self, beat_tlui, tluis, tmp_path):
        self.open_file_with(
            tmp_path,
            range(6),
            beats_in_measure=[1, 3, 2],
            measure_numbers=[0, 1, 2],
        )

        save_and_reopen(tmp_path)

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [1, 3, 2]
        assert timeline.measure_numbers == [0, 1, 2]


def add_beat_timeline_with_pattern(pattern: str) -> None:
    commands.execute("timelines.add.beat", name="", beat_pattern=pattern)


def add_beats(times) -> None:
    for time in times:
        commands.execute("media.seek", time)
        commands.execute("timeline.beat.add")


class TestBeatPattern:
    def test_bracketed_pattern_sets_bar_lengths(self, tluis):
        add_beat_timeline_with_pattern("2[3] 4")
        add_beats(range(12))

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "2[3] 4"
        assert timeline.beats_in_measure == [3, 3, 4, 2]

    def test_pattern_text_survives_save_and_reopen(self, tluis, tmp_path):
        add_beat_timeline_with_pattern("2[3] 4")
        add_beats(range(10))

        save_and_reopen(tmp_path)

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "2[3] 4"
        assert timeline.beats_in_measure == [3, 3, 4]
        add_beats(range(10, 13))
        assert timeline.beats_in_measure == [3, 3, 4, 3]

    def test_file_with_list_pattern_loads_as_text(self, tluis, tmp_path):
        # Files saved before patterns were text store a list of bar lengths.
        # The current version can't write one, so edit a saved file.
        add_beat_timeline_with_pattern("4")
        path = save_tilia_to_tmp_path(tmp_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for timeline_data in data["timelines"].values():
            if "beat_pattern" in timeline_data:
                timeline_data["beat_pattern"] = [3, 4]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        post(Post.APP_CLEAR)

        commands.execute("file.open", path=path)
        add_beats(range(7))

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "3 4"
        assert timeline.beats_in_measure == [3, 4]

    def test_set_pattern_recomputes_bars(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(12))
        timeline_ui = tluis[0]

        with undoable():
            commands.execute("timeline.beat.set_pattern", timeline_ui, pattern="3")

        timeline = timeline_ui.timeline
        assert timeline.beat_pattern == "3"
        assert timeline.beats_in_measure == [3, 3, 3, 3]
        assert timeline.measure_numbers == [1, 2, 3, 4]
        assert [b.is_first_in_measure for b in timeline].count(True) == 4
        assert timeline[3].is_first_in_measure

    def test_set_pattern_with_fewer_bars(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        timeline_ui = tluis[0]

        commands.execute("timeline.beat.set_pattern", timeline_ui, pattern="4")

        assert timeline_ui.timeline.beats_in_measure == [4, 4]
        assert timeline_ui.timeline.measure_numbers == [1, 2]

    def test_set_pattern_on_empty_timeline(self, tluis):
        add_beat_timeline_with_pattern("4")

        commands.execute("timeline.beat.set_pattern", tluis[0], pattern="10[4] 3")

        assert tluis[0].timeline.beat_pattern == "10[4] 3"
        add_beats(range(8))
        assert tluis[0].timeline.beats_in_measure == [4, 4]

    def test_set_pattern_through_dialog(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(10))

        with patch_beat_pattern_dialog("2[3] 4"):
            commands.execute("timeline.beat.set_pattern", tluis[0])

        assert tluis[0].timeline.beat_pattern == "2[3] 4"
        assert tluis[0].timeline.beats_in_measure == [3, 3, 4]

    def test_dialog_starts_with_current_pattern(self, tluis):
        add_beat_timeline_with_pattern("2[3] 4")
        add_beats(range(5))
        seen = {}

        def record(dialog):
            seen["text"] = dialog.text
            seen["footer"] = dialog.footer.text()

        with patch_bars_dialog(record):
            commands.execute("timeline.beat.set_pattern", tluis[0])

        assert seen["text"] == "2[3] 4"
        assert seen["footer"].endswith("5 beats tapped, in 2 bars.")
        assert tluis[0].timeline.beats_in_measure == [3, 2]

    def test_cancel_dialog_changes_nothing(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))

        with patch_beat_pattern_dialog(None):
            commands.execute("timeline.beat.set_pattern", tluis[0])

        assert tluis[0].timeline.beat_pattern == "4"
        assert tluis[0].timeline.beats_in_measure == [4, 4]

    def test_invalid_pattern_shows_error(self, tluis, tilia_errors):
        add_beat_timeline_with_pattern("4")

        commands.execute("timeline.beat.set_pattern", tluis[0], pattern="2[")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("Unclosed")
        assert tluis[0].timeline.beat_pattern == "4"

    @staticmethod
    def _set_second_bar_to_three_beats(timeline_ui):
        timeline_ui.select_element(timeline_ui[4])
        with patch_ask_for_int_dialog(True, 3):
            commands.execute("timeline.beat.set_amount_in_measure")
        timeline_ui.deselect_all_elements()

    def test_overwriting_hand_set_bars_asks_first(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(12))
        timeline_ui = tluis[0]
        self._set_second_bar_to_three_beats(timeline_ui)
        assert timeline_ui.timeline.beats_in_measure == [4, 3, 4, 1]
        assert timeline_ui.timeline.get_hand_set_bars() == [1]

        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.beat.set_pattern", timeline_ui, pattern="4")
        assert timeline_ui.timeline.beats_in_measure == [4, 3, 4, 1]

        with patch_yes_or_no_dialog(True):
            with undoable():
                commands.execute("timeline.beat.set_pattern", timeline_ui, pattern="4")
        assert timeline_ui.timeline.beats_in_measure == [4, 4, 4]

    def test_hand_set_bar_matching_new_pattern_is_not_asked_about(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(12))
        timeline_ui = tluis[0]
        self._set_second_bar_to_three_beats(timeline_ui)

        # Declining would leave the pattern unchanged, so this shows no prompt.
        with patch_yes_or_no_dialog(False):
            commands.execute("timeline.beat.set_pattern", timeline_ui, pattern="4 3")

        assert timeline_ui.timeline.beat_pattern == "4 3"
        assert timeline_ui.timeline.beats_in_measure == [4, 3, 4, 1]

    def test_dialog_highlights_bars_that_change(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(12))
        self._set_second_bar_to_three_beats(tluis[0])
        seen = {}

        def record(dialog):
            seen["rows"] = dialog.get_table_rows()
            seen["highlighted"] = dialog.get_highlighted_rows()

        with patch_beat_pattern_dialog("4", on_exec=record):
            commands.execute("timeline.beat.set_pattern", tluis[0])

        assert seen["rows"][0][0] == "1–3"
        assert seen["highlighted"] == {0}
        # What the dialog showed is applied, with no question asked.
        assert tluis[0].timeline.beats_in_measure == [4, 4, 4]

    def test_context_menu_has_set_pattern(self, tluis):
        add_beat_timeline_with_pattern("4")
        menu = BeatTimelineUIContextMenu(tluis[0], 0, 0)

        assert "timeline.beat.set_pattern" in get_command_names(menu)

    def test_set_pattern_from_context_menu(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(6))
        menu = BeatTimelineUIContextMenu(tluis[0], 0, 0)
        action = next(
            a
            for a in menu.actions()
            if getattr(a, "command_name", None) == "timeline.beat.set_pattern"
        )

        with patch_beat_pattern_dialog("3"):
            action.trigger()

        assert tluis[0].timeline.beats_in_measure == [3, 3]


def time_signatures(timeline):
    return [
        (format_units([meter.numerator]), meter.denominator)
        for meter in timeline.measure_meters
    ]


class TestEditBarsDialog:
    @staticmethod
    def edit_bars(timeline_ui, edit):
        with patch_bars_dialog(edit):
            commands.execute("timeline.beat.set_pattern", timeline_ui)

    def test_a_bar_with_another_number_of_beats_has_a_row_of_its_own(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(11))
        tluis[0].select_element(tluis[0][5])
        commands.execute("timeline.beat.set_amount_in_measure", amount=3)
        seen = {}

        def record(dialog):
            seen["rows"] = dialog.get_table_rows()
            seen["text"] = dialog.text

        self.edit_bars(tluis[0], record)

        assert seen["rows"] == [
            ("1", "4/4", "1 1 1 1"),
            ("2", "3/4", "1 1 1"),
            ("3", "4/4", "1 1 1 1"),
        ]
        assert seen["text"] == "4/4"
        # Pressing OK on what is shown changes nothing.
        assert tluis[0].timeline.beats_in_measure == [4, 3, 4]
        assert tluis[0].timeline.beat_pattern == "4/4"

    def test_correcting_a_bar_moves_the_later_bars(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(13))
        tluis[0].select_element(tluis[0][0])
        commands.execute("timeline.beat.set_amount_in_measure", amount=5)
        assert tluis[0].timeline.beats_in_measure == [5, 4, 4]

        with undoable():
            self.edit_bars(
                tluis[0],
                lambda dialog: edit_bars_dialog_cell(dialog, 0, TAPS_COLUMN, "1 1 1 1"),
            )

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [4, 4, 4, 1]
        assert timeline.beat_pattern == "4/4"

    def test_changing_a_time_signature(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(12))

        def edit(dialog):
            edit_bars_dialog_cell(dialog, 0, BARS_COLUMN, "1")
            edit_bars_dialog_cell(dialog, 0, TIME_SIGNATURE_COLUMN, "6/8(3 3)")

        with undoable():
            self.edit_bars(tluis[0], edit)

        # The three bars now take two beats each, and the beats left over
        # make bars from the pattern.
        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [2, 2, 2, 4, 2]
        # The last bar has two of its four beats so far.
        assert time_signatures(timeline) == [("6", 8)] * 3 + [("4", 4), ("2", 4)]

    def test_numbering_a_repeat(self, tluis, tmp_path):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(24))

        with undoable():
            self.edit_bars(
                tluis[0],
                lambda dialog: edit_bars_dialog_cell(
                    dialog, 0, BARS_COLUMN, "1-3, 1-3"
                ),
            )

        assert tluis[0].timeline.measure_numbers == [1, 2, 3, 1, 2, 3]
        save_and_reopen(tmp_path)
        assert tluis[0].timeline.measure_numbers == [1, 2, 3, 1, 2, 3]

    def test_rows_reflect_the_numbers(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(16))
        tluis[0].timeline.set_measure_numbers([1, 2, 1, 2])
        seen = {}

        self.edit_bars(
            tluis[0], lambda dialog: seen.update(rows=dialog.get_table_rows())
        )

        assert [row[0] for row in seen["rows"]] == ["1–2", "1–2"]
        assert tluis[0].timeline.measure_numbers == [1, 2, 1, 2]

    def test_bars_not_tapped_yet_are_listed(self, tluis):
        add_beat_timeline_with_pattern("2[4/4] 3/4 2/4")
        add_beats(range(5))
        seen = {}

        def record(dialog):
            seen["tapped"] = [row.is_tapped for row in dialog.rows]
            seen["text"] = dialog.text

        self.edit_bars(tluis[0], record)

        assert seen["tapped"] == [True, False, False]
        assert seen["text"] == "2[4/4] 3/4 2/4"

    def test_ok_without_changes_keeps_the_pattern_for_later_bars(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(9))
        # A pickup, which the pattern doesn't plan.
        tluis[0].select_element(tluis[0][0])
        commands.execute("timeline.beat.set_amount_in_measure", amount=1)
        assert tluis[0].timeline.beats_in_measure == [1, 4, 4]

        self.edit_bars(tluis[0], lambda dialog: None)

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "4/4"
        assert timeline.beats_in_measure == [1, 4, 4]
        add_beats(range(9, 17))
        assert timeline.beats_in_measure == [1, 4, 4, 4, 4]

    def test_assumed_time_signatures_stay_assumed(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))

        self.edit_bars(tluis[0], lambda dialog: None)

        assert all(m.is_assumed for m in tluis[0].timeline.measure_meters)


class TestPatternWithTimeSignatures:
    def test_tapping_follows_the_time_signatures(self, tluis):
        add_beat_timeline_with_pattern("2[4/4] 3/4 2[4/4(3/2 3/2 1)]")
        add_beats(range(4 + 4 + 3 + 3 + 3))

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [4, 4, 3, 3, 3]
        assert time_signatures(timeline) == [
            ("4", 4),
            ("4", 4),
            ("3", 4),
            ("4", 4),
            ("4", 4),
        ]
        values = [m.beat_values for m in timeline.measure_meters]
        assert values[3] == (F(3, 2), F(3, 2), F(1))

    def test_beat_units_go_where_the_time_signature_changes(self, tluis):
        add_beat_timeline_with_pattern("2[4/4] 6/8(3 3)")
        add_beats(range(10))

        timeline = tluis[0].timeline
        units = [
            (
                timeline.get_beat_index(timeline.get_component(u.beat_id)),
                u.denominator,
                u.units,
                u.assumed,
            )
            for u in timeline.beat_units
        ]
        assert units == [(0, 4, "1", False), (8, 8, "3", False)]

    def test_tapping_past_the_pattern_starts_it_again(self, tluis):
        add_beat_timeline_with_pattern("4/4 3/4")
        add_beats(range(4 + 3 + 4 + 3))

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [4, 3, 4, 3]
        assert time_signatures(timeline) == [("4", 4), ("3", 4), ("4", 4), ("3", 4)]

    def test_a_time_signature_set_by_hand_carries_on_while_tapping(self, tluis):
        add_beat_timeline_with_pattern("2/4")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")

        add_beats(range(4, 6))

        assert time_signatures(tluis[0].timeline) == [("2", 4), ("6", 8), ("6", 8)]

    def test_numbers_of_beats_alone_are_assumed(self, tluis):
        add_beat_timeline_with_pattern("3")
        add_beats(range(6))

        timeline = tluis[0].timeline
        assert time_signatures(timeline) == [("3", 4), ("3", 4)]
        assert all(m.is_assumed for m in timeline.measure_meters)

    def test_written_time_signatures_are_not_assumed(self, tluis):
        add_beat_timeline_with_pattern("3/4")
        add_beats(range(6))

        assert not any(m.is_assumed for m in tluis[0].timeline.measure_meters)

    def test_fill_with_beats_follows_the_time_signatures(self, tluis, tilia_state):
        tilia_state.duration = 100
        add_beat_timeline_with_pattern("6/8(3 3) 2/4")

        with patch_fill_beat_timeline_dialog(
            tluis[0].timeline, BeatTimeline.FillMethod.BY_AMOUNT, 8
        ):
            commands.execute("timeline.beat.fill")

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [2, 2, 2, 2]
        assert time_signatures(timeline) == [("6", 8), ("2", 4), ("6", 8), ("2", 4)]

    def test_setting_the_pattern_remeasures_with_its_time_signatures(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(12))

        with undoable():
            commands.execute(
                "timeline.beat.set_pattern", tluis[0], pattern="6/8(3 3) 3/4(1 1 1)"
            )

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [2, 3, 2, 3, 2]
        assert time_signatures(timeline) == [
            ("6", 8),
            ("3", 4),
            ("6", 8),
            ("3", 4),
            ("6", 8),
        ]

    def test_time_signatures_survive_save_and_reopen(self, tluis, tmp_path):
        add_beat_timeline_with_pattern("2[4/4] 3/4")
        add_beats(range(11))

        save_and_reopen(tmp_path)

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "2[4/4] 3/4"
        assert time_signatures(timeline) == [("4", 4), ("4", 4), ("3", 4)]
        add_beats(range(11, 15))
        assert time_signatures(timeline)[-1] == ("4", 4)


class TestCreateDeleteBeat:
    def test_create_single(self, beat_tlui):
        beat_tlui.create_beat(0)

        assert len(beat_tlui) == 1

    def test_create_multiple(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        assert len(beat_tlui) == 3

    def test_delete(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_all_elements()

        commands.execute("timeline.component.delete")

        assert len(beat_tlui) == 0
        assert not beat_tlui.selected_elements

    def test_delete_update_next_measures_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        settings.set("beat_timeline", "display_measure_periodicity", 1)
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        assert get_displayed_measure_number(beat_tlui[0]) == "1"
        assert get_displayed_measure_number(beat_tlui[1]) == "2"

    def test_create_in_a_measure_moves_the_later_barlines(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        settings.set("beat_timeline", "display_measure_periodicity", 1)
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        commands.execute("media.seek", 0.5)
        commands.execute("timeline.beat.add")

        # Each measure keeps its one beat.
        assert [get_displayed_measure_number(beat) for beat in beat_tlui] == [
            "1",
            "2",
            "3",
            "4",
        ]

    def test_create_after_the_last_beat_numbers_the_new_measure(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        settings.set("beat_timeline", "display_measure_periodicity", 1)
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)

        commands.execute("media.seek", 2)
        commands.execute("timeline.beat.add")

        assert [get_displayed_measure_number(beat) for beat in beat_tlui] == [
            "1",
            "2",
            "3",
        ]

    def test_deleting_a_stray_tap_puts_the_later_barlines_back(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        # A stray tap at 1.5 makes every later bar start a beat early.
        add_beats([0, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        timeline = tluis[0].timeline
        assert [b.time for b in timeline if b.is_first_in_measure] == [0, 3, 7, 11]

        tluis[0].select_element(tluis[0][2])
        with undoable():
            commands.execute("timeline.component.delete")

        assert [b.time for b in timeline if b.is_first_in_measure] == [0, 4, 8]
        assert timeline.beats_in_measure == [4, 4, 4]

    def test_adding_a_missed_tap_puts_the_later_barlines_back(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        # Without a tap at 2, every later bar starts a beat late.
        add_beats([0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        timeline = tluis[0].timeline
        assert [b.time for b in timeline if b.is_first_in_measure] == [0, 5, 9]

        with undoable():
            add_beats([2])

        assert [b.time for b in timeline if b.is_first_in_measure] == [0, 4, 8]

    def test_a_time_signature_moves_with_its_bar(self, tluis):
        add_beat_timeline_with_pattern("2[2/4] 6/8(3 3)")
        add_beats(range(7))
        timeline = tluis[0].timeline
        assert time_signatures(timeline) == [("2", 4), ("2", 4), ("6", 8), ("1", 4)]

        tluis[0].select_element(tluis[0][1])
        with undoable():
            commands.execute("timeline.component.delete")

        assert time_signatures(timeline) == [("2", 4), ("2", 4), ("6", 8)]
        assert timeline.get_beat_unit_on_beat(timeline[4].id).denominator == 8
        assert not any(meter.is_conflicting for meter in timeline.measure_meters)


class TestSelect:
    def test_deselect_all_but_last(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        beat_tlui.select_all_elements()

        beat_tlui._deselect_all_but_last()

        assert beat_tlui.selected_elements == [beat_tlui[-1]]

    def test_deselect_all_but_first(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        beat_tlui.select_all_elements()

        beat_tlui._deselect_all_but_first()

        assert beat_tlui.selected_elements == [beat_tlui[0]]

    def test_on_right_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]

        beat_tlui.select_element(beat0)
        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat1]

        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat1]

    def test_on_left_arrow_press_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]

        beat_tlui.select_element(beat1)
        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]

        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]

    def test_on_right_arrow_press_more_than_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        beat2 = beat_tlui[2]
        beat3 = beat_tlui[3]

        beat_tlui.select_element(beat0)
        beat_tlui.select_element(beat1)
        beat_tlui.select_element(beat2)

        beat_tlui.on_horizontal_arrow_press("right")
        assert beat_tlui.selected_elements == [beat3]

    def test_on_left_arrow_press_more_than_one_element_selected(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        beat2 = beat_tlui[2]
        beat3 = beat_tlui[3]

        beat_tlui.select_element(beat1)
        beat_tlui.select_element(beat2)
        beat_tlui.select_element(beat3)

        beat_tlui.on_horizontal_arrow_press("left")
        assert beat_tlui.selected_elements == [beat0]


class TestGetBeat:
    def test_get_next_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        assert beat_tlui.get_next_element(beat0) == beat1
        assert beat_tlui.get_next_element(beat1) is None

    def test_get_previous_beat(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)

        beat0 = beat_tlui[0]
        beat1 = beat_tlui[1]
        assert beat_tlui.get_previous_element(beat1) == beat0
        assert beat_tlui.get_previous_element(beat0) is None


class TestCopyPaste:
    def test_get_copy_data_from_beat_uis(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)
        beat_tlui.create_beat(0.3)

        for beat in beat_tlui:
            beat_tlui.select_element(beat)

        copy_data = beat_tlui.get_copy_data_from_selected_elements()
        # The first beat carries the timeline's first beat unit.
        beat0_data = {
            "values": {},
            "context": {"time": 0},
            "beat_unit": {"denominator": 4, "units": "1", "assumed": True},
        }
        beat1_data = {
            "values": {},
            "context": {"time": 0.1},
        }
        beat2_data = {
            "values": {},
            "context": {"time": 0.2},
        }
        beat3_data = {
            "values": {},
            "context": {"time": 0.3},
        }
        assert beat0_data in copy_data
        assert beat1_data in copy_data
        assert beat2_data in copy_data
        assert beat3_data in copy_data

    def test_paste_single_into_selected_elements(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui.elements[0])

        tl_state0 = beat_tlui.timeline.get_state()

        commands.execute("timeline.component.copy")
        commands.execute("timeline.component.paste")

        tl_state1 = beat_tlui.timeline.get_state()

        assert tl_state0 == tl_state1

    def test_paste_single_into_timeline(self, beat_tlui, tluis):
        beat_tlui.create_beat(10)
        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.component.copy")

        beat_tlui.deselect_element(beat_tlui[0])

        commands.execute("timeline.component.paste")

        assert len(beat_tlui) == 2
        assert beat_tlui[0].time == 0

    def test_pasted_beats_keep_the_measures_lengths(self, tluis):
        add_beat_timeline_with_pattern("4/4")
        add_beats(range(10, 22))
        for beat_ui in tluis[0][0:2]:
            tluis[0].select_element(beat_ui)
        commands.execute("timeline.component.copy")
        tluis[0].deselect_all_elements()
        commands.execute("media.seek", 14.5)

        with undoable():
            commands.execute("timeline.component.paste")

        # As adding them one at a time would: the second measure keeps its
        # four beats, so the barlines after it move.
        starts = [b.time for b in tluis[0].timeline if b.is_first_in_measure]
        assert starts == [10, 14, 16, 20]

    def test_paste_multiple_into_timeline(self, beat_tlui, tluis):
        beat_tlui.create_beat(10)
        beat_tlui.create_beat(11)
        beat_tlui.create_beat(12)
        beat_tlui.create_beat(13)

        beat_tlui.select_all_elements()

        commands.execute("timeline.component.copy")

        beat_tlui.deselect_all_elements()

        commands.execute("timeline.component.paste")

        assert len(beat_tlui) == 8
        assert beat_tlui[0].time == 0
        assert beat_tlui[1].time == 1
        assert beat_tlui[2].time == 2
        assert beat_tlui[3].time == 3


class TestOther:
    def test_get_measure_number(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.timeline.recalculate_measures()

        expected_measure_numbers = {
            0: 1,
            1: 1,
            2: 1,
            3: 2,
            4: 2,
            5: 2,
            6: 3,
            7: 3,
            8: 3,
            9: 4,
            10: 4,
            11: 4,
        }

        for i, beat in enumerate(sorted(beat_tlui)):
            assert beat.get_data("measure") == expected_measure_numbers[i]


DUMMY_MEASURE_NUMBER = 11


class TestSetMeasureNumber:
    @staticmethod
    def _set_measure_number(number=DUMMY_MEASURE_NUMBER):
        """Assumes there a beat in the measure is selected"""
        with patch_ask_for_int_dialog(True, number):
            commands.execute("timeline.beat.set_measure_number")

    def test_set_measure_number_single_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_twice(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        self._set_measure_number(101)
        assert beat_tlui.timeline.measure_numbers[0] == 101

    def test_set_measure_number_multiple_measures(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[3])
        self._set_measure_number()

        assert beat_tlui.timeline.measure_numbers[1] == DUMMY_MEASURE_NUMBER

    def test_set_measure_number_not_first_beat_in_measure(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [3]

        for i in range(12):
            beat_tlui.create_beat(i / 10)

        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number()

        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_undo_set_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("edit.undo")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_redo_set_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_undo_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        commands.execute("edit.undo")
        assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_redo_reset_measure_number(self, beat_tlui):
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])
        self._set_measure_number()
        commands.execute("timeline.beat.reset_measure_number")
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert beat_tlui.timeline.measure_numbers[0] == 1

    def test_reset_measure_number_hides_label_set_more_than_once(self, beat_tlui):
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            beat_tlui.create_beat(i)

        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number()
        self._set_measure_number()
        assert get_displayed_measure_number(beat_tlui[1]) == str(DUMMY_MEASURE_NUMBER)

        commands.execute("timeline.beat.reset_measure_number")

        assert get_displayed_measure_number(beat_tlui[1]) == ""

    def test_forced_measure_past_the_end_is_dropped_when_beats_are_deleted(
        self, beat_tlui
    ):
        settings.set("beat_timeline", "display_measure_periodicity", 4)
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(6):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")

        # Forcing measure 6 before measure 2 leaves the list unsorted.
        beat_tlui.select_element(beat_tlui[5])
        self._set_measure_number(6)
        beat_tlui.deselect_all_elements()
        beat_tlui.select_element(beat_tlui[1])
        self._set_measure_number(2)
        beat_tlui.deselect_all_elements()

        for i in range(3, 6):
            beat_tlui.select_element(beat_tlui[i])
        commands.execute("timeline.component.delete")
        for i in range(3, 6):
            commands.execute("media.seek", i)
            commands.execute("timeline.beat.add")

        assert get_displayed_measure_number(beat_tlui[5]) == ""

    def test_measure_zero_number_is_not_displayed(self, beat_tlui):
        settings.set("beat_timeline", "display_measure_periodicity", 2)
        beat_tlui.timeline.beat_pattern = [1]

        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)
        beat_tlui.create_beat(3)

        beat_tlui.timeline.recalculate_measures()

        beat_tlui.select_element(beat_tlui[0])

        self._set_measure_number(0)

        displayed_measure = [get_displayed_measure_number(b) for b in beat_tlui]
        assert displayed_measure == ["", "1", "", "3"]

    def test_set_measure_number_undo_redo_and_reload(self, beat_tlui, tluis, tmp_path):
        """Setting a measure number is undoable/redoable and survives
        a save/reopen round trip."""
        commands.execute("timeline.beat.add")
        beat_tlui.select_element(beat_tlui[0])

        with undoable():
            self._set_measure_number()
            assert beat_tlui.timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

        @reloadable(tmp_path / "file.tla")
        def check_measure_number():
            assert tluis[0].timeline.measure_numbers[0] == DUMMY_MEASURE_NUMBER

    def test_reset_measure_number_is_undoable(self, beat_tlui):
        """Undoing a measure-number reset must restore the custom
        number exactly (full app-state comparison, not just the target
        attribute), and redoing must reset it again. Uses a non-first
        measure so the reset also exercises the propagation cascade to
        later measures, not just the hardcoded "measure 0 resets to 1"
        branch."""
        beat_tlui.timeline.beat_pattern = [3]
        for i in range(12):
            beat_tlui.create_beat(i / 10)
        beat_tlui.timeline.recalculate_measures()

        beat_tlui.select_element(beat_tlui[3])
        self._set_measure_number()

        with undoable():
            commands.execute("timeline.beat.reset_measure_number")
            assert beat_tlui.timeline.measure_numbers[1] == 2


class TestActions:
    def test_inspect(self, qtui, beat_tlui, tilia_state):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for element in beat_tlui:
            beat_tlui.select_element(element)

        commands.execute("timeline.element.inspect")

        assert tilia_state.is_window_open(qtui, WindowKind.INSPECT)

        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_distribute_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)
        beat_tlui.create_beat(3)
        beat_tlui.create_beat(8)

        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.distribute")

        assert beat_tlui[1].get_data("time") == 2
        assert beat_tlui[2].get_data("time") == 4
        assert beat_tlui[3].get_data("time") == 6

    def test_distribute_beats_on_last_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)

        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.distribute")

        assert beat_tlui[0].get_data("time") == 0
        assert beat_tlui[1].get_data("time") == 1


class TestSetBeatAmountInMeasure:
    def test_the_measure_being_tapped_can_still_fill_up(self, beat_tlui):
        add_beats(range(10))
        assert beat_tlui.timeline.beats_in_measure == [4, 4, 2]
        beat_tlui.select_element(beat_tlui[0])

        commands.execute("timeline.beat.set_amount_in_measure", amount=3)

        assert beat_tlui.timeline.beats_in_measure == [3, 4, 3]
        add_beats(range(10, 13))
        assert beat_tlui.timeline.beats_in_measure == [3, 4, 4, 2]
        assert beat_tlui.timeline.get_hand_set_bars() == [0]

    def test_measures_made_from_the_pattern_get_its_time_signatures(self, tluis):
        add_beat_timeline_with_pattern("2/4 6/8(3 3)")
        add_beats(range(8))
        tluis[0].select_element(tluis[0][0])

        commands.execute("timeline.beat.set_amount_in_measure", amount=1)

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [1, 2, 2, 2, 1]
        assert time_signatures(timeline) == [
            ("1", 4),
            ("6", 8),
            ("2", 4),
            ("6", 8),
            ("1", 4),
        ]

    def test_set_beat_amount_in_measure(self, beat_tlui):
        beat_tlui.create_beat(0)

        beat_tlui.select_element(beat_tlui[0])

        beat_tlui.timeline.set_beat_amount_in_measure = MagicMock()
        with patch_ask_for_int_dialog(True, 11):
            commands.execute("timeline.beat.set_amount_in_measure")

        beat_tlui.timeline.set_beat_amount_in_measure.assert_called_with(0, 11)

    def test_updates_measure_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        settings.set("beat_timeline", "display_measure_periodicity", 1)
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        beat_tlui.select_element(beat_tlui[0])

        with patch_ask_for_int_dialog(True, 2):
            commands.execute("timeline.beat.set_amount_in_measure")

        assert [get_displayed_measure_number(b) for b in beat_tlui] == ["1", "", "2"]

    def test_add_beat_when_last_measure_is_fuller_than_beat_pattern(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [4]
        for i in range(24):
            beat_tlui.create_beat(i / 10)

        # give a middle measure one beat more than the beat pattern prescribes
        beat_tlui.select_element(beat_tlui[16])
        commands.execute("timeline.beat.set_amount_in_measure", amount=5)

        # then make that measure the last one
        beat_tlui.deselect_all_elements()
        for element in list(beat_tlui)[-3:]:
            beat_tlui.select_element(element)
        commands.execute("timeline.component.delete")
        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4, 4, 5]

        commands.execute("media.seek", 3.0)
        commands.execute("timeline.beat.add")

        assert len(beat_tlui) == 22
        assert beat_tlui.timeline.beats_in_measure == [4, 4, 4, 4, 5, 1]


class TestFillWithBeats:
    @pytest.fixture(autouse=True)
    def setup(self, beat_tlui):
        # required for undoable actions
        post(Post.APP_STATE_RECORD, "test")

    def test_by_amount(self, beat_tlui):
        with patch_fill_beat_timeline_dialog(
            beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100
        ):
            with undoable():
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 100

    def test_by_interval(self, beat_tlui, tilia_state):
        interval = 0.5
        amount = int(tilia_state.duration / interval)
        with patch_fill_beat_timeline_dialog(
            beat_tlui.timeline, BeatTimeline.FillMethod.BY_INTERVAL, interval
        ):
            with undoable():
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == amount
        assert beat_tlui[1].get_data("time") - beat_tlui[0].get_data("time") == interval

    def test_accept_delete_existing_beats(self, beat_tlui):
        commands.execute("timeline.beat.add")

        with patch_fill_beat_timeline_dialog(
            beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100
        ):
            with patch_yes_or_no_dialog(True):
                with undoable():
                    commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 100

    def test_reject_delete_existing_beats(self, beat_tlui):
        beat_tlui.create_beat(0)
        with patch_fill_beat_timeline_dialog(
            beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, 100
        ):
            with patch_yes_or_no_dialog(False):
                commands.execute("timeline.beat.fill")

        assert len(beat_tlui) == 1

    def test_refilling_starts_the_measures_over(self, beat_tlui):
        def fill(amount):
            with patch_fill_beat_timeline_dialog(
                beat_tlui.timeline, BeatTimeline.FillMethod.BY_AMOUNT, amount
            ):
                commands.execute("timeline.beat.fill")

        fill(12)
        beat_tlui.select_element(beat_tlui[4])
        with patch_ask_for_int_dialog(True, 3):
            commands.execute("timeline.beat.set_amount_in_measure")
        beat_tlui.deselect_all_elements()
        beat_tlui.select_element(beat_tlui[7])
        with patch_ask_for_int_dialog(True, 10):
            commands.execute("timeline.beat.set_measure_number")
        assert beat_tlui.timeline.measure_numbers == [1, 2, 10, 11]

        with patch_yes_or_no_dialog(True):
            with undoable():
                fill(8)

        assert beat_tlui.timeline.beats_in_measure == [4, 4]
        assert beat_tlui.timeline.measure_numbers == [1, 2]
        assert beat_tlui.timeline.get_time_by_measure(3) == []


class TestUndoRedo:
    def test_undo_redo_add_beat(self, beat_tlui, tluis):
        commands.execute("media.seek", 10)
        commands.execute("timeline.beat.add")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 0

        commands.execute("edit.redo")
        assert len(beat_tlui) == 1

    def test_undo_redo_delete_beat_multiple_beats(self, beat_tlui, tluis):
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(0.1)
        beat_tlui.create_beat(0.2)

        for beat_ui in beat_tlui:
            beat_tlui.select_element(beat_ui)

        post(Post.APP_STATE_RECORD, "test state")

        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 3

        commands.execute("edit.redo")
        assert len(beat_tlui) == 0

    def test_undo_redo_delete_beat(self, beat_tlui, tluis):
        # 'tlui_clct' is needed as it subscriber to toolbar event
        # and forwards it to beat timeline

        commands.execute("timeline.beat.add")

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")
        assert len(beat_tlui) == 1

        commands.execute("edit.redo")
        assert len(beat_tlui) == 0

    def test_undo_redo_updates_displayed_measure_numbers(self, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        settings.set("beat_timeline", "display_measure_periodicity", 1)
        beat_tlui.create_beat(0)
        beat_tlui.create_beat(1)
        beat_tlui.create_beat(2)

        post(Post.APP_STATE_RECORD, "test")

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")

        commands.execute("edit.undo")

        assert [get_displayed_measure_number(beat_ui) for beat_ui in beat_tlui] == [
            "1",
            "2",
            "3",
        ]

        commands.execute("edit.redo")

        assert [get_displayed_measure_number(beat_ui) for beat_ui in beat_tlui] == [
            "1",
            "2",
        ]


class TestTimelineUIContextMenu:
    def test_has_no_height_set_action(self, beat_tlui, tluis):
        context_menu = beat_tlui.CONTEXT_MENU_CLASS(beat_tlui, 0, 0)

        assert get_qaction("timeline.set_height") not in context_menu.actions()


class TestElementContextMenu:
    def test_has_cut(self, beat_tlui):
        commands.execute("timeline.beat.add", time=0)
        menu = BeatContextMenu(beat_tlui[0])
        assert "timeline.component.cut" in get_command_names(menu)

    def test_cut(self, beat_tlui):
        commands.execute("timeline.beat.add", time=0)
        commands.execute("timeline.beat.add", time=10)
        click_beat_ui(beat_tlui[0])

        menu = BeatContextMenu(beat_tlui[0])
        with undoable():
            get_command_action(menu, "timeline.component.cut").trigger()

        assert len(beat_tlui) == 1
        assert beat_tlui[0].get_data("time") == 10


class TestChangeBeatsInMeasureContextMenu:
    def test_context_menu_has_set_amount_in_measure(self, beat_tlui):
        beat_tlui.create_beat(0)
        menu = BeatContextMenu(beat_tlui[0])
        assert "timeline.beat.set_amount_in_measure" in get_command_names(menu)

    def test_change_3_to_8_beats_and_undo_redo(self, beat_tlui):
        # A timeline with 3 beats/measure; change one measure from 3 to 8
        # beats and undo/redo it. Regression test for a previously reported
        # crash on undo.
        beat_tlui.timeline.beat_pattern = [3]
        for t in range(6):
            commands.execute("timeline.beat.add", time=t)
        assert beat_tlui.timeline.beats_in_measure == [3, 3]

        beat_tlui.select_element(beat_tlui[0])
        with undoable():
            commands.execute("timeline.beat.set_amount_in_measure", amount=8)
        assert beat_tlui.timeline.beats_in_measure == [6]


class TestDistributeBeatsErrors:
    def test_distribute_from_last_beat_displays_error(self, beat_tlui, tilia_errors):
        for t in range(8):
            beat_tlui.create_beat(t)

        beat_tlui.select_element(beat_tlui[-1])
        commands.execute("timeline.beat.distribute")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_title("Distribute")
        assert beat_tlui.timeline.beats_in_measure == [4, 4]

    def test_distribute_measure_with_one_beat_displays_error(
        self, beat_tlui, tilia_errors
    ):
        # Most plausible reading: the only measure-with-one-beat case the app
        # actually flags is a trailing/incomplete last measure -
        # BeatTLComponentManager.distribute_beats only errors on
        # `measure_index == measure_count - 1`, so build a timeline whose
        # last measure has exactly one beat.
        for t in range(5):
            beat_tlui.create_beat(t)
        assert beat_tlui.timeline.beats_in_measure == [4, 1]

        beat_tlui.select_element(beat_tlui[4])
        commands.execute("timeline.beat.distribute")

        tilia_errors.assert_error()
        assert beat_tlui.timeline.beats_in_measure == [4, 1]


class TestSetBeatAmountInMeasureEdgeCases:
    def test_add_beat_after_oversized_measure_change(self, beat_tlui):
        for t in range(8):
            beat_tlui.create_beat(t)  # pattern [4] -> measures [4, 4]

        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.beat.set_amount_in_measure", amount=100)

        commands.execute("timeline.beat.add", time=8)
        assert len(beat_tlui) == 9

    def test_change_beats_starting_from_measure_with_one_beat(self, beat_tlui):
        # The one-beat measure being changed is not the last measure, so the
        # shortfall is absorbed from later measures instead of being
        # silently reverted.
        beat_tlui.timeline.beat_pattern = [1, 4]
        for t in range(5):
            commands.execute("timeline.beat.add", time=t)
        assert beat_tlui.timeline.beats_in_measure == [1, 4]

        beat_tlui.select_element(beat_tlui[0])
        with undoable():
            commands.execute("timeline.beat.set_amount_in_measure", amount=2)
        assert beat_tlui.timeline.beats_in_measure == [2, 3]


class TestFillWithBeatsIntervalEdgeCases:
    @pytest.mark.parametrize(
        "pre_existing_beats, interval",
        [
            pytest.param(0, 0.5, id="empty-timeline"),
            pytest.param(1, 0.5, id="non-empty-timeline"),
            pytest.param(
                0,
                0,
                id="interval-zero",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "BeatTimeline.fill_with_beats divides the media "
                        "duration by the interval unconditionally "
                        "(tilia/timelines/beat/timeline.py:705), so an "
                        "interval of 0 raises ZeroDivisionError instead of "
                        "being refused."
                    ),
                ),
            ),
        ],
    )
    def test_fill_by_interval(
        self, beat_tlui, tilia_state, pre_existing_beats, interval
    ):
        for t in range(pre_existing_beats):
            commands.execute("timeline.beat.add", time=t)

        response = (
            True,
            (beat_tlui.timeline, BeatTimeline.FillMethod.BY_INTERVAL, interval),
        )
        with Serve(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, response):
            with patch_yes_or_no_dialog(True):
                with undoable():
                    commands.execute("timeline.beat.fill")

        amount = int(tilia_state.duration / interval)
        assert len(beat_tlui) == amount


class TestDragBeatLimits:
    def test_drag_beyond_next_beat_cannot_pass_it(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)
        commands.execute("timeline.beat.add", time=20)
        commands.execute("timeline.beat.add", time=30)

        click_beat_ui(beat_tlui[1])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(40), 0)
            assert beat_tlui[1].get_data("time") < 30

    def test_drag_beyond_previous_beat_cannot_pass_it(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)
        commands.execute("timeline.beat.add", time=20)
        commands.execute("timeline.beat.add", time=30)

        click_beat_ui(beat_tlui[1])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0), 0)
            assert beat_tlui[1].get_data("time") > 10

    def test_drag_beyond_timeline_end_is_clamped(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=90)

        click_beat_ui(beat_tlui[0])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(100) + 200, 0)
            assert beat_tlui[0].get_data("time") == 100

    def test_drag_beyond_timeline_start_is_clamped(self, beat_tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute("timeline.beat.add", time=10)

        click_beat_ui(beat_tlui[0])
        with undoable():
            drag_mouse_in_timeline_view(time_x_converter.get_x_by_time(0) - 200, 0)
            assert beat_tlui[0].get_data("time") == 0


def set_beat_unit(
    timeline_ui, measure_index, denominator, units, only_this_measure=False
):
    """
    Gives a measure a beat unit, as editing its time signature in the
    inspector does, and records the state, so it can be undone.
    """
    timeline_ui.timeline.set_beat_unit(
        measure_index, denominator, units, only_this_measure
    )
    post(Post.APP_STATE_RECORD, "set beat unit")


def newest_beat_unit_ui(timeline_ui):
    """The beat unit on the latest beat, i.e. the one a test set last."""
    timeline = timeline_ui.timeline
    return timeline_ui.get_element(timeline.beat_units[-1].id)


def assert_only_the_default_beat_unit(timeline):
    """Every timeline with beats keeps a beat unit on its first beat."""
    assert [
        (timeline.get_component(u.beat_id), u.denominator, u.units)
        for u in timeline.beat_units
    ] == [(timeline[0], 4, "1")]


def label_texts(labels):
    return [(lb.spec.numerator, lb.spec.denominator) for lb in labels]


def all_labels(timeline_ui):
    labels = timeline_ui.default_time_signature_labels + [
        lb for u in timeline_ui.beat_unit_uis for lb in u.labels
    ]
    return sorted(labels, key=lambda lb: lb.measure_index)


class TestTimeSignatures:
    def test_new_timeline_shows_time_signatures(self, tluis):
        add_beat_timeline_with_pattern("4")

        timeline_ui = tluis[0]
        assert timeline_ui.get_data("show_time_signatures")
        assert timeline_ui.get_data("height") == (
            settings.get("beat_timeline", "default_height") + TIME_SIGNATURE_BAND_HEIGHT
        )

    def test_default_label_on_first_measure_only(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))

        labels = all_labels(tluis[0])
        assert label_texts(labels) == [("4", "4")]
        assert labels[0].measure_index == 0

    def test_label_where_bar_length_changes(self, tluis):
        add_beat_timeline_with_pattern("4 3")
        add_beats(range(11))

        labels = all_labels(tluis[0])
        assert label_texts(labels) == [("4", "4"), ("3", "4"), ("4", "4")]

    def test_beat_unit_label(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")

        first_ui = tluis[0].get_element(tluis[0].timeline.beat_units[0].id)
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        assert label_texts(first_ui.labels) == [("2", "4")]
        assert label_texts(beat_unit_ui.labels) == [("6", "8")]
        assert tluis[0].default_time_signature_labels == []

    def test_label_where_beat_unit_starts_without_changing_signature(self, tluis):
        add_beat_timeline_with_pattern("4 2")
        add_beats(range(6))
        # 4/4 then 4/4 again: tapped in 4, then in 2.
        set_beat_unit(tluis[0], 1, 4, "2")

        labels = all_labels(tluis[0])
        assert label_texts(labels) == [("4", "4"), ("4", "4")]

    def test_whole_and_fraction_numerator(self, tluis):
        add_beat_timeline_with_pattern("13")
        add_beats(range(13))
        set_beat_unit(tluis[0], 0, 4, "1/3")

        assert label_texts(all_labels(tluis[0])) == [("4 1/3", "4")]

    def test_twelve_triplet_taps_show_four_four(self, tluis):
        add_beat_timeline_with_pattern("12")
        add_beats(range(12))
        set_beat_unit(tluis[0], 0, 4, "1/3")

        assert label_texts(all_labels(tluis[0])) == [("4", "4")]

    def test_label_is_centered_on_the_downbeat(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")

        # The first label would reach into the left margin, so it is checked
        # separately below.
        (label,) = newest_beat_unit_ui(tluis[0]).labels
        assert label.rect().center().x() == pytest.approx(
            time_x_converter.get_x_by_time(2)
        )

    def test_labels_stay_out_of_the_margins(self, tluis, tilia_state):
        add_beat_timeline_with_pattern("1")
        add_beats([0, tilia_state.duration])
        set_beat_unit(tluis[0], 1, 8, "1")

        first = all_labels(tluis[0])[0]
        (last,) = newest_beat_unit_ui(tluis[0]).labels
        assert first.body.x() == get(Get.LEFT_MARGIN_X)
        assert last.body.x() + last.body.width == get(Get.RIGHT_MARGIN_X)

    def test_labels_follow_zoom(self, tluis, tilia_state):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        before = beat_unit_ui.labels[0].rect().left()

        commands.execute("view.zoom.in")

        assert beat_unit_ui.labels[0].rect().left() > before

    def test_labels_follow_dragged_downbeat(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")

        tluis[0].timeline.set_component_data(tluis[0].timeline[2].id, "time", 2.5)

        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        assert beat_unit_ui.labels[0].rect().center().x() == pytest.approx(
            time_x_converter.get_x_by_time(2.5)
        )

    def test_conflicting_beat_units_are_red(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))
        timeline = tluis[0].timeline
        for index, denominator in [(4, 8), (5, 2)]:
            timeline.create_component(
                ComponentKind.BEAT_UNIT,
                beat_id=timeline[index].id,
                denominator=denominator,
                units="1",
            )

        label = all_labels(tluis[0])[1]
        assert label.spec.state == LabelState.CONFLICTING
        assert label.toolTip()

    def test_ambiguous_fit_is_amber(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(5))
        set_beat_unit(tluis[0], 0, 4, "2+3")

        labels = all_labels(tluis[0])
        assert [lb.spec.state for lb in labels] == [
            LabelState.NORMAL,
            LabelState.AMBIGUOUS,
        ]
        assert labels[1].toolTip() == BEAT_UNIT_AMBIGUOUS_TOOLTIP.format(
            3, "2+3", "2+3+2"
        )

    def test_clicking_a_label_selects_its_beat_unit(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])

        click_time_signature_label(tluis[0], beat_unit_ui.labels[0])

        assert tluis[0].selected_elements == [beat_unit_ui]
        assert beat_unit_ui.labels[0].pen().style() != Qt.PenStyle.NoPen

    def test_only_the_clicked_label_is_outlined(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        assert len(beat_unit_ui.labels) > 2

        click_time_signature_label(tluis[0], beat_unit_ui.get_label(2))

        outlined = [
            lb.measure_index
            for lb in beat_unit_ui.labels
            if lb.pen().style() != Qt.PenStyle.NoPen
        ]
        assert outlined == [2]

        click_time_signature_label(tluis[0], beat_unit_ui.get_label(1))
        outlined = [
            lb.measure_index
            for lb in beat_unit_ui.labels
            if lb.pen().style() != Qt.PenStyle.NoPen
        ]
        assert outlined == [1]

    def test_outline_goes_when_deselected(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        click_time_signature_label(tluis[0], beat_unit_ui.labels[0])

        tluis[0].deselect_all_elements()

        assert all(lb.pen().style() == Qt.PenStyle.NoPen for lb in beat_unit_ui.labels)

    def test_selected_without_a_click_outlines_where_it_starts(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 1, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])

        tluis[0].select_element(beat_unit_ui)

        outlined = [
            lb.measure_index
            for lb in beat_unit_ui.labels
            if lb.pen().style() != Qt.PenStyle.NoPen
        ]
        assert outlined == [1]

    def test_clicking_an_inherited_label_selects_the_governing_beat_unit(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inherited = beat_unit_ui.get_label(1)
        assert inherited is not None

        click_time_signature_label(tluis[0], inherited)

        assert tluis[0].selected_elements == [beat_unit_ui]

    def test_first_label_selects_the_first_beats_beat_unit(self, tluis):
        # Every timeline with beats has a beat unit on its first beat, so no
        # label is left that can't be selected.
        add_beat_timeline_with_pattern("4")
        add_beats(range(4))
        first_ui = tluis[0].get_element(tluis[0].timeline.beat_units[0].id)

        click_time_signature_label(tluis[0], all_labels(tluis[0])[0])

        assert tluis[0].selected_elements == [first_ui]

    def test_hover_draws_line_to_the_beat(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])

        hover_time_signature_label(tluis[0], beat_unit_ui.get_label(1))

        line = beat_unit_ui.hover_line
        assert line is not None
        assert line.line().p2().x() == time_x_converter.get_x_by_time(0)

        hover_time_signature_label(tluis[0], beat_unit_ui.get_label(1), False)
        assert beat_unit_ui.hover_line is None

    def test_delete_beat_unit_through_its_label(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        click_time_signature_label(tluis[0], beat_unit_ui.labels[0])

        with undoable():
            commands.execute("timeline.component.delete")

        assert_only_the_default_beat_unit(tluis[0].timeline)
        assert label_texts(all_labels(tluis[0])) == [("2", "4")]

    def test_beat_units_do_not_count_as_beats(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")

        assert len(tluis[0]) == 4
        assert all(isinstance(e, BeatUI) for e in tluis[0])

    def test_select_all_and_arrows_skip_beat_units(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")

        tluis[0].select_all_elements()
        assert all(isinstance(e, BeatUI) for e in tluis[0].selected_elements)

        tluis[0].deselect_all_elements()
        tluis[0].select_element(tluis[0][3])
        press_key("Right")
        assert tluis[0].selected_elements == [tluis[0][3]]

    def test_toggle_hides_labels_and_shrinks_timeline(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "1")
        height = tluis[0].get_data("height")

        with undoable():
            commands.execute("timeline.beat.toggle_time_signatures", tluis[0])

        assert not tluis[0].get_data("show_time_signatures")
        assert tluis[0].get_data("height") == height - TIME_SIGNATURE_BAND_HEIGHT
        assert all_labels(tluis[0]) == []

        commands.execute("timeline.beat.toggle_time_signatures", tluis[0])
        assert tluis[0].get_data("height") == height
        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("2", "8")]

    def test_toggle_keeps_a_height_set_by_hand(self, tluis):
        add_beat_timeline_with_pattern("4")
        commands.execute("timeline.set_height", tluis[0], height=100)

        commands.execute("timeline.beat.toggle_time_signatures", tluis[0])

        assert tluis[0].get_data("height") == 100 - TIME_SIGNATURE_BAND_HEIGHT

    def test_toggle_in_context_menu(self, tluis):
        add_beat_timeline_with_pattern("4")
        menu = BeatTimelineUIContextMenu(tluis[0], 0, 0)

        assert "timeline.beat.toggle_time_signatures" in get_command_names(menu)

    def test_toggle_from_context_menu(self, tluis):
        add_beat_timeline_with_pattern("4")
        menu = BeatTimelineUIContextMenu(tluis[0], 0, 0)
        action = next(
            a
            for a in menu.actions()
            if getattr(a, "command_name", None)
            == "timeline.beat.toggle_time_signatures"
        )

        action.trigger()

        assert not tluis[0].get_data("show_time_signatures")

    def test_hidden_by_default_for_timelines_without_the_setting(self, beat_tlui):
        # e.g. timelines from files saved before time signatures existed.
        beat_tlui.create_beat(0)

        assert not beat_tlui.get_data("show_time_signatures")
        assert all_labels(beat_tlui) == []

    def test_beat_units_survive_save_and_reopen(self, tluis, tmp_path):
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))
        set_beat_unit(tluis[0], 1, 8, "2+1")

        save_and_reopen(tmp_path)

        timeline = tluis[0].timeline
        beat_unit = timeline.beat_units[-1]
        assert (beat_unit.denominator, beat_unit.units) == (8, "2+1")
        assert beat_unit.beat_id == timeline[2].id
        assert tluis[0].get_data("show_time_signatures")
        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("3", "8")]


class TestEditBarsCommand:
    @staticmethod
    def record_dialog(seen):
        def record(dialog):
            seen["rows"] = dialog.get_table_rows()
            seen["current_row"] = dialog.current_row

        return record

    def test_opens_the_dialog_at_the_selected_beats_measure(self, tluis):
        add_beat_timeline_with_pattern("2/4")
        add_beats(range(6))
        set_beat_unit(tluis[0], 1, 8, "3")
        # A beat in the middle of measure 3.
        tluis[0].select_element(tluis[0][5])
        seen = {}

        with patch_bars_dialog(self.record_dialog(seen)):
            commands.execute("timeline.beat.edit_bars")

        # The measure has a row of its own, apart from the alike one before.
        assert seen["rows"] == [
            ("1", "2/4", "1 1"),
            ("2", "6/8", "3 3"),
            ("3", "6/8", "3 3"),
        ]
        assert seen["current_row"] == 2

    def test_cancel_changes_nothing(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        tluis[0].select_element(tluis[0][0])

        with patch_beat_pattern_dialog(None):
            commands.execute("timeline.beat.edit_bars")

        assert_only_the_default_beat_unit(tluis[0].timeline)

    def test_editing_a_time_signature(self, tluis):
        add_beat_timeline_with_pattern("2/4")
        add_beats(range(6))
        tluis[0].select_element(tluis[0][2])

        def edit(dialog):
            edit_bars_dialog_cell(dialog, 0, BARS_COLUMN, "1, 2, 3")
            edit_bars_dialog_cell(dialog, 1, TIME_SIGNATURE_COLUMN, "6/8")

        with undoable():
            with patch_bars_dialog(edit):
                commands.execute("timeline.beat.edit_bars")

        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("6", "8"), ("2", "4")]
        assert tluis[0].timeline.beats_in_measure == [2, 2, 2]

    def test_double_clicking_a_label_opens_the_dialog_at_its_measure(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        seen = {}

        with patch_bars_dialog(self.record_dialog(seen)):
            click_time_signature_label(tluis[0], beat_unit_ui.get_label(2), double=True)

        assert seen["current_row"] == 2

    def test_beat_context_menu_has_edit_bars(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(4))

        menu = BeatContextMenu(tluis[0][0])

        assert "timeline.beat.edit_bars" in get_command_names(menu)
        assert "timeline.beat.set_beat_unit" not in get_command_names(menu)

    def test_edit_bars_from_beat_context_menu(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))
        tluis[0].select_element(tluis[0][0])
        action = get_command_action(
            BeatContextMenu(tluis[0][0]), "timeline.beat.edit_bars"
        )

        with patch_bars_dialog(
            lambda dialog: edit_bars_dialog_cell(
                dialog, 0, TIME_SIGNATURE_COLUMN, "8/8"
            )
        ):
            action.trigger()

        # Only the measure the dialog was opened at changes.
        assert label_texts(all_labels(tluis[0])) == [("8", "8"), ("4", "4")]

    def test_label_context_menu_items(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(4))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])

        names = get_command_names(BeatUnitContextMenu(beat_unit_ui))

        assert names == ["timeline.beat.edit_bars", "timeline.component.delete"]

    def test_delete_from_label_context_menu(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(4))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        click_time_signature_label(tluis[0], beat_unit_ui.labels[0])
        action = get_command_action(
            BeatUnitContextMenu(beat_unit_ui), "timeline.component.delete"
        )

        action.trigger()

        assert_only_the_default_beat_unit(tluis[0].timeline)

    def test_edit_bars_from_label_context_menu(self, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        with patch.object(BeatUnitContextMenu, "exec"):
            click_time_signature_label(
                tluis[0], beat_unit_ui.get_label(1), button="right"
            )
        action = get_command_action(
            BeatUnitContextMenu(beat_unit_ui), "timeline.beat.edit_bars"
        )
        seen = {}

        with patch_bars_dialog(self.record_dialog(seen)):
            action.trigger()

        assert seen["current_row"] == 1

    def test_deleting_the_beat_moves_its_beat_unit(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "1")
        tluis[0].select_element(tluis[0][4])

        with undoable():
            commands.execute("timeline.component.delete")

        beat_unit = tluis[0].timeline.beat_units[-1]
        assert beat_unit.beat_id == tluis[0].timeline[4].id

    def test_undo_restores_beat_unit_on_its_beat(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_id = tluis[0].timeline.beat_units[-1].beat_id

        commands.execute("edit.undo")
        assert_only_the_default_beat_unit(tluis[0].timeline)

        commands.execute("edit.redo")
        beat_unit = tluis[0].timeline.beat_units[-1]
        assert beat_unit.beat_id == beat_id
        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("6", "8")]


class TestTimeSignatureInspector:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    @staticmethod
    def open_inspector_for_label(timeline_ui, label, qtui):
        click_time_signature_label(timeline_ui, label)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    @staticmethod
    def type_into(widget, text):
        widget.selectAll()
        QTest.keyClicks(widget, text)
        QTest.keyClick(widget, Qt.Key.Key_Return)
        # The edit is applied from the event loop, once the mouse is released.
        QApplication.processEvents()

    def test_shows_values(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])

        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        widgets = inspector.field_name_to_widgets
        assert widgets["Time signature"][1].text() == "6/8"
        assert widgets["Taps"][1].text() == "3 3"
        assert widgets["Measure"][1].text() == "2"
        assert "Denominator" not in widgets

    def test_edit_until_next_change(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        with patch_beat_unit_scope_prompt("onward"):
            with undoable():
                self.type_into(
                    inspector.field_name_to_widgets["Time signature"][1], "2/8"
                )

        assert len(tluis[0].timeline.beat_units) == 2
        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("2", "8")]

    def test_the_measure_keeps_its_taps(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        with patch_beat_unit_scope_prompt("onward"):
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "6/8")

        timeline = tluis[0].timeline
        assert timeline.beats_in_measure == [2, 2]
        assert label_texts(all_labels(tluis[0])) == [("6", "8")]
        assert [m.beat_values for m in timeline.measure_meters] == [(3, 3), (3, 3)]

    def test_other_taps_are_refused(self, qtui, tluis, tilia_errors):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        self.type_into(
            inspector.field_name_to_widgets["Time signature"][1], "6/8(1 1 1 1 1 1)"
        )

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("This measure has 2 taps.")
        assert_only_the_default_beat_unit(tluis[0].timeline)

    def test_edit_this_measure_only(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        with patch_beat_unit_scope_prompt("measure"):
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "2/2")

        assert label_texts(all_labels(tluis[0])) == [("2", "4"), ("2", "2"), ("2", "8")]

    def test_cancelling_the_scope_question_changes_nothing(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        line_edit = inspector.field_name_to_widgets["Time signature"][1]

        # Ended by clicking away rather than Enter, which closes the
        # inspector, so the field can be seen going back.
        with patch_beat_unit_scope_prompt(None):
            line_edit.selectAll()
            QTest.keyClicks(line_edit, "2/8")
            line_edit.editingFinished.emit()
            QApplication.processEvents()

        assert tluis[0].timeline.beat_units[-1].units == "3"
        assert line_edit.text() == "6/8"

    def test_no_question_when_the_beat_unit_covers_one_measure(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        with patch_beat_unit_scope_prompt("onward") as prompts:
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "2/8")

        assert prompts == []
        assert tluis[0].timeline.beat_units[-1].units == "1"

    def test_edit_from_an_inherited_label_starts_there(self, qtui, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.get_label(2), qtui
        )

        # The next measure, a 3/8, isn't alike, so nothing asks how far the
        # edit goes, and it keeps its time signature.
        with patch_beat_unit_scope_prompt("onward") as shown:
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "2/4")

        assert shown == []
        assert label_texts(all_labels(tluis[0])) == [
            ("2", "8"),
            ("3", "8"),
            ("2", "4"),
            ("3", "8"),
        ]

    def test_onward_stops_where_the_time_signature_changes(self, qtui, tluis):
        add_beat_timeline_with_pattern("2[2/4] 3/4")
        add_beats(range(9))
        inspector = self.open_inspector_for_label(
            tluis[0], all_labels(tluis[0])[0], qtui
        )

        with patch_beat_unit_scope_prompt("onward"):
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "6/8")

        assert time_signatures(tluis[0].timeline) == [
            ("6", 8),
            ("6", 8),
            ("3", 4),
            ("2", 4),
        ]

    def test_an_unfinished_last_measure_is_set_over_all_its_beats(self, qtui, tluis):
        add_beat_timeline_with_pattern("2/4")
        add_beats(range(5))
        inspector = self.open_inspector_for_label(
            tluis[0], all_labels(tluis[0])[0], qtui
        )

        with patch_beat_unit_scope_prompt("onward"):
            self.type_into(inspector.field_name_to_widgets["Time signature"][1], "6/8")
        add_beats(range(5, 8))

        assert time_signatures(tluis[0].timeline) == [("6", 8)] * 4

    def test_half_typed_time_signature_is_not_applied(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )

        self.type_into(inspector.field_name_to_widgets["Time signature"][1], "2/")

        assert tluis[0].timeline.beat_units[-1].units == "3"

    def test_edit_reported_twice_asks_once(self, qtui, tluis):
        # Opening the question moves focus off the field, which reports the
        # same edit again.
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )
        line_edit = inspector.field_name_to_widgets["Time signature"][1]
        with patch_beat_unit_scope_prompt("onward") as prompts:
            line_edit.selectAll()
            QTest.keyClicks(line_edit, "2/8")
            line_edit.editingFinished.emit()
            line_edit.editingFinished.emit()
            QApplication.processEvents()

        assert len(prompts) == 1
        assert tluis[0].timeline.beat_units[-1].units == "1"

    def test_clicking_another_element_keeps_its_inspector(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = self.open_inspector_for_label(
            tluis[0], beat_unit_ui.labels[0], qtui
        )
        line_edit = inspector.field_name_to_widgets["Time signature"][1]

        with patch_beat_unit_scope_prompt("onward"):
            line_edit.selectAll()
            QTest.keyClicks(line_edit, "2/8")
            # Clicking a beat ends the edit, then selects the beat.
            line_edit.editingFinished.emit()
            click_beat_ui(tluis[0][5])
            QApplication.processEvents()

        assert tluis[0].timeline.beat_units[-1].units == "1"
        assert inspector.element_id == tluis[0][5].id

    def test_beat_inspector_shows_time_signature(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        tluis[0].select_element(tluis[0][3])

        commands.execute("timeline.element.inspect")

        inspector = qtui._windows[WindowKind.INSPECT]
        assert inspector.field_name_to_widgets["Time signature"][1].text() == "6/8"


class TestCopyPasteBeatUnits:
    def test_pasted_beats_bring_their_beat_units(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        for beat_ui in tluis[0][2:4]:
            tluis[0].select_element(beat_ui)

        commands.execute("timeline.component.copy")
        tluis[0].deselect_all_elements()
        commands.execute("media.seek", 10)
        with undoable():
            commands.execute("timeline.component.paste")

        timeline = tluis[0].timeline
        assert len(timeline) == 6
        pasted_beat = timeline.get_component_by_attr("time", 10)
        pasted_unit = timeline.get_beat_unit_on_beat(pasted_beat.id)
        assert (pasted_unit.denominator, pasted_unit.units) == (8, "3")
        assert len(timeline.beat_units) == 3

    def test_copying_a_label_copies_nothing(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        click_time_signature_label(tluis[0], beat_unit_ui.labels[0])
        before = get(Get.CLIPBOARD_CONTENTS)

        commands.execute("timeline.component.copy")

        assert get(Get.CLIPBOARD_CONTENTS) == before


def assumed_flags(timeline):
    return [u.assumed for u in timeline.beat_units]


def is_drawn_assumed(label):
    return (
        label.body.opacity() == ASSUMED_OPACITY
        and BEAT_UNIT_ASSUMED_TOOLTIP in label.toolTip()
    )


class TestAssumedBeatUnits:
    """
    Tapping can't tell 6/8 in two from 2/4, so the beat unit TiLiA gives the
    first beat is marked assumed until the user sets one.
    """

    def test_default_beat_unit_is_assumed(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))

        assert assumed_flags(tluis[0].timeline) == [True]
        (label,) = all_labels(tluis[0])
        assert is_drawn_assumed(label)

    def test_beat_unit_set_by_the_user_is_not_assumed(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))

        with undoable():
            set_beat_unit(tluis[0], 1, 8, "3")

        assert assumed_flags(tluis[0].timeline) == [True, False]
        first, second = all_labels(tluis[0])
        assert is_drawn_assumed(first)
        assert second.body.opacity() == 1
        assert second.toolTip() == ""

    def test_confirming_an_assumed_time_signature_in_the_dialog(self, tluis):
        add_beat_timeline_with_pattern("4")
        add_beats(range(4))

        with patch_bars_dialog(
            lambda dialog: edit_bars_dialog_cell(
                dialog, 0, TIME_SIGNATURE_COLUMN, "4/4"
            )
        ):
            with undoable():
                commands.execute("timeline.beat.set_pattern", tluis[0])

        beat_unit = tluis[0].timeline.beat_units[0]
        assert (beat_unit.denominator, beat_unit.units) == (4, "1")
        assert not beat_unit.assumed
        assert not is_drawn_assumed(all_labels(tluis[0])[0])

    def test_restored_measure_after_one_measure_edit_stays_assumed(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))

        set_beat_unit(tluis[0], 0, 8, "3", only_this_measure=True)

        assert assumed_flags(tluis[0].timeline) == [False, True]
        assert [is_drawn_assumed(lb) for lb in all_labels(tluis[0])] == [
            False,
            True,
        ]

    def test_deleting_the_first_beat_unit_makes_it_assumed_again(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 0, 8, "3")
        click_time_signature_label(tluis[0], all_labels(tluis[0])[0])

        with undoable():
            commands.execute("timeline.component.delete")

        assert assumed_flags(tluis[0].timeline) == [True]

    def test_measure_zero_copy_of_the_next_beat_unit_is_assumed(self, tluis):
        add_beat_timeline_with_pattern("1 2")
        add_beats(range(1, 5))
        set_beat_unit(tluis[0], 0, 8, "3")

        # A measure of its own before the first, as a score's measure 0 adds.
        tluis[0].timeline.add_measure_zero(0.5)

        # It gets the next beat unit's values, but nobody set them there.
        timeline = tluis[0].timeline
        assert assumed_flags(timeline) == [True, False]
        assert [(u.denominator, u.units) for u in timeline.beat_units] == [
            (8, "3"),
            (8, "3"),
        ]

    def test_beat_inspector_says_assumed(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")

        tluis[0].select_element(tluis[0][0])
        assert tluis[0][0].get_inspector_dict()["Time signature"] == ("2/4 (assumed)")
        assert tluis[0][2].get_inspector_dict()["Time signature"] == "6/8"

    def test_beat_unit_inspector_says_assumed(self, qtui, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        click_time_signature_label(tluis[0], all_labels(tluis[0])[0])
        commands.execute("timeline.element.inspect")
        inspector = qtui._windows[WindowKind.INSPECT]

        assert inspector.field_name_to_widgets["Assumed"][1].text() == "Yes"
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_flag_survives_save_and_reopen(self, tluis, tmp_path):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")

        save_and_reopen(tmp_path)

        assert assumed_flags(tluis[0].timeline) == [True, False]

    def test_file_from_before_beat_units_loads_assumed(self, resources, tluis):
        commands.execute("file.open", path=resources / "tla" / "many_beats.tla")

        assert assumed_flags(tluis[0].timeline) == [True]

    def test_file_without_a_first_beat_unit_loads_its_copy_assumed(
        self, tluis, tmp_path
    ):
        # TiLiA always keeps a beat unit in the first measure, so it can't
        # write such a file: remove that beat unit from a saved one.
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))
        set_beat_unit(tluis[0], 2, 8, "3")
        first_beat_id = tluis[0].timeline[0].id
        path = save_tilia_to_tmp_path(tmp_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        components = next(
            tl["components"]
            for tl in data["timelines"].values()
            if tl["kind"] == "Beat"
        )
        (first_unit_id,) = [
            id
            for id, component in components.items()
            if component["kind"] == "BEAT_UNIT"
            and component["beat_id"] == first_beat_id
        ]
        del components[first_unit_id]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        post(Post.APP_CLEAR)

        commands.execute("file.open", path=path)

        # The first measure gets a copy of the beat unit on bar 3, but nobody
        # set a time signature on the bars before it.
        meters = tluis[0].timeline.measure_meters
        assert [(m.time_signature, m.is_assumed) for m in meters] == [
            ((6, 8), True),
            ((6, 8), True),
            ((6, 8), False),
        ]

    def test_pasted_beat_unit_keeps_its_flag(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 1, 8, "3")
        tluis[0].select_element(tluis[0][2])

        commands.execute("timeline.component.copy")
        tluis[0].deselect_all_elements()
        commands.execute("media.seek", 10)
        commands.execute("timeline.component.paste")

        timeline = tluis[0].timeline
        pasted_beat = timeline.get_component_by_attr("time", 10)
        assert not timeline.get_beat_unit_on_beat(pasted_beat.id).assumed


class TestConflictingBeatUnits:
    @staticmethod
    def make_conflict(tluis):
        """
        Two beat units in one measure, as a CSV import that gives a beat unit
        to a beat that doesn't start a measure leaves them.
        """
        add_beat_timeline_with_pattern("2")
        add_beats(range(6))
        set_beat_unit(tluis[0], 0, 8, "1")
        timeline = tluis[0].timeline
        timeline.put_beat_unit_on_beat(timeline[1].id, 2, "1")
        post(Post.APP_STATE_RECORD, "conflicting beat units")
        assert timeline.get_measure_meter(0).is_conflicting

    @staticmethod
    def right_click_label(timeline_ui, label):
        with patch.object(BeatUnitContextMenu, "exec"):
            click_time_signature_label(timeline_ui, label, button="right")

    def test_label_is_red(self, tluis):
        self.make_conflict(tluis)

        label = all_labels(tluis[0])[0]
        assert label.spec.state == LabelState.CONFLICTING

    def test_menu_offers_removing_the_others(self, tluis):
        self.make_conflict(tluis)
        beat_unit_ui = next(u for u in tluis[0].beat_unit_uis if u.labels)
        self.right_click_label(tluis[0], beat_unit_ui.labels[0])

        names = get_command_names(BeatUnitContextMenu(beat_unit_ui))

        assert names == [
            "timeline.beat.edit_bars",
            "timeline.beat.remove_other_beat_units",
            "timeline.component.delete",
        ]

    def test_menu_does_not_offer_it_without_a_conflict(self, tluis):
        add_beat_timeline_with_pattern("2")
        add_beats(range(4))
        set_beat_unit(tluis[0], 0, 8, "1")
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        self.right_click_label(tluis[0], beat_unit_ui.labels[0])

        names = get_command_names(BeatUnitContextMenu(beat_unit_ui))

        assert "timeline.beat.remove_other_beat_units" not in names

    def test_removing_the_others_keeps_the_first(self, tluis):
        self.make_conflict(tluis)
        timeline = tluis[0].timeline
        first = timeline.get_beat_units_in_measure(0)[0]
        beat_unit_ui = tluis[0].get_element(first.id)
        self.right_click_label(tluis[0], beat_unit_ui.labels[0])
        action = get_command_action(
            BeatUnitContextMenu(beat_unit_ui),
            "timeline.beat.remove_other_beat_units",
        )

        with undoable():
            action.trigger()

        # Undo and redo recreate components, so compare by id.
        assert [u.id for u in timeline.beat_units] == [first.id]
        assert all_labels(tluis[0])[0].spec.state == LabelState.NORMAL


class TestFileFromBeforeBeatUnits:
    """tests/resources/tla/many_beats.tla was saved by TiLiA 0.5.15: its beat
    pattern is a list, it has no show_time_signatures and no beat units."""

    @pytest.fixture
    def old_timeline_ui(self, resources, tluis):
        commands.execute("file.open", path=resources / "tla" / "many_beats.tla")
        return tluis[0]

    def test_loads_unchanged(self, old_timeline_ui):
        timeline = old_timeline_ui.timeline
        assert len(timeline) == 1000
        assert timeline.beat_pattern == "4"
        assert timeline.beats_in_measure == [4] * 250
        assert_only_the_default_beat_unit(timeline)
        assert not timeline.show_time_signatures
        assert timeline.height == 35
        assert all_labels(old_timeline_ui) == []

    def test_opening_does_not_count_as_a_change(self, old_timeline_ui, tilia):
        # Loading adds the first beat's beat unit, which isn't an edit.
        assert not tilia.is_file_modified()

    def test_defaults_to_four_four(self, old_timeline_ui):
        timeline = old_timeline_ui.timeline
        assert {m.time_signature for m in timeline.measure_meters} == {(4, 4)}
        assert timeline.quarter_stamps[4] == 4

    @pytest.mark.timeout(10)
    def test_showing_time_signatures(self, old_timeline_ui):
        commands.execute("timeline.beat.toggle_time_signatures", old_timeline_ui)

        assert label_texts(all_labels(old_timeline_ui)) == [("4", "4")]
        assert old_timeline_ui.get_data("height") == 35 + TIME_SIGNATURE_BAND_HEIGHT

    def test_new_features_work_and_save_in_new_format(
        self, old_timeline_ui, tluis, tmp_path
    ):
        commands.execute("timeline.beat.set_pattern", old_timeline_ui, pattern="3")
        set_beat_unit(old_timeline_ui, 1, 8, "3")

        save_and_reopen(tmp_path)

        timeline = tluis[0].timeline
        assert timeline.beat_pattern == "3"
        assert timeline.measure_count == 334
        beat_unit = timeline.beat_units[-1]
        assert (beat_unit.denominator, beat_unit.units) == (8, "3")
        assert timeline.get_measure_meter(1).time_signature == (9, 8)


class TestTimeSignaturesFollowTimelineChanges:
    def test_fill_with_beats_shows_time_signatures(self, tluis):
        add_beat_timeline_with_pattern("4")
        commands.execute("timeline.beat.set_pattern", tluis[0], pattern="3[2 3]")

        with patch_fill_beat_timeline_dialog(
            tluis[0].timeline, BeatTimeline.FillMethod.BY_AMOUNT, 20
        ):
            commands.execute("timeline.beat.fill")

        assert label_texts(all_labels(tluis[0])) == [
            ("2", "4"),
            ("3", "4"),
            ("2", "4"),
            ("3", "4"),
            ("2", "4"),
            ("3", "4"),
            ("2", "4"),
            ("3", "4"),
        ]

    def test_labels_follow_cropped_timeline(self, tluis, tilia_state):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))

        tilia_state.set_duration(5.5, scale_timelines="no")

        assert label_texts(all_labels(tluis[0])) == [
            ("2", "4"),
            ("3", "4"),
            ("1", "4"),
        ]

    def test_labels_follow_scaled_timeline(self, tluis, tilia_state):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(10))

        tilia_state.set_duration(200, scale_timelines="yes")

        # Downbeats were at 0, 2, 5 and 7 s; the first label sits against the
        # left margin, so only the others are checked.
        labels = all_labels(tluis[0])[1:]
        for label, time in zip(labels, [4, 10, 14], strict=True):
            assert label.rect().center().x() == pytest.approx(
                time_x_converter.get_x_by_time(time)
            )


def _add_a_beat(tluis, tilia_state):
    commands.execute("media.seek", 7.5)
    commands.execute("timeline.beat.add")


def _delete_a_beat(tluis, tilia_state):
    tluis[0].select_element(tluis[0][3])
    commands.execute("timeline.component.delete")


def _move_a_beat(tluis, tilia_state):
    # What dragging a beat does.
    tluis[0].timeline.set_component_data(tluis[0].timeline[3].id, "time", 3.5)


def _distribute(tluis, tilia_state):
    tluis[0].timeline.set_component_data(tluis[0].timeline[1].id, "time", 0.2)
    tluis[0].select_element(tluis[0][0])
    commands.execute("timeline.beat.distribute")


def _set_pattern(tluis, tilia_state):
    commands.execute("timeline.beat.set_pattern", tluis[0], pattern="3")


def _set_amount_in_measure(tluis, tilia_state):
    tluis[0].select_element(tluis[0][0])
    with patch_ask_for_int_dialog(True, 3):
        commands.execute("timeline.beat.set_amount_in_measure")


def _set_another_beat_unit(tluis, tilia_state):
    set_beat_unit(tluis[0], 2, 2, "1")


def _edit_the_beat_unit(tluis, tilia_state):
    set_beat_unit(tluis[0], 1, 8, "1+2")


def _delete_the_beat_unit(tluis, tilia_state):
    click_time_signature_label(tluis[0], newest_beat_unit_ui(tluis[0]).labels[0])
    commands.execute("timeline.component.delete")


def _fill_with_beats(tluis, tilia_state):
    with (
        patch_fill_beat_timeline_dialog(
            tluis[0].timeline, BeatTimeline.FillMethod.BY_AMOUNT, 30
        ),
        patch_yes_or_no_dialog(True),
    ):
        commands.execute("timeline.beat.fill")


def _crop(tluis, tilia_state):
    tilia_state.set_duration(5.5, scale_timelines="no")


def _scale(tluis, tilia_state):
    tilia_state.set_duration(200, scale_timelines="yes")


def _undo(tluis, tilia_state):
    commands.execute("edit.undo")


def _redo(tluis, tilia_state):
    commands.execute("edit.undo")
    _warm_quarter_stamp_caches(tluis[0].timeline)
    commands.execute("edit.redo")


def _paste_beats(tluis, tilia_state):
    for beat_ui in tluis[0][2:4]:
        tluis[0].select_element(beat_ui)
    commands.execute("timeline.component.copy")
    tluis[0].deselect_all_elements()
    commands.execute("media.seek", 20)
    commands.execute("timeline.component.paste")


def _warm_quarter_stamp_caches(timeline):
    timeline.get_quarter_stamp_by_time(1.0)
    timeline.get_time_by_quarter_stamp(1.0)


class TestQuarterStampCacheStaysFresh:
    """
    The time/stamp table is cached and rebuilt when the beats change. After
    every kind of change, the cached values must equal a fresh build.
    """

    @pytest.mark.parametrize(
        "change",
        [
            _add_a_beat,
            _delete_a_beat,
            _move_a_beat,
            _distribute,
            _set_pattern,
            _set_amount_in_measure,
            _set_another_beat_unit,
            _edit_the_beat_unit,
            _delete_the_beat_unit,
            _fill_with_beats,
            _crop,
            _scale,
            _undo,
            _redo,
            _paste_beats,
        ],
    )
    def test_after(self, tluis, tilia_state, change):
        add_beat_timeline_with_pattern("2")
        add_beats(range(8))
        set_beat_unit(tluis[0], 1, 8, "3")
        timeline = tluis[0].timeline
        _warm_quarter_stamp_caches(timeline)

        change(tluis, tilia_state)

        timeline = tluis[0].timeline
        assert timeline.quarter_stamps == timeline._build_quarter_stamps()
        assert timeline._get_time_stamp_table() == timeline._build_time_stamp_table()


class TestOneMeasureEditRoundTrips:
    """
    Pattern "2 3" with 6 taps gives bars of 2, 3 and 1 beats. Changing the
    denominator of the middle bar only puts a beat unit on it and one on the
    next bar restoring the old values. Everything derived from that must
    survive saving, reopening, undo and redo.
    """

    @staticmethod
    def setup_timeline(tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(6))
        set_beat_unit(tluis[0], 1, 8, "1", only_this_measure=True)

    @staticmethod
    def snapshot(timeline_ui):
        timeline = timeline_ui.timeline
        return {
            "bars": list(timeline.beats_in_measure),
            "time_signatures": [m.time_signature for m in timeline.measure_meters],
            "beat_units": [
                (
                    timeline.get_beat_index(timeline.get_component(u.beat_id)),
                    u.denominator,
                    u.units,
                )
                for u in timeline.beat_units
            ],
            "stamps": list(timeline.quarter_stamps),
            "stamp_at_4_5s": timeline.get_quarter_stamp_by_time(4.5),
            "labels": label_texts(all_labels(timeline_ui)),
        }

    EXPECTED = {
        "bars": [2, 3, 1],
        "time_signatures": [(2, 4), (3, 8), (1, 4)],
        "beat_units": [(0, 4, "1"), (2, 8, "1"), (5, 4, "1")],
        "stamps": [0, 1, 2, F(5, 2), 3, F(7, 2)],
        "stamp_at_4_5s": 3.25,
        "labels": [("2", "4"), ("3", "8"), ("1", "4")],
    }

    def test_edit(self, tluis):
        self.setup_timeline(tluis)

        assert self.snapshot(tluis[0]) == self.EXPECTED

    def test_save_and_reopen(self, tluis, tmp_path):
        self.setup_timeline(tluis)

        save_and_reopen(tmp_path)

        assert self.snapshot(tluis[0]) == self.EXPECTED

    def test_reopening_twice_changes_nothing(self, tluis, tmp_path, tilia):
        self.setup_timeline(tluis)
        save_and_reopen(tmp_path)
        components = tluis[0].timeline.get_state()["components"]

        save_and_reopen(tmp_path, "second")

        assert tluis[0].timeline.get_state()["components"] == components
        assert not tilia.is_file_modified()

    def test_undo_and_redo(self, qtui, tluis):
        add_beat_timeline_with_pattern("2 3")
        add_beats(range(6))
        beat_unit_ui = newest_beat_unit_ui(tluis[0])
        inspector = TestTimeSignatureInspector.open_inspector_for_label(
            tluis[0], beat_unit_ui.get_label(1), qtui
        )

        with patch_beat_unit_scope_prompt("measure"):
            with undoable():
                TestTimeSignatureInspector.type_into(
                    inspector.field_name_to_widgets["Time signature"][1], "3/8"
                )

        assert self.snapshot(tluis[0]) == self.EXPECTED
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def test_tapping_on_after_reopening(self, tluis, tmp_path):
        self.setup_timeline(tluis)
        save_and_reopen(tmp_path)

        add_beats([6])

        snapshot = self.snapshot(tluis[0])
        assert snapshot["bars"] == [2, 3, 2]
        assert snapshot["time_signatures"] == [(2, 4), (3, 8), (2, 4)]
        assert snapshot["stamps"][-1] == F(9, 2)


class TestManyBeats:
    @pytest.mark.timeout(15)
    def test_setting_a_pattern_with_changing_time_signatures(self, tluis, tilia_state):
        tilia_state.set_duration(10000, scale_timelines="no")
        add_beat_timeline_with_pattern("4")
        with patch_fill_beat_timeline_dialog(
            tluis[0].timeline, BeatTimeline.FillMethod.BY_AMOUNT, 2000
        ):
            commands.execute("timeline.beat.fill")

        with undoable():
            commands.execute(
                "timeline.beat.set_pattern", tluis[0], pattern="2/4 3/8(3)"
            )

        # A beat unit on every measure: 666 pairs and one more 2/4.
        assert len(tluis[0].timeline.beat_units) == 1333

    @pytest.mark.timeout(15)
    def test_pasting_many_beats_near_the_start(self, tluis, tilia_state):
        tilia_state.set_duration(10000, scale_timelines="no")
        add_beat_timeline_with_pattern("4/4")
        with patch_fill_beat_timeline_dialog(
            tluis[0].timeline, BeatTimeline.FillMethod.BY_AMOUNT, 2000
        ):
            commands.execute("timeline.beat.fill")
        for beat_ui in tluis[0][0:100]:
            tluis[0].select_element(beat_ui)
        commands.execute("timeline.component.copy")
        tluis[0].deselect_all_elements()
        commands.execute("media.seek", 2.5)

        commands.execute("timeline.component.paste")

        assert len(tluis[0].timeline) == 2100
        assert tluis[0].timeline.beats_in_measure == [4] * 525
