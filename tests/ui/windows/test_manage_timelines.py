import sys
from contextlib import contextmanager, nullcontext
from typing import Literal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.mock import patch_yes_no_or_cancel_mb, patch_yes_or_no_dialog
from tests.utils import save_and_reopen, undoable
from tilia.requests import Get, Post, get, post
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.collection.collection import Timelines
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.ui import commands
from tilia.ui.windows.manage_timelines import ManageTimelines


def assert_order_is_correct(tls: Timelines, expected: list[Timeline]):
    # assert timeline order
    for tl, e in zip(sorted(tls), expected, strict=True):
        assert tl == e

    # assert list widget order
    for i, tl in enumerate(expected):
        tlui = get(Get.TIMELINE_UI, tl.id)
        with manage_timelines() as mt:
            assert mt.list_widget.item(i).timeline_ui == tlui


@contextmanager
def manage_timelines():
    """Context manager for the ManageTimelines window."""
    mt = ManageTimelines()
    try:
        yield mt
    finally:
        mt.close()


class TestChangeTimelineVisibility:
    @staticmethod
    def toggle_timeline_is_visible(row: int = 0):
        """Toggles timeline visibility using the Manage Timelines window."""
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(row)
            QTest.mouseClick(mt.checkbox, Qt.MouseButton.LeftButton)

    def test_hide(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        self.toggle_timeline_is_visible()
        assert not marker_tlui.get_data("is_visible")

    def test_show(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, False)
        self.toggle_timeline_is_visible()
        assert marker_tlui.get_data("is_visible")

    def test_toggle_visibility_multiple_times(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        for i in range(10):
            self.toggle_timeline_is_visible()
            if i % 2 == 1:
                assert marker_tlui.get_data("is_visible")
            else:
                assert not marker_tlui.get_data("is_visible")


class TestChangeTimelineOrder:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tluis, tls):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="")
        return list(tls)

    @staticmethod
    def click_set_ordinal_button(button: Literal["up", "down"], row: int):
        """Toggles timeline visibility using the ManageTimelines window."""
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(row)
            if button == "up":
                button = mt.up_button
            elif button == "down":
                button = mt.down_button
            else:
                raise AssertionError("Invalid button value.")

            QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def test_increase_ordinal(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_increase_ordinal_undo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)
        commands.execute("edit.undo")

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_increase_ordinal_redo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 1)
        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_increase_ordinal_with_first_selected_does_nothing(
        self, tls, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("up", 0)

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_decrease_ordinal(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_decrease_ordinal_undo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)
        commands.execute("edit.undo")

        assert_order_is_correct(tls, [tl0, tl1, tl2])

    def test_decrease_ordinal_redo(self, tls, setup_timelines):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 0)
        commands.execute("edit.undo")
        commands.execute("edit.redo")

        assert_order_is_correct(tls, [tl1, tl0, tl2])

    def test_decrease_ordinal_with_last_selected_does_nothing(
        self, tls, setup_timelines
    ):
        tl0, tl1, tl2 = setup_timelines

        self.click_set_ordinal_button("down", 2)

        assert_order_is_correct(tls, [tl0, tl1, tl2])


class TesttimelinesChangeWhileOpen:
    @pytest.fixture
    def uncaught(self, monkeypatch):
        # Qt hands exceptions raised in the window's slots to sys.excepthook,
        # where the app shows its crash dialog and exits. They never reach
        # pytest, so collect them here.
        exceptions = []
        monkeypatch.setattr(sys, "excepthook", lambda *info: exceptions.append(info[1]))
        return exceptions

    def test_timeline_is_deleted(self, tluis):
        commands.execute("timelines.add.marker", name="")
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            commands.execute("timeline.delete", tluis[0], confirm=False)
            assert mt.list_widget.count() == 0

    @staticmethod
    def move_second_timeline_up(mt):
        mt.list_widget.setCurrentRow(1)
        QTest.mouseClick(mt.up_button, Qt.MouseButton.LeftButton)

    def test_timeline_is_deleted_after_reordering(self, tluis, uncaught):
        commands.execute("timelines.add.marker", name="First")
        commands.execute("timelines.add.marker", name="Second")
        with manage_timelines() as mt:
            self.move_second_timeline_up(mt)
            first = next(tlui for tlui in tluis if tlui.get_data("name") == "First")
            commands.execute("timeline.delete", first, confirm=False)

            assert uncaught == []
            assert mt.list_widget.count() == 1
            assert mt.list_widget.currentItem().timeline_ui.get_data("name") == "Second"

    def test_new_file_after_reordering(self, tluis, uncaught):
        commands.execute("timelines.add.marker", name="First")
        commands.execute("timelines.add.marker", name="Second")
        with manage_timelines() as mt:
            self.move_second_timeline_up(mt)
            with patch_yes_no_or_cancel_mb(False):
                commands.execute("file.new")

            assert uncaught == []
            listed = [mt.list_widget.item(i) for i in range(mt.list_widget.count())]
            assert all(get(Get.TIMELINE, item.timeline_ui.id) for item in listed)

    # Much more could be tested here.


