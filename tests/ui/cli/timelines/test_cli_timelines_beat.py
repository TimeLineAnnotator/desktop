from unittest.mock import patch

import pytest

from tilia.ui.cli.timelines.utils import assert_error


@pytest.fixture
def beat_tl(cli, tls):
    cli.parse_and_run("timelines add beat --name B1")
    yield tls.get_timelines()[0]


def add_beats(cli, times):
    for time in times:
        cli.parse_and_run(f"components beat -o 1 --time {time}")


class TestSetPattern:
    def test_bracketed_pattern(self, cli, beat_tl):
        add_beats(cli, range(10))

        cli.parse_and_run("timelines beat pattern set -o 1 2[3] 4")

        assert beat_tl.beat_pattern == "2[3] 4"
        assert beat_tl.beats_in_measure == [3, 3, 4]

    def test_by_name(self, cli, beat_tl):
        cli.parse_and_run("timelines beat pattern set -n B1 3")

        assert beat_tl.beat_pattern == "3"

    def test_invalid_pattern(self, cli, beat_tl):
        with assert_error():
            cli.parse_and_run("timelines beat pattern set -o 1 2[")

        assert beat_tl.beat_pattern == "4"

    def test_non_beat_timeline(self, cli, tls):
        cli.parse_and_run("timelines add marker --name M")

        with assert_error():
            cli.parse_and_run("timelines beat pattern set -o 1 3")

    def test_missing_timeline(self, cli, beat_tl):
        with assert_error():
            cli.parse_and_run("timelines beat pattern set -o 5 3")


class TestSetPatternOverHandSetBars:
    @pytest.fixture
    def hand_set_tl(self, cli, beat_tl):
        add_beats(cli, range(12))
        beat_tl.set_beat_amount_in_measure(1, 3)
        assert beat_tl.beats_in_measure == [4, 3, 4, 1]
        yield beat_tl

    def test_declining_keeps_bars(self, cli, hand_set_tl):
        with patch("tilia.ui.cli.io.ask_yes_or_no", return_value=False) as ask:
            cli.parse_and_run("timelines beat pattern set -o 1 4")

        ask.assert_called_once()
        assert "measures 2" in ask.call_args.args[0]
        assert hand_set_tl.beats_in_measure == [4, 3, 4, 1]

    def test_accepting_overwrites(self, cli, hand_set_tl):
        with patch("tilia.ui.cli.io.ask_yes_or_no", return_value=True):
            cli.parse_and_run("timelines beat pattern set -o 1 4")

        assert hand_set_tl.beats_in_measure == [4, 4, 4]

    def test_yes_skips_the_question(self, cli, hand_set_tl):
        with patch("tilia.ui.cli.io.ask_yes_or_no") as ask:
            cli.parse_and_run("timelines beat pattern set -o 1 4 --yes")

        ask.assert_not_called()
        assert hand_set_tl.beats_in_measure == [4, 4, 4]
