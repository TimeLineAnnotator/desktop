import pytest

from tests.constants import EXAMPLE_MUSICXML_PATH
from tests.mock import Serve
from tilia.requests import Get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui.cli.timelines.imp import (
    get_timelines_for_import,
    validate_timelines_for_import,
)

GET_TIMELINES_FOR_IMPORT_PATH = "tilia.ui.cli.timelines.imp.get_timelines_for_import"
CSV_PARSER_PATH = "tilia.parsers.csv"


def tmp_csv(tmp_path, data):
    with open(tmp_path / "tmp.csv", "w") as f:
        f.write(data)
    return tmp_path / "tmp.csv"


class TestImportTimeline:
    def test_markers_by_measure(self, cli, marker_tl, beat_tl, tmp_path):
        beat_tl.beat_pattern = [1]
        for i in range(5):
            beat_tl.create_beat(i)

        data = "measure\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import marker by-measure --target-ordinal 1 --reference-tl-ordinal 2 --file {str(csv_path.resolve())}"
        )
        for i in range(5):
            assert marker_tl[i].get_data("time") == i

    def test_markers_by_time(self, cli, tmp_path, marker_tl):
        data = "time\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timeline import marker by-time --file {str(csv_path.resolve())} --target-ordinal 1"
        )
        assert len(marker_tl) == 5
        for i in range(5):
            assert marker_tl[i].get_data("time") == i + 1

    def test_hierarchies_by_measure(self, cli, hierarchy_tl, beat_tl, tmp_path):
        beat_tl.beat_pattern = [1]
        for i in range(6):
            beat_tl.create_beat(i)

        data = "start,end,level\n1,2,1\n2,3,1\n3,4,1\n4,5,1\n5,6,1"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import hierarchy by-measure --target-ordinal 1 --reference-tl-ordinal 2 --file {str(csv_path.resolve())}"
        )

        for i in range(5):
            assert hierarchy_tl[i].get_data("start") == i
            assert hierarchy_tl[i].get_data("end") == i + 1

    def test_hierarchies_by_time(self, cli, hierarchy_tl, tmp_path):
        data = "start,end,level\n1,2,1\n2,3,1\n3,4,1\n4,5,1\n5,6,1"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timeline import hierarchy by-time --file {str(csv_path.resolve())} --target-ordinal 1"
        )
        for i in range(5):
            assert hierarchy_tl[i].get_data("start") == i + 1
            assert hierarchy_tl[i].get_data("end") == i + 2

    def test_beats(self, cli, beat_tl, tmp_path):
        data = "time\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timeline import beat --file {str(csv_path.resolve())} --target-ordinal 1"
        )
        assert len(beat_tl) == 5
        for i in range(5):
            assert beat_tl[i].get_data("time") == i + 1

    def test_ranges_by_time(self, cli, range_tl, tmp_path):
        data = "start,end,row,label\n0,1,A,first\n1,2,B,second"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import range by-time --target-ordinal 1 "
            f"--file {str(csv_path.resolve())}"
        )

        rows_by_name = {r.name: r.id for r in range_tl.rows}
        ranges = sorted(range_tl)
        assert ranges[0].get_data("label") == "first"
        assert ranges[0].get_data("start") == 0
        assert ranges[0].get_data("end") == 1
        assert ranges[0].get_data("row_id") == rows_by_name["A"]
        assert ranges[1].get_data("label") == "second"
        assert ranges[1].get_data("start") == 1
        assert ranges[1].get_data("end") == 2
        assert ranges[1].get_data("row_id") == rows_by_name["B"]
        assert set(rows_by_name) == {"A", "B"}

    def test_ranges_by_measure(self, cli, range_tl, beat_tl, tmp_path):
        beat_tl.beat_pattern = [1]
        for i in range(1, 6):
            beat_tl.create_beat(i)
        beat_tl.recalculate_measures()

        data = "start,end,row,label\n1,2,A,first\n3,4,B,second"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import range by-measure --target-ordinal 1 "
            f"--reference-tl-ordinal 2 --file {str(csv_path.resolve())}"
        )

        rows_by_name = {r.name: r.id for r in range_tl.rows}
        ranges = sorted(range_tl)
        assert ranges[0].get_data("label") == "first"
        assert ranges[0].get_data("start") == 1
        assert ranges[0].get_data("end") == 2
        assert ranges[0].get_data("row_id") == rows_by_name["A"]
        assert ranges[1].get_data("label") == "second"
        assert ranges[1].get_data("start") == 3
        assert ranges[1].get_data("end") == 4
        assert ranges[1].get_data("row_id") == rows_by_name["B"]

    def test_ranges_replace_drops_pre_existing_rows(self, cli, range_tl, tmp_path):
        # Pre-existing row + component should be wiped on import — the
        # CLI must mirror the GUI's clear_rows() behaviour.
        old_row = range_tl.add_row(name="OldRow")
        range_tl.create_component(
            ComponentKind.RANGE, start=0, end=1, row_id=old_row.id
        )

        data = "start,end,row\n0,1,Verses\n1,2,Choruses"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import range by-time --target-ordinal 1 "
            f"--file {str(csv_path.resolve())}"
        )

        names = [r.name for r in range_tl.rows]
        assert "OldRow" not in names
        assert names == ["Verses", "Choruses"]

    def test_ranges_empty_import_keeps_default_row(self, cli, range_tl, tmp_path):
        # Every CSV row fails validation → zero imported rows. CLI must
        # still leave the timeline with >=1 row (matches GUI).
        data = "start,end,row\n0,1,\n1,2,"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f"timelines import range by-time --target-ordinal 1 "
            f"--file {str(csv_path.resolve())}"
        )

        assert len(range_tl.rows) == 1
        assert range_tl.rows[0].name

    def test_score(self, cli, tls, beat_tl, score_tl, tmp_path, tilia_errors):
        beat_tl.beat_pattern = [1]
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.create_beat(3)
        beat_tl.create_beat(4)

        # A 0th measure is necessary to import the pickup measure
        beat_tl.measure_numbers = [0, 1, 2, 3]
        beat_tl.recalculate_measures()

        cli.parse_and_run(
            f"timeline import score --file {EXAMPLE_MUSICXML_PATH} --target-ordinal 2 --reference-tl-ordinal 1"
        )

        tilia_errors.assert_no_error()
        notes = score_tl.get_components_by_attr("KIND", ComponentKind.NOTE)
        assert len(notes) == 4


