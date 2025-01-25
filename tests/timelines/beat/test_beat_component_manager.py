class TestBeatTlComponentManager:
    def test_distribute_beats_2beats(self, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        for time in [1, 2, 3, 3.1, 5, 6]:
            beat_tl.create_beat(time)

        beat_tl.distribute_beats(1)

        assert beat_tl[2].time == 3
        assert beat_tl[3].time == 4

    def test_distribute_beats_3beats(self, beat_tl):
        beat_tl.set_data("beat_pattern", [3])
        for time in [1, 2, 3, 4, 4.1, 4.2, 7, 8, 9]:
            beat_tl.create_beat(time)

        beat_tl.distribute_beats(1)

        assert beat_tl[3].time == 4
        assert beat_tl[4].time == 5
        assert beat_tl[5].time == 6
