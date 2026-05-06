from unittest.mock import patch

import pytest

from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui import commands


@pytest.fixture
def range_cli(cli, tluis):
    """Brings up the UI (so commands are registered) and returns the cli."""
    yield cli


@pytest.fixture
def range_tl(range_cli, tls):
    range_cli.parse_and_run("timelines add range --name R1")
    yield tls.get_timelines()[0]


class TestAddRangeTimeline:
    def test_add_range_timeline(self, range_cli, tls):
        range_cli.parse_and_run("timelines add range --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, RangeTimeline)
        assert tl.name == "test"

    def test_add_range_timeline_short_alias(self, range_cli, tls):
        range_cli.parse_and_run("timelines add rng --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, RangeTimeline)
        assert tl.name == "test"

    def test_add_range_timeline_with_row_height(self, range_cli, tls):
        range_cli.parse_and_run("timelines add range --name test --row-height 75")

        tl = tls.get_timelines()[0]
        assert tl.default_row_height == 75

    def test_add_range_timeline_default_row_height_is_none(self, range_cli, tls):
        range_cli.parse_and_run("timelines add range --name test")

        tl = tls.get_timelines()[0]
        assert tl.default_row_height is None


class TestRowAdd:
    def test_appends_at_end_when_no_index(self, range_cli, range_tl):
        range_cli.parse_and_run("timelines range row add --tl-name R1 --name R2")
        assert [r.name for r in range_tl.rows] == ["Row 0", "R2"]

    def test_inserts_at_index(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row add --tl-name R1 --name R2 --index 0"
        )
        assert [r.name for r in range_tl.rows] == ["R2", "Row 0"]

    def test_passes_color(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row add --tl-name R1 --name R2 --color #112233"
        )
        added = next(r for r in range_tl.rows if r.name == "R2")
        assert added.color == "#112233"

    def test_clamps_high_index_with_warning(self, range_cli, range_tl):
        with patch("tilia.ui.cli.io.warn") as warn:
            range_cli.parse_and_run(
                "timelines range row add --tl-name R1 --name R2 --index 99"
            )
        warn.assert_called()
        assert range_tl.rows[-1].name == "R2"

    def test_clamps_negative_index_with_warning(self, range_cli, range_tl):
        with patch("tilia.ui.cli.io.warn") as warn:
            range_cli.parse_and_run(
                "timelines range row add --tl-name R1 --name R2 --index -5"
            )
        warn.assert_called()
        assert range_tl.rows[0].name == "R2"

    def test_targets_correct_timeline_by_ordinal(self, range_cli, range_tl, tls):
        range_cli.parse_and_run("timelines add range --name R2")
        range_cli.parse_and_run("timelines range row add --tl-ordinal 2 --name added")
        r1, r2 = sorted(tls.get_timelines(), key=lambda t: t.ordinal)
        assert "added" not in [r.name for r in r1.rows]
        assert "added" in [r.name for r in r2.rows]


class TestRowSetHeight:
    def test_sets_row_height(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row set-height --tl-name R1 --height 75"
        )
        assert range_tl.default_row_height == 75


class TestRowList:
    def test_lists_rows(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2", color="#ff0000")
        commands.execute(
            "timeline.range.add_range", row=range_tl.rows[0], start=0, end=5
        )
        with patch("tilia.ui.cli.io.tabulate") as tabulate:
            range_cli.parse_and_run("timelines range row list --tl-name R1")
        tabulate.assert_called_once()
        headers, data = tabulate.call_args.args[:2]
        assert headers == ["index", "name", "color", "ranges"]
        # data is a list of (idx, name, color, ranges) tuples
        rows = list(data)
        assert ("0", "Row 0", "(default)", "1") in rows
        assert ("1", "R2", "#ff0000", "0") in rows

    def test_empty_timeline_message(self, range_cli, range_tl):
        # Drop the auto-created first row by replacing the timeline data
        # directly — there's no public CLI command to remove the last row.
        from tilia.requests import Get, get

        get(Get.TIMELINE_COLLECTION).set_timeline_data(range_tl.id, "rows", [])
        with patch("tilia.ui.cli.io.output") as output:
            range_cli.parse_and_run("timelines range row list --tl-name R1")
        output.assert_called()
        assert "no rows" in output.call_args.args[0]


class TestRowRename:
    def test_by_index(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row rename --tl-name R1 --row-index 0 --new-name X"
        )
        assert range_tl.rows[0].name == "X"

    def test_by_name(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row rename --tl-name R1 " '--row-name "Row 0" --new-name X'
        )
        assert range_tl.rows[0].name == "X"

    def test_unknown_row_name_errors(self, range_cli, range_tl):
        with patch("tilia.ui.cli.io.error") as err:
            range_cli.parse_and_run(
                "timelines range row rename --tl-name R1 "
                "--row-name nope --new-name X"
            )
        err.assert_called()
        assert range_tl.rows[0].name == "Row 0"


class TestRowSetColor:
    def test_sets_color(self, range_cli, range_tl):
        range_cli.parse_and_run(
            "timelines range row set-color --tl-name R1 "
            "--row-index 0 --color #abcdef"
        )
        assert range_tl.rows[0].color == "#abcdef"


class TestRowResetColor:
    def test_clears_color(self, range_cli, range_tl):
        commands.execute(
            "timeline.range.set_row_color", row=range_tl.rows[0], color="#ff0000"
        )
        range_cli.parse_and_run(
            "timelines range row reset-color --tl-name R1 --row-index 0"
        )
        assert range_tl.rows[0].color is None


class TestRowReorder:
    def test_moves_row(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2")
        commands.execute("timeline.range.add_row", name="R3")
        range_cli.parse_and_run(
            "timelines range row reorder --tl-name R1 " "--row-name R3 --new-index 0"
        )
        assert [r.name for r in range_tl.rows] == ["R3", "Row 0", "R2"]

    def test_clamps_out_of_bound_index(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2")
        with patch("tilia.ui.cli.io.warn") as warn:
            range_cli.parse_and_run(
                "timelines range row reorder --tl-name R1 "
                "--row-index 0 --new-index 99"
            )
        warn.assert_called()
        assert range_tl.rows[1].name == "Row 0"


class TestRowRemove:
    def test_removes_by_index(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2")
        range_cli.parse_and_run("timelines range row remove --tl-name R1 --row-index 0")
        assert [r.name for r in range_tl.rows] == ["R2"]

    def test_removes_by_name(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2")
        range_cli.parse_and_run("timelines range row remove --tl-name R1 --row-name R2")
        assert [r.name for r in range_tl.rows] == ["Row 0"]

    def test_remove_drops_ranges_in_row(self, range_cli, range_tl):
        commands.execute("timeline.range.add_row", name="R2")
        commands.execute(
            "timeline.range.add_range", row=range_tl.rows[1], start=0, end=5
        )
        assert len(range_tl) == 1
        range_cli.parse_and_run("timelines range row remove --tl-name R1 --row-name R2")
        assert len(range_tl) == 0

    def test_cannot_remove_last_row(self, range_cli, range_tl):
        assert range_tl.row_count == 1
        with patch("tilia.ui.cli.io.error") as err:
            range_cli.parse_and_run(
                "timelines range row remove --tl-name R1 --row-index 0"
            )
        err.assert_called()
        assert range_tl.row_count == 1


class TestNonRangeTimelineRejected:
    def test_errors_when_target_is_not_range(self, range_cli, tls):
        range_cli.parse_and_run("timelines add marker --name M")
        with patch("tilia.ui.cli.io.error") as err:
            range_cli.parse_and_run("timelines range row add --tl-name M --name X")
        err.assert_called()


class TestRangeCliWithoutUi:
    """Real CLI mode has no QtUI, so commands must run without `Get.TIMELINE_UI`.
    These tests use only `cli` + `tls` (no `tluis`) to lock in headless behaviour."""

    def test_add_row(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run("timelines range row add --tl-name R1 --name R2")
        tl = tls.get_timelines()[0]
        assert [r.name for r in tl.rows] == ["Row 0", "R2"]

    def test_set_row_height(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run("timelines range row set-height --tl-name R1 --height 75")
        assert tls.get_timelines()[0].default_row_height == 75

    def test_rename_row(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run(
            "timelines range row rename --tl-name R1 --row-index 0 --new-name X"
        )
        assert tls.get_timelines()[0].rows[0].name == "X"

    def test_set_and_reset_row_color(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run(
            "timelines range row set-color --tl-name R1 "
            "--row-index 0 --color #abcdef"
        )
        assert tls.get_timelines()[0].rows[0].color == "#abcdef"
        cli.parse_and_run("timelines range row reset-color --tl-name R1 --row-index 0")
        assert tls.get_timelines()[0].rows[0].color is None

    def test_reorder_row(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run("timelines range row add --tl-name R1 --name R2")
        cli.parse_and_run(
            "timelines range row reorder --tl-name R1 " "--row-name R2 --new-index 0"
        )
        assert [r.name for r in tls.get_timelines()[0].rows] == ["R2", "Row 0"]

    def test_remove_row(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run("timelines range row add --tl-name R1 --name R2")
        cli.parse_and_run("timelines range row remove --tl-name R1 --row-name R2")
        assert [r.name for r in tls.get_timelines()[0].rows] == ["Row 0"]

    def test_list_rows(self, cli, tls):
        cli.parse_and_run("timelines add range --name R1")
        cli.parse_and_run("timelines range row add --tl-name R1 --name R2")
        with patch("tilia.ui.cli.io.tabulate") as tabulate:
            cli.parse_and_run("timelines range row list --tl-name R1")
        tabulate.assert_called_once()


def _get_range_timeline(tls):
    matches = [tl for tl in tls.get_timelines() if isinstance(tl, RangeTimeline)]
    assert len(matches) == 1
    return matches[0]


class TestSaveLoadRoundtrip:
    def test_roundtrip_via_cli(self, range_cli, tls, tmp_path):
        range_cli.parse_and_run("timelines add range --name test --row-height 75")
        range_cli.parse_and_run(
            "timelines range row add --tl-name test --name R2 --color #abcdef"
        )

        path = tmp_path / "saved.tla"
        range_cli.parse_and_run(f"save {path}")

        range_cli.parse_and_run("clear --force")
        assert not any(isinstance(t, RangeTimeline) for t in tls.get_timelines())

        range_cli.parse_and_run(f"open {path}")
        tl = _get_range_timeline(tls)
        assert tl.name == "test"
        assert tl.default_row_height == 75
        assert [r.name for r in tl.rows] == ["Row 0", "R2"]
        assert tl.rows[1].color == "#abcdef"

    def test_open_then_save_preserves_state(self, range_cli, tls, tmp_path):
        range_cli.parse_and_run("timelines add range --name original --row-height 60")
        range_cli.parse_and_run("timelines range row add --tl-name original --name R2")
        range_cli.parse_and_run(
            "timelines range row set-color --tl-name original "
            "--row-index 0 --color #112233"
        )

        path = tmp_path / "first.tla"
        range_cli.parse_and_run(f"save {path}")
        range_cli.parse_and_run("clear --force")
        range_cli.parse_and_run(f"open {path}")

        path2 = tmp_path / "second.tla"
        range_cli.parse_and_run(f"save {path2}")
        range_cli.parse_and_run("clear --force")
        range_cli.parse_and_run(f"open {path2}")

        tl = _get_range_timeline(tls)
        assert tl.default_row_height == 60
        assert [r.name for r in tl.rows] == ["Row 0", "R2"]
        assert tl.rows[0].color == "#112233"


class TestRangeScript:
    def test_script_runs_range_commands(self, range_cli, tls, tmp_path):
        script_path = tmp_path / "range.tilia"
        script_path.write_text(
            "\n".join(
                [
                    "# Set up a range timeline with two rows.",
                    "timelines add range --name FromScript --row-height 40",
                    "timelines range row add --tl-name FromScript --name Verses",
                    "timelines range row add --tl-name FromScript --name Choruses --color #abcdef",
                    "timelines range row set-color --tl-name FromScript --row-index 0 --color #112233",
                    "",
                    "# Reorder so Choruses lands first.",
                    "timelines range row reorder --tl-name FromScript --row-name Choruses --new-index 0",
                ]
            )
        )

        range_cli.parse_and_run(f"script {script_path}")

        tl = _get_range_timeline(tls)
        assert tl.name == "FromScript"
        assert tl.default_row_height == 40
        assert [r.name for r in tl.rows] == ["Choruses", "Row 0", "Verses"]
        # Choruses (was added with color)
        assert tl.rows[0].color == "#abcdef"
        # Row 0 (set-color was applied while it was still at index 0)
        assert tl.rows[1].color == "#112233"

    def test_script_save_load_roundtrip(self, range_cli, tls, tmp_path):
        save_path = tmp_path / "from_script.tla"
        script_path = tmp_path / "build_and_save.tilia"
        script_path.write_text(
            "\n".join(
                [
                    "timelines add range --name R1 --row-height 50",
                    "timelines range row add --tl-name R1 --name R2 --color #aa00bb",
                    f"save {save_path}",
                ]
            )
        )

        range_cli.parse_and_run(f"script {script_path}")
        range_cli.parse_and_run("clear --force")
        assert not any(isinstance(t, RangeTimeline) for t in tls.get_timelines())

        range_cli.parse_and_run(f"open {save_path}")
        tl = _get_range_timeline(tls)
        assert tl.default_row_height == 50
        assert [r.name for r in tl.rows] == ["Row 0", "R2"]
        assert tl.rows[1].color == "#aa00bb"
