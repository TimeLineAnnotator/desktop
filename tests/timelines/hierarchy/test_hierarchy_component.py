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
            'level': 2,
            "parent": "test_parent",
            "children": ["test_children"],
            "comments": "test_comments",
            "playback_start": "test_playback_start",
            "playback_end": "test_playback_end",
            "formal_type": "test_formal_type",
            "formal_function": "test_formal_function",
        }

        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            **params
        )

        for attr, value in params.items():
            assert getattr(hrc, attr) == params[attr]

    def test_create_no_playback_start_or_end(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            0, 1, 1
        )

        assert hrc.playback_start == 0
        assert hrc.playback_end == 1

    def test_set_start_changes_playback_start_previously_equal(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1, 2, 1
        )

        hrc.start = 1.5
        assert hrc.playback_start == 1.5

    def test_set_start_changes_playback_start_not_previously_equal_1(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1,
            2,
            1,
            playback_start=0.5
        )

        hrc.start = 0.8
        assert hrc.playback_start == 0.5

    def test_set_start_changes_playback_start_not_previously_equal_2(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1,
            2,
            1,
            playback_start=0.5
        )

        hrc.start = 0.4
        assert hrc.playback_start == 0.4
        
    def test_set_end_changes_playback_end_previously_equal(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1, 2, 1
        )

        hrc.end = 1.5
        assert hrc.playback_end == 1.5

    def test_set_end_changes_playback_end_not_previously_equal_1(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1,
            2,
            1,
            playback_end=2.5
        )

        hrc.end = 2.3
        assert hrc.playback_end == 2.5

    def test_set_end_changes_playback_end_not_previously_equal_2(self):
        hrc = Hierarchy.create(
            DummyHierarchyTL(),
            1,
            2,
            1,
            playback_end=2.5
        )

        hrc.end = 2.8
        assert hrc.playback_end == 2.8
