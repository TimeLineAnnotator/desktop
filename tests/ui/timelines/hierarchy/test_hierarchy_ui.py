import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tests.utils import (
    get_blank_file_data,
    save_and_reopen,
    save_tilia_to_tmp_path,
    undoable,
)
from tilia.parsers.csv.hierarchy import import_by_measure, import_by_time
from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI
from tilia.ui.timelines.hierarchy.drag import DRAG_PROXIMITY_LIMIT
from tilia.ui.windows import WindowKind

FORMAL_ATTRS = ("formal_type", "formal_function")
OLD_CSV = "start,end,level,label,formal_type,formal_function\n1,2,1,kept,sonata,opening"


@pytest.fixture
def tlui(hierarchy_tlui):
    return hierarchy_tlui


def assert_has_no_formal_attrs(hierarchy) -> None:
    for attr in FORMAL_ATTRS:
        assert not hasattr(hierarchy, attr)


def write_old_file(tmp_path: Path) -> Path:
    """A file as TiLiA 0.7 saved it, with a formal type and a formal function."""
    file_data = get_blank_file_data()
    file_data["version"] = "0.7.0"
    file_data["media_metadata"]["media length"] = 100.0
    file_data["timelines"]["1"] = {
        "name": "old",
        "kind": "HIERARCHY_TIMELINE",
        "height": 120,
        "is_visible": True,
        "ordinal": 2,
        "components": {
            "2": {
                "start": 0.0,
                "pre_start": 0.0,
                "end": 100.0,
                "post_end": 100.0,
                "level": 1,
                "label": "kept",
                "color": "",
                "formal_type": "sonata",
                "formal_function": "opening",
                "comments": "",
                "kind": "HIERARCHY",
                "hash": "irrelevant",
            }
        },
    }
    path = tmp_path / "old.tla"
    path.write_text(json.dumps(file_data), encoding="utf-8")
    return path


