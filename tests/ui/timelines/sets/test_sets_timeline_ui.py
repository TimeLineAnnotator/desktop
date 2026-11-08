import importlib

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF

from tests.constants import EXAMPLE_QUARTER_TONES_MUSICXML_PATH
from tests.mock import Serve, patch_file_dialog, patch_yes_or_no_dialog
from tests.ui.timelines.interact import click_timeline_ui_view
from tests.utils import save_and_reopen, wait_until
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.sets.timeline import SetsTimeline
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.sets.timeline import SetBar

pytestmark = [pytest.mark.timeout(60), pytest.mark.draws_scores]


@pytest.fixture(autouse=True)
def delete_web_views():
    yield
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def score_tlui(tluis):
    commands.execute("timelines.add.score", name="Score")
    with Serve(Get.FROM_USER_BEAT_PATTERN, (True, [4])):
        commands.execute("timelines.add.beat", name="Beats")
    for time in range(17):
        commands.execute("timeline.beat.add", time=time)
    tlui = get_timeline_ui(ScoreTimeline)
    with (
        patch_yes_or_no_dialog(False),
        patch_file_dialog(True, [EXAMPLE_QUARTER_TONES_MUSICXML_PATH]),
    ):
        commands.execute("timelines.import.score")
    assert wait_until(lambda: tlui.svg_view.is_score_loaded, timeout=30)
    return tlui


def get_timeline_ui(kind):
    return next(
        (t for t in get(Get.TIMELINE_UIS) if t.timeline_class is kind),
        None,
    )


def get_lane():
    return get_timeline_ui(SetsTimeline)


def get_notes(tlui):
    return [c for c in tlui.timeline if c.KIND == ComponentKind.NOTE]


def get_groups(tlui):
    return [c for c in tlui.timeline if c.KIND == ComponentKind.NOTE_GROUP]


def element_at(tlui, start, staff_index):
    """Beats last 1 s. Staff 0 is the flute, staff 1 the clarinet."""
    return next(
        n.element_id
        for n in sorted(get_notes(tlui), key=lambda n: n.pitch)
        if n.start == start and n.staff_index == staff_index
    )


def create_group(tlui, starts, staff_index=0, **kwargs):
    before = {g.id for g in get_groups(tlui)}
    commands.execute(
        "timeline.score.group.create",
        element_ids=[element_at(tlui, start, staff_index) for start in starts],
        **kwargs,
    )
    return next(g for g in get_groups(tlui) if g.id not in before)


