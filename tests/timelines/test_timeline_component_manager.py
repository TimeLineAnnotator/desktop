import itertools
import os
import random
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.utils import undoable
from tilia.requests import Post, listen, post, stop_listening_to_all
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.score.components import Clef
from tilia.ui import commands
from tilia.undo_manager import PauseUndoManager

# These cross a change in length, where sorting by text alone would put "100"
# before "99".
IDS_ACROSS_A_LENGTH = [str(i) for i in range(95, 105)]


class TestComponentOrder:
    def test_components_stay_sorted_after_setting_ordering_attr(
        self, marker_tl, tilia_state
    ):
        for i in range(0, 100, 10):
            marker_tl.create_marker(i)

        for i in range(10):
            marker_tl[i].set_data("time", random.randrange(0, 99))

        for c1, c2 in itertools.pairwise(marker_tl):
            assert c1 < c2 or c1.time == c2.time


def _record():
    post(Post.APP_STATE_RECORD, "test")


def _ids(timeline):
    return {c.id for c in timeline}


def _add_identical_notes(score_tl):
    score_tl.create_component(ComponentKind.STAFF, 0, 5)
    score_tl.create_component(ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE)
    return [
        score_tl.create_component(ComponentKind.NOTE, 0, 1, 0, 0, 3, 0)[0].id
        for _ in range(2)
    ]


def _add_beats(times):
    for time in times:
        commands.execute("media.seek", time)
        commands.execute("timeline.beat.add")


class _Listener:
    """The ids a post names, in the order they were posted."""

    def __init__(self, post_, id_index):
        self.ids = []
        self.id_index = id_index
        listen(self, post_, self._on_post)

    def _on_post(self, *args):
        self.ids.append(args[self.id_index])

    def __enter__(self):
        return self

    def __exit__(self, *_):
        stop_listening_to_all(self)