class TestHierarchyUI:
    def test_create(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        assert tlui[0]

    def test_full_name(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1, label="hui")
        tlui.set_data("name", "tl")

        assert tlui[0].full_name == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + "hui"

    def test_full_name_no_label(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        tlui.set_data("name", "tl")

        assert (
            tlui[0].full_name
            == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + HierarchyUI.NAME_WHEN_UNLABELLED
        )

    def test_full_name_with_parent(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="child"
        )
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=2, label="parent"
        )
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=3, label="grandparent"
        )

        sep = HierarchyUI.FULL_NAME_SEPARATOR

        tlui.set_data("name", "tl")

        assert (
            tlui[0].full_name
            == "tl" + sep + "grandparent" + sep + "parent" + sep + "child"
        )

    def test_right_click(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        with patch(
            "tilia.ui.timelines.hierarchy.context_menu.HierarchyContextMenu.exec"
        ) as exec_mock:
            tlui[0].on_right_click(0, 0, None)

        exec_mock.assert_called_once()

    def test_drag_start_handle(self, tlui, hierarchy_tlui, tilia_state):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=tilia_state.duration, level=1
        )
        hierarchy_tlui._trigger_left_click_side_effects(
            hierarchy_tlui[0], hierarchy_tlui[0].start_handle
        )
        time_to_drag = tilia_state.duration / 2
        x_to_drag = time_x_converter.get_x_by_time(time_to_drag)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)
        assert hierarchy_tlui[0].dragged
        assert hierarchy_tlui[0].start_x == time_x_converter.get_x_by_time(time_to_drag)

    def test_drag_end_handle(self, tlui, hierarchy_tlui, tilia_state):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=tilia_state.duration, level=1
        )
        hierarchy_tlui._trigger_left_click_side_effects(
            hierarchy_tlui[0], hierarchy_tlui[0].end_handle
        )
        time_to_drag = tilia_state.duration / 2
        x_to_drag = time_x_converter.get_x_by_time(time_to_drag)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)
        assert hierarchy_tlui[0].dragged
        assert hierarchy_tlui[0].end_x == time_x_converter.get_x_by_time(time_to_drag)

    def test_drag_end_handle_beyond_timeline_end_is_clamped(
        self, tlui, hierarchy_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        hui = hierarchy_tlui[0]
        hierarchy_tlui._trigger_left_click_side_effects(hui, hui.end_handle)

        x_to_drag = time_x_converter.get_x_by_time(tilia_state.duration) + 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("end") == pytest.approx(tilia_state.duration)

    def test_drag_end_handle_cannot_pass_units_start(
        self, tlui, hierarchy_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        hui = hierarchy_tlui[0]
        hierarchy_tlui._trigger_left_click_side_effects(hui, hui.end_handle)

        x_to_drag = hui.start_x - 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("end") > hui.get_data("start")
        assert hui.end_x == pytest.approx(hui.start_x + DRAG_PROXIMITY_LIMIT)

    def test_drag_start_handle_cannot_pass_units_end(
        self, tlui, hierarchy_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        hui = hierarchy_tlui[0]
        hierarchy_tlui._trigger_left_click_side_effects(hui, hui.start_handle)

        x_to_drag = hui.end_x + 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("start") < hui.get_data("end")
        assert hui.start_x == pytest.approx(hui.end_x - DRAG_PROXIMITY_LIMIT)

    def test_drag_start_handle_beyond_timeline_start_is_clamped(
        self, tlui, hierarchy_tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute("timeline.hierarchy.add", start=10, end=50, level=1)
        hui = hierarchy_tlui[0]
        hierarchy_tlui._trigger_left_click_side_effects(hui, hui.start_handle)

        x_to_drag = time_x_converter.get_x_by_time(0) - 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("start") == pytest.approx(0)


class TestPreStartIndicator:
    def test_has_pre_start_when_element_has_pre_start(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )

        assert tlui[0].has_pre_start

    def test_has_pre_start_when_element_has_no_pre_start(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)

        assert not tlui[0].has_pre_start

    def test_update_position_preserves_undrawn_pre_start(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)

        assert tlui[0].pre_start_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )
        tlui.select_element(tlui[0])
        assert tlui[0].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )
        tlui.select_element(tlui[1])

        assert tlui[0].pre_start_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )
        tlui.select_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )

        tlui.select_element(tlui[1])

        assert tlui[0].pre_start_handle.isVisible() is False
        assert tlui[1].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )

        tlui.select_element(tlui[1])
        tlui.select_element(tlui[0])

        assert tlui[1].pre_start_handle.isVisible() is True
        assert tlui[0].pre_start_handle.isVisible() is False

    def test_display_as_deselected_with_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.deselect_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is False
        assert tlui[1].pre_start_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_two_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=3, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, pre_start=0
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )

        child = tlui[1]
        grandchild = tlui[0]

        tlui.select_element(tlui[2])
        tlui.select_element(child)
        tlui.select_element(grandchild)
        tlui.deselect_element(tlui[2])

        assert tlui[2].pre_start_handle.isVisible() is False
        assert child.pre_start_handle.isVisible() is True
        assert grandchild.pre_start_handle.isVisible() is False

    def test_display_as_deselected_with_no_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, pre_start=0
        )

        tlui.select_element(tlui[0])
        tlui.deselect_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is False

    def test_drag_pre_start_handle_cannot_pass_units_start(self, tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute(
            "timeline.hierarchy.add", start=10, end=50, level=1, pre_start=5
        )
        hui = tlui[0]
        tlui.select_element(hui)
        tlui._trigger_left_click_side_effects(hui, hui.pre_start_handle.vertical_line)

        x_to_drag = hui.start_x + 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("pre_start") == pytest.approx(hui.get_data("start"))

    def test_drag_pre_start_handle_beyond_timeline_start_is_clamped(
        self, tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute(
            "timeline.hierarchy.add", start=10, end=50, level=1, pre_start=5
        )
        hui = tlui[0]
        tlui.select_element(hui)
        tlui._trigger_left_click_side_effects(hui, hui.pre_start_handle.vertical_line)

        x_to_drag = time_x_converter.get_x_by_time(0) - 500
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("pre_start") == pytest.approx(0)

    def test_drag_pre_start_handle_normal_drag(self, tlui, tilia_state):
        tilia_state.duration = 100
        commands.execute(
            "timeline.hierarchy.add", start=10, end=50, level=1, pre_start=5
        )
        hui = tlui[0]
        tlui.select_element(hui)
        tlui._trigger_left_click_side_effects(hui, hui.pre_start_handle.vertical_line)

        x_to_drag = time_x_converter.get_x_by_time(2)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)

        assert hui.get_data("pre_start") == pytest.approx(2)


class TestPostEndIndicator:
    def test_has_pre_start_when_element_has_post_end(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.1
        )

        assert tlui[0].has_post_end

    def test_has_post_end_when_element_has_no_post_end(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)

        assert not tlui[0].has_post_end

    def test_update_position_preserves_undrawn_post_end(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0.1, end=1, level=1)

        assert tlui[0].post_end_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )
        tlui.select_element(tlui[0])
        assert tlui[0].post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        tlui.select_element(tlui[1])

        assert tlui[0].post_end_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        tlui.select_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )

        tlui.select_element(tlui[1])

        assert tlui[0].post_end_handle.isVisible() is False
        assert tlui[1].post_end_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )

        tlui.select_element(tlui[1])
        tlui.select_element(tlui[0])

        assert tlui[1].post_end_handle.isVisible() is True
        assert tlui[0].post_end_handle.isVisible() is False

    def test_display_as_deselected_with_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.deselect_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is False
        assert tlui[1].post_end_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_two_selected_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=3, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=2, post_end=1.10
        )
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )
        child = tlui[1]
        grandchild = tlui[2]

        tlui.select_element(tlui[0])
        tlui.select_element(child)
        tlui.select_element(grandchild)
        tlui.deselect_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is False
        assert child.post_end_handle.isVisible() is True
        assert grandchild.post_end_handle.isVisible() is False

    def test_display_as_deselected_with_no_descendant(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0.1, end=1, level=1, post_end=1.10
        )

        tlui.select_element(tlui[0])
        tlui.deselect_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is False

    def test_drag_post_end_handle_onto_end_removes_it_with_child_present(
        self, tlui, tilia_state
    ):
        tilia_state.duration = 100
        commands.execute(
            "timeline.hierarchy.add", start=0, end=50, level=2, post_end=70
        )
        parent = tlui[0]
        tlui.select_element(parent)
        commands.execute("timeline.hierarchy.create_child")
        child = next(e for e in tlui if e is not parent)

        tlui.select_element(parent)
        tlui._trigger_left_click_side_effects(
            parent, parent.post_end_handle.vertical_line
        )
        x_to_drag = parent.end_x
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

        assert not parent.has_post_end
        assert parent.get_data("post_end") == pytest.approx(parent.get_data("end"))
        assert child.get_data("start") == 0
        assert child.get_data("end") == 50