class TestClearButtonIsEnabled:
    """Regression tests for #435 — Clear button should be disabled when
    the selected timeline has nothing to clear, and should react to
    components being added or removed underneath the open window."""

    def test_disabled_when_empty(self, marker_tlui):
        with manage_timelines() as mt:
            assert not mt.clear_button.isEnabled()

    def test_enabled_when_non_empty(self, marker_tlui):
        commands.execute("timeline.marker.add")
        with manage_timelines() as mt:
            assert mt.clear_button.isEnabled()

    def test_updates_when_component_added_while_open(self, marker_tlui):
        with manage_timelines() as mt:
            assert not mt.clear_button.isEnabled()
            commands.execute("timeline.marker.add")
            assert mt.clear_button.isEnabled()

    def test_updates_when_component_removed_while_open(self, marker_tlui, tilia_state):
        commands.execute("timeline.marker.add")
        with manage_timelines() as mt:
            assert mt.clear_button.isEnabled()
            marker_tlui.select_all_elements()
            commands.execute("timeline.component.delete")
            assert not mt.clear_button.isEnabled()

    def test_disabled_for_audiowave_timeline_even_when_non_empty(self, audiowave_tlui):
        # AudioWaveTimeline.FLAGS includes NOT_CLEARABLE, so Clear should
        # stay disabled regardless of whether it has components.
        audiowave_tlui.create_amplitudebar(0, 1, 1)
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert not mt.clear_button.isEnabled()


class TestButtonsDisabledWhenHidden:
    """Regression tests — Clear and Delete buttons should be disabled
    when the selected timeline is hidden."""

    def test_clear_disabled_when_hidden(self, marker_tlui):
        commands.execute("timeline.marker.add")
        commands.execute("timeline.set_is_visible", marker_tlui, False)
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert not mt.clear_button.isEnabled()

    def test_delete_disabled_when_hidden(self, marker_tlui):
        commands.execute("timeline.set_is_visible", marker_tlui, False)
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert not mt.delete_button.isEnabled()

    def test_buttons_enabled_when_visible(self, marker_tlui):
        commands.execute("timeline.marker.add")
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert mt.clear_button.isEnabled()
            assert mt.delete_button.isEnabled()

    def test_buttons_update_when_visibility_toggled_via_checkbox(self, marker_tlui):
        commands.execute("timeline.marker.add")
        commands.execute("timeline.set_is_visible", marker_tlui, True)
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert mt.clear_button.isEnabled()
            assert mt.delete_button.isEnabled()

            QTest.mouseClick(mt.checkbox, Qt.MouseButton.LeftButton)

            assert not mt.clear_button.isEnabled()
            assert not mt.delete_button.isEnabled()


class TestDeleteTimeline:
    def delete_selected_timeline(self, mt):
        with patch_yes_or_no_dialog(True):
            mt.delete_button.click()

    def test_deleting_last_timeline_does_not_crash(self, tluis):
        commands.execute("timelines.add.marker", name="First")
        commands.execute("timelines.add.marker", name="Second")
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(1)
            self.delete_selected_timeline(mt)

            assert mt.list_widget.count() == 1
        assert len(tluis) == 1
        assert tluis[0].get_data("name") == "First"

    def test_deleting_twice_in_a_row(self, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="")
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            self.delete_selected_timeline(mt)
            self.delete_selected_timeline(mt)
            assert mt.list_widget.count() == 0
        assert len(tluis) == 0

    def test_deleting_non_last_row_preserves_row_index(self, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="")
        commands.execute("timelines.add.marker", name="")
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(1)
            self.delete_selected_timeline(mt)
            assert mt.list_widget.currentRow() == 1