class TestRestoreById:
    def test_components_with_identical_values_survive_undo_and_redo(self, score_tl):
        _add_identical_notes(score_tl)
        ids = _ids(score_tl)
        _record()
        score_tl.clear()
        _record()

        commands.execute("edit.undo")
        assert _ids(score_tl) == ids

        commands.execute("edit.redo")
        assert _ids(score_tl) == set()

    def test_deleting_one_of_two_identical_components_is_undone_and_redone(
        self, score_tl
    ):
        kept, deleted = _add_identical_notes(score_tl)
        ids = _ids(score_tl)
        _record()
        score_tl.delete_components([score_tl.get_component(deleted)])
        _record()

        commands.execute("edit.undo")
        assert _ids(score_tl) == ids

        commands.execute("edit.redo")
        assert _ids(score_tl) == ids - {deleted}
        assert kept in _ids(score_tl)

    def test_deleted_component_is_restored_with_its_id(self, marker_tl):
        marker_tl.create_marker(10)
        marker, _ = marker_tl.create_marker(20)
        id = marker.id
        _record()
        marker_tl.delete_components([marker])
        _record()

        commands.execute("edit.undo")

        assert marker_tl.get_component(id).get_data("time") == 20

    def test_changed_component_is_restored_with_its_id(self, marker_tl):
        marker, _ = marker_tl.create_marker(10, label="before")
        id = marker.id
        _record()
        marker_tl.set_component_data(id, "label", "after")
        _record()

        commands.execute("edit.undo")
        assert marker_tl.get_component(id).get_data("label") == "before"
        assert marker_tl.get_component(id) is not marker

        commands.execute("edit.redo")
        assert marker_tl.get_component(id).get_data("label") == "after"

    def test_unchanged_component_is_left_alone(self, marker_tl):
        unchanged, _ = marker_tl.create_marker(10)
        changed, _ = marker_tl.create_marker(20, label="before")
        _record()
        marker_tl.set_component_data(changed.id, "label", "after")
        _record()

        commands.execute("edit.undo")

        assert marker_tl.get_component(unchanged.id) is unchanged

    def test_values_that_changed_places_go_back_to_their_ids(self, marker_tl):
        # The timeline's digest is the same in both states: it knows the values,
        # not whose they are.
        first, _ = marker_tl.create_marker(10)
        second, _ = marker_tl.create_marker(20)
        first_id, second_id = first.id, second.id
        _record()
        with PauseUndoManager():
            marker_tl.set_component_data(first_id, "time", 15)
            marker_tl.set_component_data(second_id, "time", 10)
            marker_tl.set_component_data(first_id, "time", 20)
        _record()

        commands.execute("edit.undo")

        assert marker_tl.get_component(first_id).get_data("time") == 10
        assert marker_tl.get_component(second_id).get_data("time") == 20

    def test_beat_deleted_and_made_again_at_the_same_time_keeps_its_first_id(
        self, beat_tlui
    ):
        beat_tl = beat_tlui.timeline
        _add_beats([0, 10, 20])
        first_ids = [beat.id for beat in beat_tl]
        _record()

        # The two states have the same values, and differ only in the beat's id.
        with PauseUndoManager():
            beat_tl.delete_components([beat_tl[1]])
            _add_beats([10])
        second_ids = [beat.id for beat in beat_tl]
        assert second_ids != first_ids
        _record()

        commands.execute("edit.undo")
        assert [beat.id for beat in beat_tl] == first_ids
        assert [beat.is_first_in_measure for beat in beat_tl] == [True, False, False]

        commands.execute("edit.redo")
        assert [beat.id for beat in beat_tl] == second_ids

    def test_component_that_cannot_be_restored_is_logged(self, marker_tl):
        # Two markers at one time, which creating a marker refuses and moving one
        # doesn't. This goes when undo no longer checks what it restores.
        marker_tl.create_marker(10)
        moved, _ = marker_tl.create_marker(20)
        id = moved.id
        marker_tl.set_component_data(id, "time", 10)
        _record()
        marker_tl.set_component_data(id, "label", "edited")
        _record()

        with patch("tilia.timelines.base.timeline.logger") as logger:
            commands.execute("edit.undo")

        assert id in logger.error.call_args.args[0]

    def test_a_restore_that_raises_leaves_the_manager_as_it_was(self, marker_tl):
        # The manager would otherwise stop updating other components for good.
        marker_tl.create_marker(10)
        state = marker_tl.get_state()["components"]
        marker_tl.clear()
        component_manager = marker_tl.component_manager

        with patch.object(marker_tl, "create_component", side_effect=RuntimeError):
            with pytest.raises(RuntimeError):
                component_manager.restore_state(state)

        assert component_manager.is_deserializing is False

    def test_components_are_created_in_id_order(self, marker_tl):
        for time, id in enumerate(IDS_ACROSS_A_LENGTH):
            marker_tl.create_marker(time, id=id)
        _record()
        marker_tl.clear()
        _record()

        with _Listener(Post.TIMELINE_COMPONENT_CREATED, 3) as created:
            commands.execute("edit.undo")

        assert created.ids == IDS_ACROSS_A_LENGTH

    def test_components_are_deleted_in_id_order(self, marker_tl):
        for time, id in enumerate(IDS_ACROSS_A_LENGTH):
            marker_tl.create_marker(time, id=id)
        _record()
        marker_tl.clear()
        _record()
        commands.execute("edit.undo")

        with _Listener(Post.TIMELINE_COMPONENT_DELETED, 2) as deleted:
            commands.execute("edit.redo")

        assert deleted.ids == IDS_ACROSS_A_LENGTH

    def test_timelines_are_created_and_deleted_in_id_order(self, tls):
        for id in IDS_ACROSS_A_LENGTH:
            tls.create_timeline(MarkerTimeline, id=id)
        _record()
        for timeline in list(tls):
            tls.delete_timeline(timeline)
        _record()

        with _Listener(Post.TIMELINE_CREATE_DONE, 1) as created:
            commands.execute("edit.undo")
        assert created.ids == IDS_ACROSS_A_LENGTH

        with _Listener(Post.TIMELINE_DELETE_DONE, 0) as deleted:
            commands.execute("edit.redo")
        assert deleted.ids == IDS_ACROSS_A_LENGTH

    def test_timelines_that_stay_are_restored_in_id_order(self, tls):
        for id in IDS_ACROSS_A_LENGTH:
            tls.create_timeline(MarkerTimeline, id=id, name="before")
        _record()
        for timeline in tls:
            tls.set_timeline_data(timeline.id, "name", "after")
        _record()

        with _Listener(Post.TIMELINE_SET_DATA_DONE, 0) as restored:
            commands.execute("edit.undo")

        assert restored.ids == IDS_ACROSS_A_LENGTH