class TestCommentsIndicator:
    @staticmethod
    def create_hierarchy_ui(
        tlui, start: float = 0, end: float = 100, level: float = 1, **kwargs
    ):
        # We use a large "end" to ensure comments icon will fit.
        commands.execute(
            "timeline.hierarchy.add", start=start, end=end, level=level, **kwargs
        )
        hui: HierarchyUI = tlui[0]
        return hui

    def test_is_hidden_when_instantiated_without_comments(self, tlui):
        hui = self.create_hierarchy_ui(tlui)
        assert not hui.comments_icon.isVisible()

    def test_is_visible_when_instantiated_with_comments(self, tlui):
        hui = self.create_hierarchy_ui(tlui, comments="something")
        assert hui.comments_icon.isVisible()

    def test_is_displayed_when_comments_are_set(self, tlui):
        hui = self.create_hierarchy_ui(tlui)
        hui.set_data("comments", "something")

        assert hui.comments_icon.isVisible()

    def test_is_hidden_when_comments_are_deleted(self, tlui):
        hui = self.create_hierarchy_ui(tlui, comments="something")
        hui.set_data("comments", "")
        assert not hui.comments_icon.isVisible()

    def test_still_visible_when_hierarchy_is_moved(self, tlui):
        hui = self.create_hierarchy_ui(tlui, 0, 10, comments="something")
        for i in range(10):
            hui.set_data("start", i)
            assert hui.comments_icon.isVisible()
            hui.set_data("end", i + 10)
            assert hui.comments_icon.isVisible()

    def test_is_hidden_when_hierarchy_is_too_small(self, tlui):
        hui = self.create_hierarchy_ui(tlui, 0, 0.000001, comments="something")
        assert not hui.comments_icon.isVisible()

    def test_is_shown_when_hierarchy_gets_big_enough(self, tlui):
        hui = self.create_hierarchy_ui(tlui, 0, 0.000001, comments="something")
        hui.set_data("end", 100)
        assert hui.comments_icon.isVisible()

    def test_does_not_stack_above_drag_handles(self, tlui):
        # Regression: the comments emoji's bounding box overhangs the end
        # handle's x. If the icon stacks above the handle it wins the itemAt
        # hit-test and the boundary can't be dragged.
        hui = self.create_hierarchy_ui(tlui, comments="something")
        assert hui.comments_icon.zValue() < hui.start_handle.zValue()
        assert hui.comments_icon.zValue() < hui.end_handle.zValue()


