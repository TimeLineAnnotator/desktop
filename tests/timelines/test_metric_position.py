"""The measure and beat TiLiA shows for a time: the core's position on the time map
T12's rule chooses (FR-044), and how the inspector shows it."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.mock import Serve
from tilia.file.open_document import OpenDocument
from tilia.requests import Get, Post, get, listen, post, stop_listening
from tilia.timelines.base.metric_position import MetricInterval, MetricPosition
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.ui import commands
from tilia.ui.windows import WindowKind
from tilia.ui.windows.inspect import HIDE_FIELD
from tilia_core import timemap, tla


def test_same_beat_same_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 1, 4) == MetricInterval(1, 0)


def test_same_beat_different_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 1, 3) == MetricInterval(1, 0)


def test_subtrahend_beat_is_larger_same_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 2, 4) == MetricInterval(0, 3)


def test_subtrahend_beat_is_larger_different_beat_count():
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 2, 3) == MetricInterval(0, 3)


def test_result_beat_exceeds_result_measure_count():
    """This can happen in cases where the subtrahend measure is larger than
    the minuend measure"""
    assert MetricPosition(2, 1, 4) - MetricPosition(1, 3, 7) == MetricInterval(0, 5)


def test_a_fractional_beat_is_subtracted_as_it_is():
    assert MetricPosition(5, 3, 4) - MetricPosition(4, 1.5, 4) == MetricInterval(1, 1.5)


class TestHowItShows:
    @pytest.mark.parametrize(
        "beat, shown",
        [
            (2.37, "12.2.37"),
            (2.0, "12.2"),
            (2, "12.2"),
            (2.5, "12.2.50"),
            (2.371, "12.2.37"),
            (2.999, "12.3"),
        ],
    )
    def test_the_beat_to_two_decimals_and_a_whole_beat_without(self, beat, shown):
        assert str(MetricPosition(12, beat, 4, "12")) == shown

    def test_the_measure_s_label(self):
        assert str(MetricPosition(16, 2.25, 4, "16a")) == "16a.2.25"

    def test_the_number_without_a_label(self):
        assert str(MetricPosition(3, 1, 4)) == "3.1"


def add_beats(timeline, times):
    for time in times:
        timeline.create_component(ComponentKind.BEAT, float(time))


def position(time):
    return get(Get.METRIC_POSITION, time)


class TestPositionsFromTheTimeMap:
    def test_a_marker_at_12_5_s_has_the_core_s_position(
        self, tilia, beat_tl, marker_tl
    ):
        add_beats(beat_tl, range(20))
        marker, _ = marker_tl.create_component(ComponentKind.MARKER, 12.5)

        # Half-way from the first beat of measure 4 to its second. TiLiA's own
        # lookup gave the nearer beat, a whole one.
        shown = marker.metric_position
        assert (shown.measure, shown.beat) == (4, 1.5)
        assert (shown.measure_beat_count, shown.label) == (4, "4")
        tilia.sync_document()
        found = timemap.find_time_map(tilia.file_manager.file.document)
        core = found.time_map.positions(12.5, 12.5)
        assert (marker.measure, marker.beat) == (core.bar, core.beat)

    def test_a_time_on_a_beat(self, beat_tl):
        add_beats(beat_tl, range(20))
        assert (position(13.0).measure, position(13.0).beat) == (4, 2)
        # Within the tolerance of a beat, the core puts it on the beat.
        assert position(13.05).beat == 2

    def test_no_beat_timeline_gives_none(self, marker_tl):
        marker, _ = marker_tl.create_component(ComponentKind.MARKER, 1.0)
        assert position(1.0) is None
        assert marker.metric_position is None
        assert (marker.measure, marker.beat) == (None, None)

    def test_a_beat_timeline_without_beats_gives_none(self, beat_tl):
        assert position(1.0) is None

    def test_one_beat_gives_none(self, beat_tl):
        add_beats(beat_tl, [1])
        assert position(1.0) is None
        assert position(1.5) is None

    def test_a_time_before_the_first_beat_gives_none(self, beat_tl):
        add_beats(beat_tl, range(5, 13))
        assert position(4.5) is None
        assert position(0.0) is None
        assert position(5.0).measure == 1

    def test_a_time_after_the_closing_barline_gives_none(self, beat_tl):
        # The last beat lasts as long as the one before it: the closing barline
        # is at 13.
        add_beats(beat_tl, range(5, 13))
        assert (position(12.5).measure, position(12.5).beat) == (2, 4.5)
        assert position(13.0) is None
        assert position(13.5) is None
        assert position(50.0) is None

    def test_the_first_beat_timeline_without_a_role(self, tls):
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        second = tls.create_timeline(BeatTimeline, [], beat_pattern=[2])
        add_beats(first, range(20))
        add_beats(second, range(20))
        assert position(12.0).measure == 4
        assert tls.time_map_found().guessed

    def test_the_beat_timeline_whose_role_is_time_map(self, tls):
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        second = tls.create_timeline(
            BeatTimeline, [], beat_pattern=[2], fields={"role": "time_map"}
        )
        add_beats(first, range(20))
        add_beats(second, range(20))
        # The second's measures have two beats: the 13th beat starts its 7th.
        assert position(12.0).measure == 7
        assert tls.time_map_found().timeline_id == second.id

    def test_a_role_given_later(self, tls):
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        second = tls.create_timeline(BeatTimeline, [], beat_pattern=[2])
        add_beats(first, range(20))
        add_beats(second, range(20))
        assert position(12.0).measure == 4

        tls.set_timeline_data(second.id, "fields", {"role": "time_map"})

        assert position(12.0).measure == 7

    def test_the_order_of_the_beat_timelines(self, tls):
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        second = tls.create_timeline(BeatTimeline, [], beat_pattern=[2])
        add_beats(first, range(20))
        add_beats(second, range(20))
        assert position(12.0).measure == 4

        tls.permute_ordinal(first, second)

        assert position(12.0).measure == 7

    def test_the_beat_timeline_chosen(self, tls):
        # What the score viewer finds its measures on.
        assert tls.get_time_map_timeline() is None
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        # Even without beats, which give no time map.
        assert tls.get_time_map_timeline() is first

        second = tls.create_timeline(
            BeatTimeline, [], beat_pattern=[2], fields={"role": "time_map"}
        )

        assert tls.get_time_map_timeline() is second


class TestTheTimeMapFollowsTheBeats:
    def test_a_beat_added(self, beat_tl):
        add_beats(beat_tl, range(1, 9))
        assert (position(6.5).measure, position(6.5).beat) == (2, 2.5)

        add_beats(beat_tl, [0])

        assert (position(6.5).measure, position(6.5).beat) == (2, 3.5)

    def test_a_beat_deleted(self, beat_tl):
        add_beats(beat_tl, range(9))
        assert (position(6.5).measure, position(6.5).beat) == (2, 3.5)

        beat_tl.delete_components([beat_tl[0]])

        assert (position(6.5).measure, position(6.5).beat) == (2, 2.5)

    def test_a_beat_moved(self, beat_tl):
        add_beats(beat_tl, range(9))
        assert position(6.5).beat == 3.5

        beat_tl.set_component_data(beat_tl[7].id, "time", 6.75)

        assert position(6.5).beat == pytest.approx(3 + 0.5 / 0.75)

    def test_a_measure_number_set(self, beat_tl):
        add_beats(beat_tl, range(9))
        assert position(6.5).measure == 2

        beat_tl.set_measure_number(1, 10)

        assert position(6.5).measure == 10

    def test_a_measure_number_reset_before_the_action_is_recorded(self, beat_tl):
        add_beats(beat_tl, range(12))
        # A number set to 0 isn't forced to show.
        beat_tl.set_measure_number(1, 0)
        post(Post.APP_STATE_RECORD, "measure number")
        assert position(6.5).measure == 0

        beat_tl.reset_measure_number(1)

        assert position(6.5).measure == 2

    def test_the_beats_in_a_measure_set(self, beat_tl):
        add_beats(beat_tl, range(9))
        assert position(6.5).measure == 2

        # Measure 1 has two beats, measure 2 the next four: beat 6 starts measure 3.
        beat_tl.set_beat_amount_in_measure(0, 2)

        assert (position(6.5).measure, position(6.5).beat) == (3, 1.5)

    def test_a_beat_timeline_deleted(self, tls, beat_tl):
        add_beats(beat_tl, range(9))
        assert position(6.5).measure == 2

        tls.delete_timeline(beat_tl)

        assert position(6.5) is None

    def test_a_change_without_a_post_once_the_action_is_recorded(self, tls, beat_tl):
        add_beats(beat_tl, range(9))
        assert position(13.0) is None

        # Scaling sets the beats' times without a post.
        tls.scale_timeline_components(2)
        post(Post.APP_STATE_RECORD, "scale")

        assert (position(13.0).measure, position(13.0).beat) == (2, 3.5)

    def test_undo_and_redo(self, beat_tlui):
        for time in range(9):
            commands.execute("timeline.beat.add", time=time)
        beat_tlui.select_element(beat_tlui[0])
        commands.execute("timeline.component.delete")
        assert position(6.5).beat == 2.5

        commands.execute("edit.undo")
        assert position(6.5).beat == 3.5

        commands.execute("edit.redo")
        assert position(6.5).beat == 2.5

    def test_no_sync_while_an_undo_restores_a_state(self, beat_tlui):
        for time in range(10):
            commands.execute("timeline.beat.add", time=time)
        asked = []
        synced_as_a_person_s_edit = []
        original_sync = OpenDocument.sync

        def sync(file, state, *, by_person=True, back_to=None):
            if by_person:
                synced_as_a_person_s_edit.append(state)
            original_sync(file, state, by_person=by_person, back_to=back_to)

        def ask(*_):
            asked.append(position(6.5))

        # Something asks for a position while the undo takes the last beat away.
        listen(self, Post.TIMELINE_COMPONENT_DELETED, ask)
        try:
            with patch.object(OpenDocument, "sync", sync):
                commands.execute("edit.undo")
        finally:
            stop_listening(self, Post.TIMELINE_COMPONENT_DELETED)

        assert asked
        assert synced_as_a_person_s_edit == []
        # Once the undo has synced, the closing barline is at 9.
        assert position(9.5) is None
        assert position(8.5).measure == 3


class TestTheTimeMapFollowsTheMediaLength:
    """The last beat lasts as long as the one before it, or until the media ends if
    that comes first."""

    @pytest.fixture
    def set_media_length(self, tilia):
        def set_length(length):
            tilia.set_file_media_duration(length, scale_timelines="no")

        yield set_length
        tilia.set_file_media_duration(100, scale_timelines="no")
        post(Post.APP_STATE_RECORD, "media length")

    def test_a_media_length_recorded(self, beat_tl, set_media_length):
        add_beats(beat_tl, range(10))
        assert str(position(9.7)) == "3.2.70"

        set_media_length(9.5)
        post(Post.APP_STATE_RECORD, "media length")

        assert position(9.7) is None
        assert str(position(9.3)) == "3.2.60"

    def test_a_media_length_before_the_action_is_recorded(
        self, beat_tl, set_media_length
    ):
        add_beats(beat_tl, range(10))
        assert str(position(9.7)) == "3.2.70"

        set_media_length(9.5)

        assert position(9.7) is None


class TestTheInspector:
    @staticmethod
    def hierarchy_ui(hierarchy_tlui, start, end):
        commands.execute("timeline.hierarchy.add", start=start, end=end, level=1)
        return hierarchy_tlui[0]

    @staticmethod
    def note_ui(score_tlui, start, end):
        timeline = score_tlui.timeline
        timeline.create_component(ComponentKind.STAFF, 0, 5)
        timeline.create_component(
            ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE
        )
        note, _ = timeline.create_component(ComponentKind.NOTE, start, end, 0, 0, 3, 0)
        return score_tlui.get_component_ui(note)

    @staticmethod
    def shown(element):
        return element.get_inspector_dict()["Start / end (metric)"]

    def test_a_hierarchy_s_start_and_end(self, beat_tl, hierarchy_tlui):
        add_beats(beat_tl, range(20))
        element = self.hierarchy_ui(hierarchy_tlui, 12.5, 18.0)
        assert self.shown(element) == "4.1.50 / 5.3"

    def test_an_end_off_the_map(self, beat_tl, hierarchy_tlui):
        add_beats(beat_tl, range(20))
        element = self.hierarchy_ui(hierarchy_tlui, 12.5, 30.0)
        assert self.shown(element) == "4.1.50 / -"

    def test_a_start_off_the_map(self, beat_tl, hierarchy_tlui):
        add_beats(beat_tl, range(5, 20))
        element = self.hierarchy_ui(hierarchy_tlui, 1.0, 10.0)
        assert self.shown(element) == "- / 2.2"

    def test_both_off_the_map(self, beat_tl, hierarchy_tlui):
        add_beats(beat_tl, range(5, 9))
        element = self.hierarchy_ui(hierarchy_tlui, 20.0, 30.0)
        assert self.shown(element) == HIDE_FIELD

    def test_without_a_beat_timeline(self, hierarchy_tlui):
        element = self.hierarchy_ui(hierarchy_tlui, 1.0, 2.0)
        assert self.shown(element) == HIDE_FIELD

    def test_the_window_follows_a_move_off_the_map(self, qtui, beat_tl, hierarchy_tlui):
        add_beats(beat_tl, range(20))
        element = self.hierarchy_ui(hierarchy_tlui, 12.5, 18.0)
        hierarchy_tlui.select_element(element)
        commands.execute("timeline.element.inspect")
        widget = qtui._windows[WindowKind.INSPECT].field_name_to_widgets[
            "Start / end (metric)"
        ][1]
        assert widget.text() == "4.1.50 / 5.3"

        hierarchy_tlui.timeline.set_component_data(element.id, "end", 30.0)
        assert widget.text() == "4.1.50 / -"
        assert not widget.isHidden()

        hierarchy_tlui.timeline.set_component_data(element.id, "start", 25.0)
        assert widget.isHidden()

    def test_a_note_s_start_and_end(self, beat_tl, score_tlui):
        add_beats(beat_tl, range(20))
        element = self.note_ui(score_tlui, 12.5, 18.0)
        assert self.shown(element) == "4.1.50 / 5.3"

    def test_a_note_s_end_off_the_map(self, beat_tl, score_tlui):
        add_beats(beat_tl, range(20))
        element = self.note_ui(score_tlui, 12.5, 30.0)
        assert self.shown(element) == "4.1.50 / -"

    def test_a_note_off_the_map(self, beat_tl, score_tlui):
        add_beats(beat_tl, range(5, 9))
        element = self.note_ui(score_tlui, 20.0, 30.0)
        assert self.shown(element) == HIDE_FIELD


def an_id(number: int) -> str:
    return f"019b76da-f000-7000-8000-{number:012d}"


def a_file(tmp_path: Path, timelines: dict) -> Path:
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": an_id(0),
        "time_unit": "seconds",
        "media": {"path": "", "length": 100.0},
        "metadata": {},
        "timelines": timelines,
        "scores": [],
    }
    path = tmp_path / "positions.tla"
    tla.write(path, tla.loads(json.dumps(content).encode()))
    return path


def beats(times, marks, *, ordinal=1, pattern="4", **keys):
    """A beat timeline: a beat at each time, and each of `marks` on the beat at its
    place."""
    components = {}
    for place, time in enumerate(times):
        component = {"kind": "BEAT", "time": float(time)}
        if place in marks:
            component["measure"] = marks[place]
        components[an_id(100 * ordinal + place)] = component
    return {
        "kind": "Beat",
        "name": f"Beats {ordinal}",
        "ordinal": ordinal,
        "height": 35,
        "beat_pattern": pattern,
        **keys,
        "components": components,
    }


def open_file(path) -> bool:
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        return commands.execute("file.open", path)


class TestFromAFile:
    def test_the_second_beat_timeline_whose_role_is_time_map(self, qtui, tls, tmp_path):
        path = a_file(
            tmp_path,
            {
                an_id(1): beats(range(20), {0: {}, 4: {}, 8: {}, 12: {}, 16: {}}),
                an_id(2): beats(
                    range(20),
                    {place: {} for place in range(0, 20, 2)},
                    ordinal=2,
                    pattern="2",
                    metadata={"role": "time_map"},
                ),
            },
        )
        assert open_file(path)

        assert position(12.0).measure == 7
        found = tls.time_map_found()
        assert found.timeline_id == an_id(2)
        assert not found.guessed

    def test_a_measure_s_label(self, qtui, tls, tmp_path):
        path = a_file(
            tmp_path,
            {an_id(1): beats(range(12), {0: {}, 4: {"label": "2a"}, 8: {}})},
        )
        assert open_file(path)

        shown = position(6.5)
        assert (shown.measure, shown.label, shown.beat) == (2, "2a", 3.5)
        assert str(shown) == "2a.3.50"
        assert position(8.0).label == "3"