class TestUndoableWithSeveralComponents:
    """`test_undo_does_not_depend_on_the_hash_seed` runs these under several seeds."""

    def test_markers(self, marker_tlui):
        for time in range(10):
            commands.execute("media.seek", time)
            commands.execute("timeline.marker.add")

        marker_tlui.select_all_elements()
        with undoable():
            commands.execute("timeline.component.delete")

    def test_beats(self, beat_tlui):
        _add_beats(range(10))

        beat_tlui.select_all_elements()
        with undoable():
            commands.execute("timeline.component.delete")

    @staticmethod
    def _add_score_components_at_the_same_place(score_tl):
        for staff_index in range(3):
            score_tl.create_component(ComponentKind.STAFF, staff_index, 5)
            score_tl.create_component(
                ComponentKind.CLEF, staff_index, 0, shorthand=Clef.Shorthand.TREBLE
            )
            score_tl.create_component(ComponentKind.BAR_LINE, 0)
            score_tl.create_component(
                ComponentKind.TIME_SIGNATURE, staff_index, 0, 4, 4
            )
            score_tl.create_component(ComponentKind.KEY_SIGNATURE, staff_index, 0, 0)
            score_tl.create_component(ComponentKind.NOTE, 0, 1, 0, 0, 3, staff_index)
        _record()

    def test_score_components_at_the_same_place(self, score_tlui):
        score_tl = score_tlui.timeline
        self._add_score_components_at_the_same_place(score_tl)

        with undoable():
            score_tl.clear()
            _record()

    def test_score_components_at_the_same_place_keep_their_order(self, score_tlui):
        score_tl = score_tlui.timeline
        self._add_score_components_at_the_same_place(score_tl)
        order = [c.id for c in score_tl]
        score_tl.clear()
        _record()

        commands.execute("edit.undo")

        assert [c.id for c in score_tl] == order

    @staticmethod
    def _add_a_score(score_tl):
        for staff_index in range(2):
            score_tl.create_component(ComponentKind.STAFF, staff_index, 5)
            score_tl.create_component(
                ComponentKind.CLEF, staff_index, 0, shorthand=Clef.Shorthand.TREBLE
            )
            score_tl.create_component(ComponentKind.NOTE, 0, 1, 0, 0, 3, staff_index)
        score_tl.create_component(ComponentKind.BAR_LINE, 0)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, score_tl.id)

    def test_undoing_the_import_of_the_same_score_keeps_the_timeline(
        self, score_tlui, tls
    ):
        score_tl = score_tlui.timeline
        timeline_id = score_tl.id
        self._add_a_score(score_tl)
        first_ids = _ids(score_tl)
        _record()
        # What importing does first: tilia/ui/timelines/collection/import_.py
        score_tl.clear()
        self._add_a_score(score_tl)
        assert _ids(score_tl) != first_ids
        _record()

        commands.execute("edit.undo")
        assert tls.get_timeline(timeline_id) is not None
        assert _ids(tls.get_timeline(timeline_id)) == first_ids

        commands.execute("edit.redo")
        assert tls.get_timeline(timeline_id) is not None
        assert _ids(tls.get_timeline(timeline_id)) != first_ids

        commands.execute("edit.undo")
        assert tls.get_timeline(timeline_id) is not None
        assert _ids(tls.get_timeline(timeline_id)) == first_ids

    @staticmethod
    def _add_harmonies_then_a_mode(harmony_tl):
        """Adding the mode changes the `applied_to` of the harmonies after it."""
        for time in range(0, 40, 10):
            harmony_tl.create_harmony(time, step=3, applied_to=3)
        mode, _ = harmony_tl.create_mode(5, step=1)
        assert harmony_tl[1].get_data("applied_to") == 2
        _record()
        return mode

    def test_harmonies_and_a_mode_are_cleared(self, harmony_tlui):
        harmony_tl = harmony_tlui.timeline
        self._add_harmonies_then_a_mode(harmony_tl)

        with undoable():
            harmony_tl.clear()
            _record()

    def test_mode_is_deleted(self, harmony_tlui):
        harmony_tl = harmony_tlui.timeline
        mode = self._add_harmonies_then_a_mode(harmony_tl)

        with undoable():
            harmony_tl.delete_components([mode])
            _record()

    def test_mode_is_edited(self, harmony_tlui):
        harmony_tl = harmony_tlui.timeline
        mode = self._add_harmonies_then_a_mode(harmony_tl)

        with undoable():
            harmony_tl.set_component_data(mode.id, "comments", "edited")
            _record()

    @staticmethod
    def _add_through_commands(harmony_tlui, mode_first):
        """Add two harmonies and a mode, in the given order, as a user does."""
        from tests.ui.timelines.harmony.test_harmony_timeline_ui import (
            add_harmony,
            add_mode,
        )

        def add_the_mode():
            commands.execute("media.seek", 5)
            add_mode(step=1, accidental=0, type="major")

        if mode_first:
            add_the_mode()
        for time in (10, 20):
            commands.execute("media.seek", time)
            add_harmony(step=3, accidental=0, quality="major")
        if not mode_first:
            add_the_mode()
        harmony_tlui.deselect_all_elements()

    @staticmethod
    def _mode_element(harmony_tlui):
        return next(e for e in harmony_tlui if e.get_data("KIND") == ComponentKind.MODE)

    @staticmethod
    def _labels(harmony_tlui):
        """What the labels show, and what they should show."""
        shown = [h.body.toPlainText() for h in harmony_tlui.harmonies()]
        should = [h.label for h in harmony_tlui.harmonies()]
        return shown, should

    @pytest.mark.parametrize("mode_first", [True, False], ids=["older", "newer"])
    def test_labels_are_right_after_undoing_the_deletion_of_a_mode(
        self, harmony_tlui, mode_first
    ):
        self._add_through_commands(harmony_tlui, mode_first)
        with_the_mode = self._labels(harmony_tlui)[1]
        harmony_tlui.select_element(self._mode_element(harmony_tlui))
        commands.execute("timeline.component.delete")
        without_the_mode = self._labels(harmony_tlui)[1]
        assert without_the_mode != with_the_mode

        commands.execute("edit.undo")

        shown, should = self._labels(harmony_tlui)
        assert should == with_the_mode
        assert shown == should

    def test_labels_are_right_after_redoing_the_addition_of_a_newer_mode(
        self, harmony_tlui
    ):
        self._add_through_commands(harmony_tlui, mode_first=False)
        with_the_mode = self._labels(harmony_tlui)[1]

        commands.execute("edit.undo")
        assert self._labels(harmony_tlui)[1] != with_the_mode
        commands.execute("edit.redo")

        shown, should = self._labels(harmony_tlui)
        assert should == with_the_mode
        assert shown == should

    def test_labels_are_right_after_redoing_a_mode_added_to_harmonies_that_name_it(
        self, harmony_tlui
    ):
        harmony_tl = harmony_tlui.timeline
        for time in (10, 20):
            harmony_tl.create_harmony(time, step=3, applied_to=3, display_mode="roman")
        _record()
        harmony_tl.create_mode(5, step=1)
        harmony_tlui.update_harmony_labels()
        _record()
        with_the_mode = self._labels(harmony_tlui)[1]

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        shown, should = self._labels(harmony_tlui)
        assert should == with_the_mode
        assert shown == should

    @pytest.mark.parametrize("mode_first", [True, False], ids=["older", "newer"])
    def test_labels_are_right_after_redoing_the_deletion_of_a_mode(
        self, harmony_tlui, mode_first
    ):
        self._add_through_commands(harmony_tlui, mode_first)
        harmony_tlui.select_element(self._mode_element(harmony_tlui))
        commands.execute("timeline.component.delete")
        without_the_mode = self._labels(harmony_tlui)[1]

        commands.execute("edit.undo")
        commands.execute("edit.redo")

        shown, should = self._labels(harmony_tlui)
        assert should == without_the_mode
        assert shown == should

    def test_hierarchies(self, hierarchy_tlui):
        hierarchy_tl = hierarchy_tlui.timeline
        for start in range(0, 40, 10):
            commands.execute(
                "timeline.hierarchy.add", start=start, end=start + 10, level=2
            )
        _record()

        with undoable():
            hierarchy_tl.clear()
            _record()

    def test_ranges(self, range_tlui):
        for start in range(0, 40, 10):
            commands.execute("timeline.range.add_range", start=start, end=start + 10)
        _record()

        with undoable():
            range_tlui.timeline.clear()
            _record()

    def test_one_of_several_annotations_with_no_order_of_their_own(self, score_tlui):
        score_tl = score_tlui.timeline
        annotations = [
            score_tl.create_component(
                ComponentKind.SCORE_ANNOTATION, x=x, viewer_id=0, text="a", font_size=14
            )[0]
            for x in range(5)
        ]
        _record()

        with undoable():
            score_tl.delete_components([annotations[0]])
            _record()


@pytest.mark.timeout(120)
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_undo_does_not_depend_on_the_hash_seed(seed, tmp_path):
    """The hash seed can only be set when Python starts, so each runs in a pytest
    session of its own.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONHASHSEED"] = str(seed)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp_path / 'basetemp'}",
            f"{__file__}::{TestRestoreById.__name__}",
            f"{__file__}::{TestUndoableWithSeveralComponents.__name__}",
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=110,
    )

    assert result.returncode == 0, result.stdout + result.stderr
