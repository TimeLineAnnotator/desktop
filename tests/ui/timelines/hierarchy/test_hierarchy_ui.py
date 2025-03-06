from unittest.mock import Mock, patch

import pytest

from tests.mock import PatchPost
from tilia.requests import Post, post
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.hierarchy import HierarchyUI


@pytest.fixture
def tlui(hierarchy_tlui):
    return hierarchy_tlui


class TestHierarchyUI:
    def test_create(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        assert tlui[0]

    def test_full_name(self, tlui):
        tlui.create_hierarchy(0, 1, 1, label="hui")
        tlui.set_data("name", "tl")

        assert tlui[0].full_name == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + "hui"

    def test_full_name_no_label(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        tlui.set_data("name", "tl")

        assert (
            tlui[0].full_name
            == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + HierarchyUI.NAME_WHEN_UNLABELED
        )

    def test_full_name_with_parent(self, tlui):
        tlui.create_hierarchy(0, 1, 1, label="child")
        tlui.create_hierarchy(0, 1, 2, label="parent")
        tlui.create_hierarchy(0, 1, 3, label="grandparent")

        sep = HierarchyUI.FULL_NAME_SEPARATOR

        tlui.set_data("name", "tl")

        assert (
            tlui[0].full_name
            == "tl" + sep + "grandparent" + sep + "parent" + sep + "child"
        )

    def test_right_click(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        with patch(
            "tilia.ui.timelines.hierarchy.context_menu.HierarchyContextMenu.exec"
        ) as exec_mock:
            tlui[0].on_right_click(0, 0, None)

        exec_mock.assert_called_once()

    def test_drag_start_handle(self, tlui, hierarchy_tlui, tilia_state):
        hierarchy_tlui.create_hierarchy(0, tilia_state.duration, 1)
        hierarchy_tlui.on_element_left_click(
            hierarchy_tlui[0], hierarchy_tlui[0].start_handle
        )
        time_to_drag = tilia_state.duration / 2
        x_to_drag = time_x_converter.get_x_by_time(time_to_drag)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)
        assert hierarchy_tlui[0].dragged
        assert hierarchy_tlui[0].start_x == time_x_converter.get_x_by_time(time_to_drag)

    def test_drag_end_handle(self, tlui, hierarchy_tlui, tilia_state):
        hierarchy_tlui.create_hierarchy(0, tilia_state.duration, 1)
        hierarchy_tlui.on_element_left_click(
            hierarchy_tlui[0], hierarchy_tlui[0].end_handle
        )
        time_to_drag = tilia_state.duration / 2
        x_to_drag = time_x_converter.get_x_by_time(time_to_drag)
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, x_to_drag, 0)
        assert hierarchy_tlui[0].dragged
        assert hierarchy_tlui[0].end_x == time_x_converter.get_x_by_time(time_to_drag)


class TestPreStartIndicator:
    def test_has_pre_start_when_element_has_pre_start(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        assert tlui[0].has_pre_start

    def test_has_pre_start_when_element_has_no_pre_start(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1)

        assert not tlui[0].has_pre_start

    def test_update_position_preserves_undrawn_pre_start(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1)

        assert tlui[0].pre_start_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        tlui.select_element(tlui[0])
        assert tlui[0].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        tlui.select_element(tlui[1])

        assert tlui[0].pre_start_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        tlui.select_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        tlui.select_element(tlui[1])

        assert tlui[0].pre_start_handle.isVisible() is False
        assert tlui[1].pre_start_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)

        tlui.select_element(tlui[1])
        tlui.select_element(tlui[0])

        assert tlui[1].pre_start_handle.isVisible() is True
        assert tlui[0].pre_start_handle.isVisible() is False

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.deselect_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is False
        assert tlui[1].pre_start_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_two_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 3, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

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
        tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        tlui.select_element(tlui[0])
        tlui.deselect_element(tlui[0])

        assert tlui[0].pre_start_handle.isVisible() is False


class TestPostEndIndicator:
    def test_has_pre_start_when_element_has_post_end(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.1)

        assert tlui[0].has_post_end

    def test_has_post_end_when_element_has_no_post_end(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1)

        assert not tlui[0].has_post_end

    def test_update_position_preserves_undrawn_post_end(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1)

        assert tlui[0].post_end_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        tlui.select_element(tlui[0])
        assert tlui[0].post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.select_element(tlui[1])

        assert tlui[0].post_end_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.select_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        tlui.select_element(tlui[1])

        assert tlui[0].post_end_handle.isVisible() is False
        assert tlui[1].post_end_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        tlui.select_element(tlui[1])
        tlui.select_element(tlui[0])

        assert tlui[1].post_end_handle.isVisible() is True
        assert tlui[0].post_end_handle.isVisible() is False

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        tlui.select_element(tlui[0])
        tlui.select_element(tlui[1])
        tlui.deselect_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is False
        assert tlui[1].post_end_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not reimplemented")
    def test_display_as_deselected_with_two_selected_descendant(self, tlui):
        tlui.create_hierarchy(0.1, 1, 3, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
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
        tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        tlui.select_element(tlui[0])
        tlui.deselect_element(tlui[0])

        assert tlui[0].post_end_handle.isVisible() is False


class TestDoubleClick:
    def test_posts_seek(self, tlui):
        tlui.create_hierarchy(10, 15, 1)
        with PatchPost(
            "tilia.ui.timelines.hierarchy.element", Post.PLAYER_SEEK
        ) as mock:
            tlui[0].on_double_left_click(None)

        mock.assert_called_with(Post.PLAYER_SEEK, 10)

    def test_does_not_trigger_drag(self, tlui):
        tlui.create_hierarchy(0, 1, 1)
        mock = Mock()
        tlui[0].setup_drag = mock
        tlui[0].on_double_left_click(None)

        mock.assert_not_called()
