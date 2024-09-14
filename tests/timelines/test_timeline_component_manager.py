import itertools
import random


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
