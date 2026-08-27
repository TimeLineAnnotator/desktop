import itertools
import random

from tilia.timelines.hash_timelines import hash_function


class TestComponentOrder:
    def test_components_stay_sorted_after_setting_ordering_attr(
        self, marker_tl, tilia_state
    ):
        for i in range(0, 100, 10):
            marker_tl.create_marker(i)

        for i in range(10):
            marker_tl[i].set_data("time", random.randrange(0, 99))

        for c1, c2 in itertools.pairwise(marker_tl):
            assert c1 < c2 or c1.time == c2.time


class TestHashComponents:
    """Pins the digest's string shape. Changing it invalidates the
    ``components_hash`` of every timeline, so it should not drift silently.
    Order-independence is covered in tests/timelines/score, as score is the
    only kind whose components can share an ordinal.
    """

    def test_is_component_hashes_joined_by_pipes(self, marker_tl):
        marker_tl.create_marker(0)
        marker_tl.create_marker(1)
        first, second = marker_tl[0], marker_tl[1]

        assert marker_tl.component_manager.hash_components() == hash_function(
            f"{first.hash}|{second.hash}|"
        )

    def test_is_hash_of_empty_string_when_there_are_no_components(self, marker_tl):
        assert marker_tl.component_manager.hash_components() == hash_function("")