def row_of(bar):
    return int(bar.pos().y() // settings.get("sets_timeline", "row_height"))


def get_bar(group):
    return next(b for b in get_lane().bars if b.span.group_id == group.id)


def click_bar(bar, modifier=None, double=False, item=None):
    point = bar.mapToScene(QPointF(1, 1))
    click_timeline_ui_view(
        get_lane().view, "left", point.x(), point.y(), item or bar, modifier, double
    )


@pytest.fixture
def playing(tilia_state):
    tilia_state.player.is_playing = True
    yield
    tilia_state.player.is_playing = False


def test_ui_class_is_registered_by_its_package():
    # TimelineUI.subclasses() imports the package, not its timeline module. This
    # file's own imports would hide a missing export, so it's checked directly.
    assert importlib.import_module("tilia.ui.timelines.sets").SetsTimelineUI


class TestCreate:
    def test_first_group_adds_the_lane(self, score_tlui):
        assert get_lane() is None
        create_group(score_tlui, [0, 1, 2])
        assert get_lane() and get_lane().get_data("name") == "Sets"

    def test_later_groups_use_the_same_lane(self, score_tlui):
        create_group(score_tlui, [0])
        create_group(score_tlui, [2])
        lanes = [t for t in get(Get.TIMELINE_UIS) if t.timeline_class is SetsTimeline]
        assert len(lanes) == 1
        assert len(lanes[0].bars) == 2

    def test_no_lane_for_a_group_that_was_not_created(self, score_tlui):
        commands.execute("timeline.score.group.create", element_ids=["nope"])
        assert get_lane() is None

    def test_add_from_menu_shows_existing_groups(self, score_tlui):
        create_group(score_tlui, [0, 1])
        commands.execute("timeline.delete", get_lane(), confirm=False)
        assert get_lane() is None

        commands.execute("timelines.add.sets", name="My sets")

        assert get_lane().get_data("name") == "My sets"
        assert len(get_lane().bars) == 1

    def test_deleted_lane_comes_back_with_the_next_group(self, score_tlui):
        create_group(score_tlui, [0, 1])
        commands.execute("timeline.delete", get_lane(), confirm=False)
        create_group(score_tlui, [2, 3])
        assert len(get_lane().bars) == 2


class TestBar:
    def test_spans_the_groups_notes(self, score_tlui):
        group = create_group(score_tlui, [1, 3])
        notes = [n for n in get_notes(score_tlui) if n.element_id in group.element_ids]
        bar = get_bar(group)

        assert bar.span.start == min(n.start for n in notes)
        assert bar.span.end == max(n.end for n in notes)
        assert bar.pos().x() == time_x_converter.get_x_by_time(bar.span.start)
        assert bar.rect().width() == pytest.approx(
            time_x_converter.get_x_by_time(bar.span.end)
            - time_x_converter.get_x_by_time(bar.span.start)
        )

    def test_shows_the_prime_form(self, score_tlui):
        group = create_group(score_tlui, [0, 1, 2])
        assert get_bar(group).text.text() == "(0 5 10)"
        assert get_bar(group).toolTip() == "(0 5 10)"

    def test_shows_the_label_after_the_prime_form(self, score_tlui):
        group = create_group(score_tlui, [0, 1, 2], label="Motif")
        assert get_bar(group).text.text() == "(0 5 10) Motif"

    def test_has_the_groups_color(self, score_tlui):
        group = create_group(score_tlui, [0, 1, 2])
        assert get_bar(group).brush().color().name() == group.color

    def test_moves_with_the_zoom(self, score_tlui):
        group = create_group(score_tlui, [1, 3])
        x_before = get_bar(group).pos().x()

        commands.execute("view.zoom.in")

        assert get_bar(group).pos().x() != x_before
        assert get_bar(group).pos().x() == time_x_converter.get_x_by_time(1)

    def test_follows_the_score_when_timelines_are_scaled(self, score_tlui, tilia_state):
        group = create_group(score_tlui, [1, 3])
        end_before = get_bar(group).span.end

        with patch_yes_or_no_dialog(True):
            tilia_state.duration = tilia_state.duration * 2

        assert get_bar(group).span.end == pytest.approx(end_before * 2)


class TestRows:
    def test_groups_in_sequence_share_a_row(self, score_tlui):
        first = create_group(score_tlui, [0, 1])
        second = create_group(score_tlui, [4, 5])
        assert row_of(get_bar(first)) == row_of(get_bar(second)) == 0
        assert get_lane().get_data("height") == settings.get(
            "sets_timeline", "row_height"
        )

    def test_groups_sounding_together_stack(self, score_tlui):
        first = create_group(score_tlui, [0, 1, 2], staff_index=0)
        second = create_group(score_tlui, [1, 2, 3], staff_index=1)
        assert row_of(get_bar(first)) == 0
        assert row_of(get_bar(second)) == 1
        row_height = settings.get("sets_timeline", "row_height")
        assert get_lane().get_data("height") == 2 * row_height
        assert get_lane().view.height() == 2 * row_height

    def test_row_is_reused_once_free(self, score_tlui):
        create_group(score_tlui, [0, 1, 2], staff_index=0)
        create_group(score_tlui, [1, 2], staff_index=1)
        third = create_group(score_tlui, [5, 6], staff_index=1)
        assert row_of(get_bar(third)) == 0

    def test_lane_shrinks_when_a_group_goes(self, score_tlui):
        create_group(score_tlui, [0, 1, 2], staff_index=0)
        second = create_group(score_tlui, [1, 2, 3], staff_index=1)

        commands.execute("timeline.score.group.delete", group_id=second.id)

        assert get_lane().get_data("height") == settings.get(
            "sets_timeline", "row_height"
        )

    def test_row_height_comes_from_settings(self, score_tlui):
        group = create_group(score_tlui, [0, 1])
        settings.set("sets_timeline", "row_height", 40)
        post(Post.SETTINGS_UPDATED, ["sets_timeline"])
        assert get_lane().get_data("height") == 40
        assert get_bar(group).rect().height() > 30


class TestFollowsGroups:
    def test_label(self, score_tlui):
        group = create_group(score_tlui, [0, 1, 2])
        commands.execute(
            "timeline.score.group.set_label", group_id=group.id, label="New"
        )
        assert get_bar(group).text.text() == "(0 5 10) New"

    def test_color(self, score_tlui):
        group = create_group(score_tlui, [0, 1, 2])
        commands.execute(
            "timeline.score.group.set_color", group_id=group.id, color="#123456"
        )
        assert get_bar(group).brush().color().name() == "#123456"

    def test_notes(self, score_tlui):
        group = create_group(score_tlui, [0, 1])
        commands.execute(
            "timeline.score.group.set_notes",
            group_id=group.id,
            element_ids=[element_at(score_tlui, 5, 0)],
        )
        assert get_bar(group).span.start == 5

    def test_delete(self, score_tlui):
        group = create_group(score_tlui, [0, 1])
        commands.execute("timeline.score.group.delete", group_id=group.id)
        assert get_lane().bars == []

    def test_score_timeline_deleted(self, score_tlui):
        create_group(score_tlui, [0, 1])
        commands.execute("timeline.delete", score_tlui, confirm=False)
        assert get_lane().bars == []


class TestUndoRedo:
    def test_undo_first_group_removes_the_lane(self, score_tlui):
        create_group(score_tlui, [0, 1])
        commands.execute("edit.undo")
        assert get_groups(score_tlui) == []
        assert get_lane() is None

    def test_redo_brings_the_lane_back(self, score_tlui):
        create_group(score_tlui, [0, 1])
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert len(get_lane().bars) == 1

    def test_undo_second_group(self, score_tlui):
        create_group(score_tlui, [0, 1, 2], staff_index=0)
        create_group(score_tlui, [1, 2, 3], staff_index=1)
        commands.execute("edit.undo")
        assert len(get_lane().bars) == 1
        assert get_lane().get_data("height") == settings.get(
            "sets_timeline", "row_height"
        )


class TestSaveAndLoad:
    def test_lane_is_saved(self, score_tlui, tmp_path):
        create_group(score_tlui, [0, 1, 2], staff_index=0)
        create_group(score_tlui, [1, 2, 3], staff_index=1, label="B")
        height = get_lane().get_data("height")

        save_and_reopen(tmp_path)

        texts = [b.span.text for b in get_lane().bars]
        assert len(texts) == 2
        assert "(0 5 10)" in texts
        assert any(text.endswith(" B") for text in texts)
        assert get_lane().get_data("height") == height

    def test_hidden_lane_stays_hidden(self, score_tlui, tmp_path):
        create_group(score_tlui, [0, 1])
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            get_lane().id, "is_visible", False
        )
        save_and_reopen(tmp_path)
        assert get_lane().get_data("is_visible") is False


