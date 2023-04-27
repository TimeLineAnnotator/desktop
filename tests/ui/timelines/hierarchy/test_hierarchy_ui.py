import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.create import create_timeline
from tilia.timelines.hierarchy.common import ParentChildRelation as PCRel
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyUI, HierarchyTimelineUI


@pytest.fixture
def hierarchy_tlui(tl_clct, tlui_clct):
    """
    :param tl_clct: Fixture that returns a TimelineCollection
    :param tlui_clct: Fixture that returns a TimelineUICollection
    :return: A HierarchyTimelineUI with the convenience method 'hui'
    """

    def create_hui(
        start: float = 0, end: float = 1, level: int = 1, **kwargs
    ) -> HierarchyUI:
        """Returns a HierarchyUI"""
        return tl.create_timeline_component(
            ComponentKind.HIERARCHY, start, end, level, **kwargs
        ).ui

    def relate_hierarchy_uis(parent: HierarchyUI, children: list[HierarchyUI]):
        relation = PCRel(
            parent=parent.tl_component, children=[c.tl_component for c in children]
        )
        return tl.component_manager._make_parent_child_relation(relation)

    tl: HierarchyTimeline = create_timeline(
        TimelineKind.HIERARCHY_TIMELINE, tl_clct, tlui_clct
    )
    tl.clear()
    tl.ui.relate_hierarchy_uis = relate_hierarchy_uis
    tl.ui.create_hui = create_hui
    yield tl.ui
    tl_clct.delete_timeline(tl)


class TestHierarchyUI:
    def test_create(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(0, 1, 1)
        assert hui

    def test_full_name(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(label="hui")
        hierarchy_tlui.name = "tl"

        assert hui.full_name == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + "hui"

    def test_full_name_no_label(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui()
        hierarchy_tlui.name = "tl"

        assert (
            hui.full_name
            == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + HierarchyUI.NAME_WHEN_UNLABELED
        )

    def test_full_name_with_parent(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(label="child")
        parent = hierarchy_tlui.create_hui(label="parent")
        grandparent = hierarchy_tlui.create_hui(label="grandparent")

        hierarchy_tlui.relate_hierarchy_uis(parent, [hui])
        hierarchy_tlui.relate_hierarchy_uis(grandparent, [parent])

        sep = HierarchyUI.FULL_NAME_SEPARATOR

        hierarchy_tlui.name = "tl"

        assert (
            hui.full_name == "tl" + sep + "grandparent" + sep + "parent" + sep + "child"
        )

    def test_process_color_before_level_change_default_color(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(label="child")

        hui.process_color_before_level_change(2)

        assert hui.color == hui.get_default_level_color(2)

    def test_process_color_before_level_change_custom_color(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(label="child", color="#1a3a5a")

        hui.process_color_before_level_change(2)

        assert hui.color == "#1a3a5a"

    def test_draw_body(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui()

        id = hui.draw_body()
        x0, y0, x1, y1 = hui.canvas.coords(id)
        assert all([x0, y0, x1, y1])
        assert x1 - x0 == (hui.end_x - hui.start_x) - 2 * hui.XOFFSET
        assert hui.canvas.itemcget(id, "fill") == hui.color

    def test_draw_label(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(label="dummy_label")

        id = hui.draw_label()
        x, y = hui.canvas.coords(id)
        assert x and y
        # check must be done with 'in' to account for cases when display_label != label
        assert hui.canvas.itemcget(id, "text") in "dummy_label"

    def test_draw_coments_indicator(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui(comments=".")

        id = hui.draw_comments_indicator()
        x, y = hui.canvas.coords(id)
        assert x and y
        assert hui.canvas.itemcget(id, "text") == hui.COMMENTS_INDICATOR_CHAR

    def test_draw_coments_indicator_no_comments(self, hierarchy_tlui):
        hui = hierarchy_tlui.create_hui()

        id = hui.draw_comments_indicator()

        assert hui.canvas.itemcget(id, "text") == ""
