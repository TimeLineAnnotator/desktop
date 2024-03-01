import random


class TestComponentOrder:
    def test_components_stay_sorted_after_setting_ordering_attr(
        self, marker_tl, tilia_state
    ):
        for i in range(0, 100, 10):
            marker_tl.create_marker(i)

        for i in range(10):
            marker_tl[i].set_data("time", random.randrange(0, 99))

        comps = marker_tl.components

        assert all(
            [
                comps[i] < comps[i + 1] or comps[i].time == comps[i + 1].time
                for i in range(len(comps) - 1)
            ]
        )