class TestClick:
    def test_click_seeks(self, score_tlui, tilia_state):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        click_bar(bar)
        assert tilia_state.current_time == 2

    def test_click_on_the_text_seeks(self, score_tlui, tilia_state):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        click_bar(bar, item=bar.text)
        assert tilia_state.current_time == 2

    def test_click_does_not_seek_while_playing(self, score_tlui, tilia_state, playing):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        click_bar(bar)
        assert tilia_state.current_time == 0

    def test_double_click_seeks_while_playing(self, score_tlui, tilia_state, playing):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        click_bar(bar, double=True)
        assert tilia_state.current_time == 2

    def test_alt_click_does_not_seek(self, score_tlui, tilia_state):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        click_bar(bar, modifier="alt")
        assert tilia_state.current_time == 0

    def test_click_activates_the_group_in_the_viewer(self, score_tlui):
        view = score_tlui.svg_view
        first = create_group(score_tlui, [0, 1])
        assert wait_until(lambda: view.active_group_id == first.id)
        second = create_group(score_tlui, [2, 3])
        assert wait_until(lambda: view.active_group_id == second.id)

        click_bar(get_bar(first))

        assert wait_until(lambda: view.active_group_id == first.id)

    def test_click_on_an_empty_part_does_nothing(self, score_tlui, tilia_state):
        create_group(score_tlui, [2, 3])
        click_timeline_ui_view(get_lane().view, "left", 1, 1, None)
        assert tilia_state.current_time == 0

    def test_a_real_item_at_the_bar_is_the_bar_or_its_text(self, score_tlui):
        bar = get_bar(create_group(score_tlui, [2, 3]))
        point = bar.mapToScene(QPointF(1, 1))
        item = get_lane().view.itemAt(int(point.x()), int(point.y()))
        assert isinstance(item, SetBar) or isinstance(item.parentItem(), SetBar)