class TestDoubleClick:
    def test_posts_seek(self, tlui, tilia_state):
        commands.execute("timeline.hierarchy.add", start=10, end=15, level=1)
        tlui[0].on_double_left_click(None)

        assert tilia_state.current_time == 10

    def test_does_not_trigger_drag(self, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=1, level=1)
        mock = Mock()
        tlui[0].setup_drag = mock
        tlui[0].on_double_left_click(None)

        mock.assert_not_called()


class TestFieldInspectorEdit:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, tlui, element, qtui):
        tlui.select_element(element)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    def test_label_edit_changes_component_and_ui(self, qtui, tlui, tluis, tmp_path):
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=1)
        hui = tlui[0]
        inspector = self.open_inspector_for(tlui, hui, qtui)
        line_edit = inspector.field_name_to_widgets["Label"][1]

        with undoable():
            line_edit.setText("new label")

        assert hui.get_data("label") == "new label"
        assert hui.get_inspector_dict()["Label"] == "new label"
        assert hui.label.toPlainText() == "new label"
        assert hui.full_name.endswith("new label")

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HierarchyTimelineUI)][0]
        assert reloaded_tlui[0].get_data("label") == "new label"

    @staticmethod
    def assert_inspector_shows_no_formal_field(inspector, hui) -> None:
        assert "Label" in inspector.field_name_to_widgets
        for field_name in ("Formal type", "Formal function"):
            assert field_name not in inspector.field_name_to_widgets
            assert field_name not in hui.get_inspector_dict()

    def test_inspector_shows_no_formal_field(self, qtui, tlui):
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=1)
        hui = tlui[0]

        inspector = self.open_inspector_for(tlui, hui, qtui)

        self.assert_inspector_shows_no_formal_field(inspector, hui)

    def test_inspector_shows_no_formal_field_for_an_old_file(
        self, qtui, tluis, tmp_path
    ):
        commands.execute("file.open", path=write_old_file(tmp_path))
        reloaded_tlui = [t for t in tluis if isinstance(t, HierarchyTimelineUI)][0]
        hui = reloaded_tlui[0]

        inspector = self.open_inspector_for(reloaded_tlui, hui, qtui)

        self.assert_inspector_shows_no_formal_field(inspector, hui)

    def test_comments_edit_changes_component_and_ui(self, qtui, tlui, tluis, tmp_path):
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=1)
        hui = tlui[0]
        assert not hui.comments_icon.isVisible()
        inspector = self.open_inspector_for(tlui, hui, qtui)
        comments_edit = inspector.field_name_to_widgets["Comments"][1]

        with undoable():
            comments_edit.setPlainText("some comments")

        assert hui.get_data("comments") == "some comments"
        assert hui.comments_icon.isVisible()

        save_and_reopen(tmp_path)
        reloaded_tlui = [t for t in tluis if isinstance(t, HierarchyTimelineUI)][0]
        reloaded_hui = reloaded_tlui[0]
        assert reloaded_hui.get_data("comments") == "some comments"
        assert reloaded_hui.comments_icon.isVisible()


