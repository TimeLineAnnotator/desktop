import os
from pathlib import Path
from unittest.mock import patch, mock_open

from tilia.parsers.csv.beat import beats_from_csv


def test_beats_from_csv(beat_tlui):
    os.chdir(Path(Path(__file__).absolute().parents[1]))

    data = "time\n5\n10\n15\n20"

    with patch("builtins.open", mock_open(read_data=data)):
        beats_from_csv(
            beat_tlui.timeline,
            Path(),
        )

    tl = beat_tlui.timeline
    tl.beat_pattern = [2]
    beats = sorted(tl.components)

    assert beats[0].time == 5
    assert beats[1].time == 10
    assert beats[2].time == 15
    assert beats[3].time == 20
