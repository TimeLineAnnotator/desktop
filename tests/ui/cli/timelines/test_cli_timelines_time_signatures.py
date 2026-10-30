from unittest.mock import patch

import pytest

from tilia.ui.cli.timelines.utils import assert_error
from tilia.ui.timelines.beat.time_signature import TIME_SIGNATURE_BAND_HEIGHT


@pytest.fixture
def beat_tl(cli, tls):
    cli.parse_and_run("timelines add beat --name B1 -b 2")
    tl = tls.get_timelines()[0]
    for time in range(8):
        cli.parse_and_run(f"components beat -o 1 --time {time}")
    yield tl


def assert_only_the_default_beat_unit(tl):
    """Every timeline with beats keeps a beat unit on its first beat."""
    assert [(u.beat_id, u.denominator, u.units) for u in tl.beat_units] == [
        (tl[0].id, 4, "1")
    ]


def time_signatures(tl):
    return [(m.numerator, m.denominator) for m in tl.measure_meters]


class TestSetTimeSignature:
    def test_by_measure_number(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 --measure 2 6/8")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (6, 8), (6, 8)]

    def test_by_measure_index(self, cli, beat_tl):
        cli.parse_and_run(
            "timelines beat time-signatures set -n B1 --measure-index 1 6/8"
        )

        assert time_signatures(beat_tl)[1] == (6, 8)

    def test_this_measure_only(self, cli, beat_tl):
        cli.parse_and_run(
            "timelines beat time-signatures set -o 1 -m 2 6/8 --scope measure"
        )

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (2, 4), (2, 4)]

    def test_the_measure_keeps_its_taps(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 5/4")

        assert time_signatures(beat_tl)[0] == (5, 4)
        assert beat_tl.beats_in_measure[0] == 2

    def test_taps_in_brackets(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 5/8(3 2)")

        assert time_signatures(beat_tl)[0] == (5, 8)
        assert [str(value) for value in beat_tl.measure_meters[0].beat_values] == [
            "3",
            "2",
        ]

    def test_confirms_an_assumed_time_signature(self, cli, beat_tl):
        assert beat_tl.measure_meters[0].is_assumed

        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 2/4")

        assert not beat_tl.measure_meters[0].is_assumed

    def test_a_number_alone_is_assumed(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 6/8")

        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 2")

        assert time_signatures(beat_tl)[0] == (2, 4)
        assert beat_tl.measure_meters[0].is_assumed

    def test_onward_stops_where_the_time_signature_changes(self, cli, tls):
        cli.parse_and_run("timelines add beat --name B -b 2[2/4] 3/4")
        tl = tls.get_timelines()[0]
        for time in range(9):
            cli.parse_and_run(f"components beat -o 1 --time {time}")

        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 6/8")

        assert time_signatures(tl) == [(6, 8), (6, 8), (3, 4), (2, 4)]

    def test_an_unfinished_last_measure_is_set_over_all_its_beats(self, cli, beat_tl):
        cli.parse_and_run("components beat -o 1 --time 8")

        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 5 6/8")
        cli.parse_and_run("components beat -o 1 --time 9")

        assert time_signatures(beat_tl)[4] == (6, 8)

    @pytest.mark.parametrize("text", ["2/4", "2/4(1 1)"])
    def test_a_short_last_measure_takes_one_that_fits_its_taps(self, cli, tls, text):
        cli.parse_and_run("timelines add beat --name B -b 4/4")
        tl = tls.get_timelines()[0]
        for time in range(10):
            cli.parse_and_run(f"components beat -o 1 --time {time}")

        cli.parse_and_run(f"timelines beat time-signatures set -o 1 -m 3 {text}")

        assert time_signatures(tl) == [(4, 4), (4, 4), (2, 4)]
        assert tl.measure_meters[2].starts_here
        assert tl.measure_meters[2].units == (1,)

    @pytest.mark.parametrize(
        "args",
        [
            "-m 9 3/4",
            "--measure-index 9 3/4",
            "-m 1 3/0",
            "-m 1 3/129",
            "-m 1 3/",
            "-m 1 x",
            "-m 1 3/4(1 1 1)",
        ],
    )
    def test_invalid(self, cli, beat_tl, args):
        with assert_error():
            cli.parse_and_run(f"timelines beat time-signatures set -o 1 {args}")

        assert_only_the_default_beat_unit(beat_tl)

    def test_repeated_measure_number_is_refused(self, cli, beat_tl):
        beat_tl.set_measure_number(2, 1)

        with assert_error():
            cli.parse_and_run("timelines beat time-signatures set -o 1 -m 1 3/8")

        assert_only_the_default_beat_unit(beat_tl)


class TestRemoveTimeSignature:
    def test_remove(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 2 6/8")
        beat_count = len(beat_tl)

        cli.parse_and_run("timelines beat time-signatures remove -o 1 -m 2")

        assert time_signatures(beat_tl) == [(2, 4)] * 4
        assert_only_the_default_beat_unit(beat_tl)
        assert len(beat_tl) == beat_count

    def test_no_change_at_measure(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 2 6/8")

        with assert_error():
            cli.parse_and_run("timelines beat time-signatures remove -o 1 -m 3")

        assert len(beat_tl.beat_units) == 2

    def test_a_change_from_the_number_of_taps_is_explained(self, cli, beat_tl):
        beat_tl.set_beat_amount_in_measure(1, 3)

        with patch("tilia.ui.cli.io.error") as error:
            cli.parse_and_run("timelines beat time-signatures remove -o 1 -m 2")

        assert "3/4 because it has 3 taps" in error.call_args.args[0]


class TestListBars:
    def test_list(self, cli, beat_tl):
        cli.parse_and_run("timelines beat time-signatures set -o 1 -m 2 6/8")

        with patch("tilia.ui.cli.io.tabulate") as tabulate:
            cli.parse_and_run("timelines beat time-signatures list -o 1")

        headers, data = tabulate.call_args.args
        assert headers == ["bars", "time signature", "taps"]
        assert data == [
            ("1", "2/4 (assumed)", "1 1"),
            ("2–4", "6/8", "3 3"),
        ]

    def test_empty(self, cli, tls):
        cli.parse_and_run("timelines add beat --name Empty")

        with patch("tilia.ui.cli.io.output") as output:
            cli.parse_and_run("timelines beat time-signatures list -o 1")

        assert "no bars" in output.call_args.args[0]


class TestTimeSignatureVisibility:
    def test_show_and_hide(self, cli, beat_tl):
        beat_tl.set_data("show_time_signatures", False)
        height = beat_tl.height

        cli.parse_and_run("timelines beat time-signatures show -o 1")
        assert beat_tl.show_time_signatures
        assert beat_tl.height == height + TIME_SIGNATURE_BAND_HEIGHT

        cli.parse_and_run("timelines beat time-signatures hide -o 1")
        assert not beat_tl.show_time_signatures
        assert beat_tl.height == height

    def test_showing_twice_changes_height_once(self, cli, beat_tl):
        beat_tl.set_data("show_time_signatures", False)
        height = beat_tl.height

        cli.parse_and_run("timelines beat time-signatures show -o 1")
        cli.parse_and_run("timelines beat time-signatures show -o 1")

        assert beat_tl.height == height + TIME_SIGNATURE_BAND_HEIGHT