class TestFormalAttrsAreGone:
    """Hierarchies have no formal type or formal function. A file or a CSV from
    before may still hold them: that isn't an error, and their values are left out.
    """

    @pytest.mark.parametrize(
        "given",
        [
            pytest.param({"formal_type": "sonata"}, id="formal-type"),
            pytest.param({"formal_function": "opening"}, id="formal-function"),
            pytest.param(
                {"formal_type": "sonata", "formal_function": "opening"}, id="both"
            ),
        ],
    )
    def test_hierarchy_given_them_is_created_without_them(self, tlui, given):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="kept", **given
        )

        assert tlui[0].get_data("label") == "kept"
        assert_has_no_formal_attrs(tlui.timeline[0])

    def test_csv_by_time_with_their_columns_is_imported_without_them(
        self, tlui, tmp_path
    ):
        path = tmp_path / "old.csv"
        path.write_text(OLD_CSV, encoding="utf-8")

        assert import_by_time(tlui.timeline, path) == (True, [])

        assert tlui[0].get_data("label") == "kept"
        assert_has_no_formal_attrs(tlui.timeline[0])

    def test_csv_by_measure_with_their_columns_is_imported_without_them(
        self, beat_tlui, tlui, tmp_path
    ):
        beat_tlui.timeline.beat_pattern = [1]
        beat_tlui.create_beat(time=1)
        beat_tlui.create_beat(time=2)
        beat_tlui.timeline.recalculate_measures()
        path = tmp_path / "old.csv"
        path.write_text(OLD_CSV, encoding="utf-8")

        assert import_by_measure(tlui.timeline, beat_tlui.timeline, path) == (True, [])

        assert tlui[0].get_data("label") == "kept"
        assert_has_no_formal_attrs(tlui.timeline[0])

    def test_old_file_holding_them_opens_and_saves_without_them(
        self, tilia, qtui, tluis, tmp_path
    ):
        commands.execute("file.open", path=write_old_file(tmp_path))

        reloaded_tlui = [t for t in tluis if isinstance(t, HierarchyTimelineUI)][0]
        assert reloaded_tlui[0].get_data("label") == "kept"
        assert_has_no_formal_attrs(reloaded_tlui.timeline[0])
        assert not tilia.is_file_modified()

        saved = json.loads(
            Path(save_tilia_to_tmp_path(tmp_path, "saved")).read_text(encoding="utf-8")
        )
        # Read through the migration, the old file's ids are new ones.
        (timeline,) = [
            tl for tl in saved["timelines"].values() if tl["kind"] == "Hierarchy"
        ]
        (component,) = timeline["components"].values()
        assert component["label"] == "kept"
        assert not set(FORMAL_ATTRS) & set(component)

    def test_copy_holds_neither(self, tlui):
        commands.execute(
            "timeline.hierarchy.add", start=0, end=1, level=1, label="copied"
        )
        tlui.select_element(tlui[0])

        commands.execute("timeline.component.copy")

        values = get(Get.CLIPBOARD_CONTENTS)["components"][0]["values"]
        assert values["label"] == "copied"
        assert not set(FORMAL_ATTRS) & set(values)
