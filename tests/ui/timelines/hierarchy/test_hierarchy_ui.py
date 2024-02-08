from unittest.mock import Mock, patch

import pytest

from tests.mock import PatchPost
from tilia.requests import Post
from tilia.ui.timelines.hierarchy import HierarchyUI


class TestHierarchyUI:
    def test_create(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        assert hui

    def test_full_name(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1, label="hui")
        hierarchy_tlui.set_data("name", "tl")

        assert hui.full_name == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + "hui"

    def test_full_name_no_label(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.set_data("name", "tl")

        assert (
            hui.full_name
            == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + HierarchyUI.NAME_WHEN_UNLABELED
        )

    def test_full_name_with_parent(self, hierarchy_tlui):
        child, child_ui = hierarchy_tlui.create_hierarchy(0, 1, 1, label="child")
        parent, _ = hierarchy_tlui.create_hierarchy(0, 1, 2, label="parent")
        grandparent, _ = hierarchy_tlui.create_hierarchy(0, 1, 3, label="grandparent")

        hierarchy_tlui.relate_hierarchies(parent, [child])
        hierarchy_tlui.relate_hierarchies(grandparent, [parent])

        sep = HierarchyUI.FULL_NAME_SEPARATOR

        hierarchy_tlui.set_data("name", "tl")

        assert (
            child_ui.full_name
            == "tl" + sep + "grandparent" + sep + "parent" + sep + "child"
        )

    def test_right_click(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        with patch('tilia.ui.timelines.hierarchy.context_menu.HierarchyContextMenu.exec') as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()


class TestPreStartIndicator:
    @pytest.fixture(autouse=True)
    def _tlui(self, hierarchy_tlui):
        self.tlui = hierarchy_tlui

    def test_has_pre_start_when_element_has_pre_start(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        assert hui.has_pre_start

    def test_has_pre_start_when_element_has_no_pre_start(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1)

        assert not hui.has_pre_start

    def test_update_position_preserves_undrawn_pre_start(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1)

        assert hui.pre_start_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        self.tlui.select_element(hui)
        assert hui.pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        _, asc = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        self.tlui.select_element(asc)

        assert hui.pre_start_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)
        _, asc = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        self.tlui.select_element(hui)

        assert hui.pre_start_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        self.tlui.select_element(dsc)

        assert hui.pre_start_handle.isVisible() is False
        assert dsc.pre_start_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        self.tlui.select_element(hui)
        self.tlui.select_element(dsc)

        assert hui.pre_start_handle.isVisible() is True
        assert dsc.pre_start_handle.isVisible() is False

    @pytest.mark.xfail(reason="feature not implemented")
    def test_display_as_deselected_with_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        self.tlui.select_element(hui)
        self.tlui.select_element(dsc)
        self.tlui.deselect_element(hui)

        assert hui.pre_start_handle.isVisible() is False
        assert dsc.pre_start_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not implemented")
    def test_display_as_deselected_with_two_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 3, pre_start=0)
        _, child = self.tlui.create_hierarchy(0.1, 1, 2, pre_start=0)
        _, grandchild = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        self.tlui.select_element(hui)
        self.tlui.select_element(child)
        self.tlui.select_element(grandchild)
        self.tlui.deselect_element(hui)

        assert hui.pre_start_handle.isVisible() is False
        assert child.pre_start_handle.isVisible() is True
        assert grandchild.pre_start_handle.isVisible() is False

    def test_display_as_deselected_with_no_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, pre_start=0)

        self.tlui.select_element(hui)
        self.tlui.deselect_element(hui)

        assert hui.pre_start_handle.isVisible() is False


class TestPostEndIndicator:
    @pytest.fixture(autouse=True)
    def _tlui(self, hierarchy_tlui):
        self.tlui = hierarchy_tlui

    def test_has_pre_start_when_element_has_post_end(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.1)

        assert hui.has_post_end

    def test_has_post_end_when_element_has_no_post_end(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1)

        assert not hui.has_post_end

    def test_update_position_preserves_undrawn_post_end(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1)

        assert hui.post_end_handle.isVisible() is False

    def test_display_as_selected_no_ascendant_or_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        self.tlui.select_element(hui)
        assert hui.post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_ascendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        _, asc = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        self.tlui.select_element(asc)

        assert hui.post_end_handle.isVisible() is False

    def test_display_as_selected_with_deselected_ascendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)
        _, asc = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        self.tlui.select_element(hui)

        assert hui.post_end_handle.isVisible() is True

    def test_display_as_selected_with_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        self.tlui.select_element(dsc)

        assert hui.post_end_handle.isVisible() is False
        assert dsc.post_end_handle.isVisible() is True

    def test_display_as_selected_with_deselected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        self.tlui.select_element(hui)
        self.tlui.select_element(dsc)

        assert hui.post_end_handle.isVisible() is True
        assert dsc.post_end_handle.isVisible() is False

    @pytest.mark.xfail(reason="feature not implemented")
    def test_display_as_deselected_with_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        _, dsc = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        self.tlui.select_element(hui)
        self.tlui.select_element(dsc)
        self.tlui.deselect_element(hui)

        assert hui.post_end_handle.isVisible() is False
        assert dsc.post_end_handle.isVisible() is True

    @pytest.mark.xfail(reason="feature not implemented")
    def test_display_as_deselected_with_two_selected_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 3, post_end=1.10)
        _, child = self.tlui.create_hierarchy(0.1, 1, 2, post_end=1.10)
        _, grandchild = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        self.tlui.select_element(hui)
        self.tlui.select_element(child)
        self.tlui.select_element(grandchild)
        self.tlui.deselect_element(hui)

        assert hui.post_end_handle.isVisible() is False
        assert child.post_end_handle.isVisible() is True
        assert grandchild.post_end_handle.isVisible() is False

    def test_display_as_deselected_with_no_descendant(self):
        _, hui = self.tlui.create_hierarchy(0.1, 1, 1, post_end=1.10)

        self.tlui.select_element(hui)
        self.tlui.deselect_element(hui)

        assert hui.post_end_handle.isVisible() is False


class TestDoubleClick:
    def test_posts_seek(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(10, 15, 1)
        with PatchPost(
            "tilia.ui.timelines.hierarchy.element", Post.PLAYER_SEEK
        ) as mock:
            hierarchy_tlui[0].on_double_left_click(None)

        mock.assert_called_with(Post.PLAYER_SEEK, 10)

    def test_does_not_trigger_drag(self, hierarchy_tlui):
        hierarchy_tlui.create_hierarchy(0, 1, 1)
        mock = Mock()
        hierarchy_tlui[0].setup_drag = mock
        hierarchy_tlui[0].on_double_left_click(None)

        mock.assert_not_called()