class ImportTestCase:
    def __init__(self, timelines, get_timelines_params, expected_tl, expected_ref_tl):
        self.timelines = timelines
        self.get_timelines_params = get_timelines_params
        self.expected_tl = expected_tl
        self.expected_ref_tl = expected_ref_tl


class TestGetTimelinesForImport:
    @staticmethod
    def run_test_case(case: ImportTestCase, tls):
        for kind, name in case.timelines:
            with Serve(Get.FROM_USER_BEAT_PATTERN, (True, [2])):
                tls.create_timeline(kind=kind, name=name)

        tl, ref_tl = get_timelines_for_import(*case.get_timelines_params)
        if case.expected_tl is None:
            assert tl is None
        else:
            assert tl.name == case.expected_tl

        if case.expected_ref_tl is None:
            assert ref_tl is None
        else:
            assert ref_tl.name == case.expected_ref_tl

    def test_marker_by_time_by_ordinal(self, tls):
        case = ImportTestCase(
            [
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            (2, None, None, None, "by-time"),
            "marker2",
            None,
        )

        self.run_test_case(case, tls)

    def test_marker_by_time_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(None, "marker1", None, None, "by-time"),
            expected_tl="marker1",
            expected_ref_tl=None,
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_ordinal(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(2, None, 4, None, "by-measure"),
            expected_tl="marker2",
            expected_ref_tl="beat2",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(None, "marker1", None, "beat1", "by-measure"),
            expected_tl="marker1",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_name_ref_by_ordinal(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(None, "marker1", 3, None, "by-measure"),
            expected_tl="marker1",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_ordinal_ref_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(2, None, None, "beat1", "by-measure"),
            expected_tl="marker2",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_hierarchy_by_time_by_ordinal(self, tls):
        case = ImportTestCase(
            [
                (MarkerTimeline, "hierarchy1"),
                (MarkerTimeline, "hierarchy2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            (2, None, None, None, "by-time"),
            "hierarchy2",
            None,
        )

        self.run_test_case(case, tls)

    def test_hierarchy_by_time_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "hierarchy1"),
                (MarkerTimeline, "hierarchy2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(None, "hierarchy1", None, None, "by-time"),
            expected_tl="hierarchy1",
            expected_ref_tl=None,
        )

        self.run_test_case(case, tls)

    def test_beat_timeline_by_name(self, tls):
        case = ImportTestCase(
            [
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            (None, "beat1", None, None, "by-time"),
            "beat1",
            None,
        )

        self.run_test_case(case, tls)

    def test_beat_timeline_by_ordinal(self, tls):
        case = ImportTestCase(
            [
                (MarkerTimeline, "marker1"),
                (MarkerTimeline, "marker2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            (4, None, None, None, "by-time"),
            "beat2",
            None,
        )

        self.run_test_case(case, tls)

    def test_no_timeline_with_ordinal_raises_error(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "hierarchy1"),
                (MarkerTimeline, "hierarchy2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(99, None, None, None, "by-time"),
            expected_tl=None,
            expected_ref_tl=None,
        )

        with pytest.raises(ValueError):
            self.run_test_case(case, tls)

    def test_no_timeline_with_name_raises_error(self, tls):
        case = ImportTestCase(
            timelines=[
                (MarkerTimeline, "hierarchy1"),
                (MarkerTimeline, "hierarchy2"),
                (BeatTimeline, "beat1"),
                (BeatTimeline, "beat2"),
            ],
            get_timelines_params=(None, "wrong name", None, None, "by-time"),
            expected_tl=None,
            expected_ref_tl=None,
        )

        with pytest.raises(ValueError):
            self.run_test_case(case, tls)


class TestValidateTimelinesForImport:
    def test_tl_of_wrong_type_when_importing_marker_tl_raises_error(self, tls):
        tl = tls.create_timeline(HierarchyTimeline)
        success, _ = validate_timelines_for_import(tl, None, "marker", "by-time")
        assert not success

    def test_tl_of_wrong_type_when_importing_hierarchy_tl_raises_error(self, tls):
        tl = tls.create_timeline(MarkerTimeline)
        success, _ = validate_timelines_for_import(tl, None, "hierarchy", "by-time")
        assert not success

    def test_ref_tl_of_wrong_type_raises_error(self, tls):
        tl = tls.create_timeline(MarkerTimeline)
        success, _ = validate_timelines_for_import(tl, tl, "marker", "by-time")
        assert not success

    def test_no_ref_tl_when_importing_by_measure_raises_error(self, tls):
        tl = tls.create_timeline(MarkerTimeline)
        success, _ = validate_timelines_for_import(tl, None, "marker", "by-measure")
        assert not success

    def test_tl_of_wrong_type_when_importing_range_tl_raises_error(self, tls):
        tl = tls.create_timeline(MarkerTimeline)
        success, _ = validate_timelines_for_import(tl, None, "range", "by-time")
        assert not success

    def test_range_tl_passes_validation(self, tls):
        tl = tls.create_timeline(RangeTimeline)
        success, _ = validate_timelines_for_import(tl, None, "range", "by-time")
        assert success
