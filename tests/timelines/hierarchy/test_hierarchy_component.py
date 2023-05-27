import itertools

from tilia.timelines.hierarchy.components import Hierarchy


class DummyHierarchyTL:
    id_counter = itertools.count()

    def get_id_for_component(self):
        return next(self.id_counter)


class TestHierarchyComponent:
    def test_create(self):
        params = {
            "start": 0,
            "end": 1,
            "level": 2,
            "parent": "test_parent",
            "children": ["test_children"],
            'label': 'test_label',
            "comments": "test_comments",
            "pre_start": "test_pre_start",
            "post_end": "test_post_end",
            "formal_type": "test_formal_type",
            "formal_function": "test_formal_function",
        }

        hrc = Hierarchy.create(DummyHierarchyTL(), **params)

        for attr, value in params.items():
            assert getattr(hrc, attr) == params[attr]

    def test_create_no_pre_start_or_end(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 0, 1, 1)

        assert hrc.pre_start == 0
        assert hrc.post_end == 1

    def test_set_start_changes_pre_start_previously_equal(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1)

        hrc.start = 1.5
        assert hrc.pre_start == 1.5

    def test_set_start_changes_pre_start_not_previously_equal_1(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1, pre_start=0.5)

        hrc.start = 0.8
        assert hrc.pre_start == 0.5

    def test_set_start_changes_pre_start_not_previously_equal_2(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1, pre_start=0.5)

        hrc.start = 0.4
        assert hrc.pre_start == 0.4

    def test_set_end_changes_post_end_previously_equal(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1)

        hrc.end = 1.5
        assert hrc.post_end == 1.5

    def test_set_end_changes_post_end_not_previously_equal_1(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1, post_end=2.5)

        hrc.end = 2.3
        assert hrc.post_end == 2.5

    def test_set_end_changes_post_end_not_previously_equal_2(self):
        hrc = Hierarchy.create(DummyHierarchyTL(), 1, 2, 1, post_end=2.5)

        hrc.end = 2.8
        assert hrc.post_end == 2.8
