from tilia.ui.timelines.hierarchy import HierarchyUI


class TestHierarchyUI:
    def test_create(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        assert hui

    def test_full_name(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1, label="hui")
        hierarchy_tlui.name = "tl"

        assert hui.full_name == "tl" + HierarchyUI.FULL_NAME_SEPARATOR + "hui"

    def test_full_name_no_label(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)
        hierarchy_tlui.name = "tl"

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

        hierarchy_tlui.name = "tl"

        assert (
            child_ui.full_name
            == "tl" + sep + "grandparent" + sep + "parent" + sep + "child"
        )

    def test_process_color_before_level_change_default_color(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1, label="child")

        hui.update_color(1, 2)

        assert hui.color == hui.get_default_color(2)

    def test_process_color_before_level_change_custom_color(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(
            0, 1, 1, label="child", color="#1a3a5a"
        )

        hui.update_color(1, 2)

        assert hui.color == "#1a3a5a"

    def test_draw_body(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)

        id = hui.draw_body()
        x0, y0, x1, y1 = hui.canvas.coords(id)
        assert all([x0, y0, x1, y1])
        assert x1 - x0 == (hui.end_x - hui.start_x) - 2 * hui.XOFFSET
        assert hui.canvas.itemcget(id, "fill") == hui.color

    def test_draw_label(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1, label="dummy_label")

        id = hui.draw_label()
        x, y = hui.canvas.coords(id)
        assert x and y
        # check must be done with 'in' to account for cases when display_label != label
        assert hui.canvas.itemcget(id, "text") in "dummy_label"

    def test_draw_coments_indicator(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1, comments=".")

        id = hui.draw_comments_indicator()
        x, y = hui.canvas.coords(id)
        assert x and y
        assert hui.canvas.itemcget(id, "text") == hui.COMMENTS_INDICATOR_CHAR

    def test_draw_coments_indicator_no_comments(self, hierarchy_tlui):
        _, hui = hierarchy_tlui.create_hierarchy(0, 1, 1)

        id = hui.draw_comments_indicator()

        assert hui.canvas.itemcget(id, "text") == ""