def get_comparable_state(timeline: Timeline) -> dict:
    """
    Timeline state without the attributes a duplicate must not share.

    A duplicate's components get fresh ids, so an id that a component holds
    (a beat unit's `beat_id`) is compared as the position of the component
    it names, and the hashes, which include such ids, are left out.
    """
    state = timeline.get_state()
    for attr in ("name", "ordinal", "hash", "components_hash"):
        state.pop(attr, None)
    positions = {id: i for i, id in enumerate(state["components"])}
    components = []
    for data in state["components"].values():
        data = {attr: value for attr, value in data.items() if attr != "hash"}
        if "beat_id" in data:
            data["beat_id"] = positions[data["beat_id"]]
        components.append(data)
    state["components"] = components
    return state


class TestDuplicateTimeline:
    @staticmethod
    def click_duplicate_button(row: int = 0):
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(row)
            QTest.mouseClick(mt.duplicate_button, Qt.MouseButton.LeftButton)

    @staticmethod
    def get_duplicate(tls, name: str) -> Timeline:
        return tls.get_timeline_by_attr("name", name)

    def test_button_enabled(self, marker_tlui):
        with manage_timelines() as mt:
            assert mt.duplicate_button.isEnabled()

    def test_button_disabled_for_slider(self, slider_tlui):
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            assert not mt.duplicate_button.isEnabled()

    def test_button_updates_when_selection_changes(self, tluis, slider_tlui):
        commands.execute("timelines.add.marker", name="")
        with manage_timelines() as mt:
            for row in range(mt.list_widget.count()):
                mt.list_widget.setCurrentRow(row)
                is_slider = mt.list_widget.item(row).timeline_ui == slider_tlui
                assert mt.duplicate_button.isEnabled() != is_slider

    def test_duplicate_slider_does_nothing(self, tls, slider_tlui):
        commands.execute("timeline.duplicate", slider_tlui)
        assert len(tls) == 1

    def test_duplicate(self, tls, tluis):
        commands.execute("timelines.add.marker", name="Cadences")
        commands.execute("timeline.marker.add", time=10)
        commands.execute("timeline.marker.add", time=20)
        original = tls[0]

        self.click_duplicate_button()

        assert len(tls) == 2
        duplicate = self.get_duplicate(tls, "Cadences_copy")
        assert duplicate is not None
        assert get_comparable_state(duplicate) == get_comparable_state(original)
        assert len(tluis.get_timeline_ui(duplicate.id)) == 2

    def test_duplicate_has_fresh_ids(self, tls, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add", time=10)
        original = tls[0]

        self.click_duplicate_button()

        duplicate = self.get_duplicate(tls, "_copy")
        assert duplicate.id != original.id
        assert duplicate[0].id != original[0].id

    def test_duplicate_is_independent(self, tls, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.marker.add", time=10)
        original = tls[0]
        self.click_duplicate_button()
        duplicate = self.get_duplicate(tls, "_copy")

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", get(Get.TIMELINE_UI, original.id))

        assert original.is_empty
        assert len(duplicate) == 1

    def test_duplicate_is_placed_below_original(self, tls, tluis):
        commands.execute("timelines.add.marker", name="first")
        commands.execute("timelines.add.marker", name="second")
        commands.execute("timelines.add.marker", name="third")
        first, second, third = sorted(tls)

        self.click_duplicate_button(row=1)

        duplicate = self.get_duplicate(tls, "second_copy")
        assert_order_is_correct(tls, [first, second, duplicate, third])

    def test_duplicate_last_timeline(self, tls, tluis):
        commands.execute("timelines.add.marker", name="first")
        commands.execute("timelines.add.marker", name="second")
        first, second = sorted(tls)

        self.click_duplicate_button(row=1)

        duplicate = self.get_duplicate(tls, "second_copy")
        assert_order_is_correct(tls, [first, second, duplicate])

    def test_list_widget_is_updated(self, tls, tluis):
        commands.execute("timelines.add.marker", name="first")
        commands.execute("timelines.add.marker", name="second")
        with manage_timelines() as mt:
            mt.list_widget.setCurrentRow(0)
            QTest.mouseClick(mt.duplicate_button, Qt.MouseButton.LeftButton)
            names = [
                mt.list_widget.item(i).text() for i in range(mt.list_widget.count())
            ]
        assert names == ["first", "first_copy", "second"]

    def test_duplicate_hidden_timeline(self, tls, tluis):
        commands.execute("timelines.add.marker", name="")
        commands.execute("timeline.set_is_visible", get(Get.TIMELINE_UIS)[0], False)

        self.click_duplicate_button()

        assert not self.get_duplicate(tls, "_copy").get_data("is_visible")

    def test_undo_redo(self, tls, tluis):
        commands.execute("timelines.add.marker", name="first")
        commands.execute("timeline.marker.add", time=10)
        commands.execute("timelines.add.marker", name="second")
        with undoable():
            commands.execute("timeline.duplicate", get(Get.TIMELINE_UIS)[0])

    def test_save_and_reopen(self, tls, tluis, tmp_path):
        commands.execute("timelines.add.marker", name="Cadences")
        commands.execute("timeline.marker.add", time=10)
        commands.execute("timeline.duplicate", get(Get.TIMELINE_UIS)[0])
        expected = [get_comparable_state(tl) for tl in sorted(tls)]

        save_and_reopen(tmp_path)

        names = [tl.get_data("name") for tl in sorted(tls)]
        assert "Cadences_copy" in names
        markers = [
            tl
            for tl in sorted(tls)
            if tl.get_data("name") in ("Cadences", "Cadences_copy")
        ]
        assert [get_comparable_state(tl) for tl in markers] == expected


class TestDuplicateTimelineKinds:
    """Every duplicatable kind should yield an identical copy."""

    @staticmethod
    def duplicate(timeline_ui) -> tuple[Timeline, Timeline]:
        original = timeline_ui.timeline
        commands.execute("timeline.duplicate", timeline_ui)
        duplicate = get(Get.TIMELINE_COLLECTION).get_timeline_by_attr(
            "name", original.get_data("name") + "_copy"
        )
        return original, duplicate

    def assert_is_copy(self, timeline_ui, check_undo: bool = True):
        # Some kinds have no commands to add components, so their setup
        # bypasses the undo manager. Record it, so undo has a state to go to.
        post(Post.APP_STATE_RECORD, "test setup")
        with undoable() if check_undo else nullcontext():
            original, duplicate = self.duplicate(timeline_ui)
            assert duplicate is not None
            assert type(duplicate) is type(original)
            assert get_comparable_state(duplicate) == get_comparable_state(original)
            duplicate_ui = get(Get.TIMELINE_UI, duplicate.id)
            assert len(duplicate_ui) == len(timeline_ui)

    def test_marker(self, marker_tlui):
        commands.execute("timeline.marker.add", time=10)
        self.assert_is_copy(marker_tlui)

    def test_hierarchy(self, tluis):
        commands.execute("timelines.add.hierarchy", name="form")
        commands.execute("timeline.hierarchy.add", start=0, end=50, level=1)
        commands.execute("timeline.hierarchy.add", start=50, end=100, level=1)
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=2)
        self.assert_is_copy(tluis[0])

    def test_empty_hierarchy(self, hierarchy_tlui):
        assert len(hierarchy_tlui.timeline) == 0
        # Restoring a timeline without components re-creates the initial
        # hierarchy, so redo doesn't round-trip. That also affects undoing
        # the deletion of an empty hierarchy timeline and is tracked
        # separately.
        self.assert_is_copy(hierarchy_tlui, check_undo=False)

    def test_beat(self, beat_tlui):
        for time in (10, 20, 30, 40, 50):
            commands.execute("timeline.beat.add", time=time)
        self.assert_is_copy(beat_tlui)

    def test_harmony(self, harmony_tlui):
        harmony_tlui.create_harmony(time=10)
        harmony_tlui.create_mode(time=10)
        self.assert_is_copy(harmony_tlui)

    def test_pdf(self, pdf_tlui):
        pdf_tlui.create_pdf_marker(0, page_number=1)
        pdf_tlui.create_pdf_marker(10, page_number=2)
        self.assert_is_copy(pdf_tlui)

    def test_score(self, score_tlui):
        tl = score_tlui.timeline
        tl.create_component(ComponentKind.STAFF, 0, 5)
        tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE)
        tl.create_component(ComponentKind.NOTE, 0, 1, 0, 0, 3, 0)
        self.assert_is_copy(score_tlui)

    def test_range(self, range_tlui):
        commands.execute("timeline.range.add_row")
        commands.execute("timeline.range.add_range", start=10, end=20)
        self.assert_is_copy(range_tlui)

    def test_audiowave(self, audiowave_tlui):
        audiowave_tlui.create_amplitudebar(0, 1, 0.5)
        audiowave_tlui.create_amplitudebar(1, 2, 0.25)
        self.assert_is_copy(audiowave_tlui)
