import time

import pytest

from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui import commands


class TestBeatTimelinePerf:
    @pytest.mark.timeout(30)
    def test_middle_insert_into_1000_beats_completes_quickly(
        self, beat_tlui, tilia_state
    ):
        tilia_state.duration = 100.0
        beat_tlui.timeline.fill_with_beats(BeatTimeline.FillMethod.BY_AMOUNT, 1000)

        commands.execute("media.seek", 50.0 + 0.05)

        start = time.perf_counter()
        commands.execute("timeline.beat.add")
        elapsed = time.perf_counter() - start

        assert len(beat_tlui) == 1001
        assert elapsed < 2.0, (
            f"Single-beat insert into 1000-beat timeline took {elapsed:.2f}s; "
            "expected < 2.0s. Possible O(N^2) regression in beat-insert path."
        )
