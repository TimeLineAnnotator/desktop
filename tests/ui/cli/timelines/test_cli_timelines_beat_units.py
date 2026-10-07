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


class TestSetUnit:
    def test_by_measure_number(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 --measure 2 -d 8 -u 3")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (6, 8), (6, 8)]

    def test_by_measure_index(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -n B1 --measure-index 1 -d 8 -u 3")

        assert time_signatures(beat_tl)[1] == (6, 8)

    def test_this_measure_only(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 -m 2 -d 8 -u 3 --scope measure")

        assert time_signatures(beat_tl) == [(2, 4), (6, 8), (2, 4), (2, 4)]

    def test_fractional_and_grouped_units(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 -m 1 -d 4 -u 2+1/2")

        assert time_signatures(beat_tl)[0] == (pytest.approx(2.5), 4)

    @pytest.mark.parametrize(
        "args",
        [
            "-m 9 -d 4 -u 1",
            "--measure-index 9 -d 4 -u 1",
            "-m 1 -d 0 -u 1",
            "-m 1 -d 129 -u 1",
            "-m 1 -d 4 -u 2+",
            "-m 1 -d 4 -u 1.5",
        ],
    )
    def test_invalid(self, cli, beat_tl, args):
        with assert_error():
            cli.parse_and_run(f"timelines beat unit set -o 1 {args}")

        assert_only_the_default_beat_unit(beat_tl)

    def test_repeated_measure_number_is_refused(self, cli, beat_tl):
        beat_tl.set_measure_number(2, 1)

        with assert_error():
            cli.parse_and_run("timelines beat unit set -o 1 -m 1 -d 8 -u 1")

        assert_only_the_default_beat_unit(beat_tl)


class TestRemoveUnit:
    def test_remove(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 -m 2 -d 8 -u 3")

        cli.parse_and_run("timelines beat unit remove -o 1 -m 2")

        assert_only_the_default_beat_unit(beat_tl)

    def test_no_unit_at_measure(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 -m 2 -d 8 -u 3")

        with assert_error():
            cli.parse_and_run("timelines beat unit remove -o 1 -m 3")

        assert len(beat_tl.beat_units) == 2


class TestListUnits:
    def test_list(self, cli, beat_tl):
        cli.parse_and_run("timelines beat unit set -o 1 -m 2 -d 8 -u 3")

        with patch("tilia.ui.cli.io.tabulate") as tabulate:
            cli.parse_and_run("timelines beat unit list -o 1")

        headers, data = tabulate.call_args.args
        assert headers == [
            "measure",
            "beat time",
            "denominator",
            "units",
            "time signature",
        ]
        assert data == [
            ("1", "0.0", "4", "1", "2/4 (assumed)"),
            ("2", "2.0", "8", "3", "6/8"),
        ]

    def test_empty(self, cli, tls):
        # Only a timeline without beats has no beat units.
        cli.parse_and_run("timelines add beat --name Empty")

        with patch("tilia.ui.cli.io.output") as output:
            cli.parse_and_run("timelines beat unit list -o 1")

        assert "no beat units" in output.call_args.args[0]


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
