from tilia.timelines.component_kinds import ComponentKind


class TestHierarchyComponent:
    def test_create_no_pre_start_or_end(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(ComponentKind.HIERARCHY, 0, 1, 1)

        assert hrc.pre_start == 0
        assert hrc.post_end == 1

    def test_set_start_changes_pre_start_previously_equal(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(ComponentKind.HIERARCHY, 1, 2, 1)

        hrc.start = 1.5
        assert hrc.pre_start == 1.5

    def test_set_start_changes_pre_start_not_previously_equal_1(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(
            ComponentKind.HIERARCHY, 1, 2, 1, pre_start=0.5
        )

        hrc.start = 0.8
        assert hrc.pre_start == 0.5

    def test_set_start_changes_pre_start_not_previously_equal_2(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(
            ComponentKind.HIERARCHY, 1, 2, 1, pre_start=0.5
        )

        hrc.start = 0.4
        assert hrc.pre_start == 0.4

    def test_set_end_changes_post_end_previously_equal(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(ComponentKind.HIERARCHY, 1, 2, 1)

        hrc.end = 1.5
        assert hrc.post_end == 1.5

    def test_set_end_changes_post_end_not_previously_equal_1(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(
            ComponentKind.HIERARCHY, 1, 2, 1, post_end=2.5
        )

        hrc.end = 2.3
        assert hrc.post_end == 2.5

    def test_set_end_changes_post_end_not_previously_equal_2(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_component(
            ComponentKind.HIERARCHY, 1, 2, 1, post_end=2.5
        )

        hrc.end = 2.8
        assert hrc.post_end == 2.8
