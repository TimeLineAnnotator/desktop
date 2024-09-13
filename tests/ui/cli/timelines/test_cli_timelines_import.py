import pytest

from tests.mock import Serve

from tilia.exceptions import WrongTimelineForImport
from tilia.requests import Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction
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
    def test_markers_by_measure(self, cli, marker_tl, beat_tl, tmp_path, tilia_state, actions):
        beat_tl.beat_pattern = [1]
        for i in range(5):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        data = "measure\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(f'timelines import csv marker by-measure --target-ordinal 1 --reference-tl-ordinal 2 --file {str(csv_path.resolve())}')
        for i in range(5):
            assert marker_tl[i].get_data('time') == i

    def test_markers_by_time(self, cli, tmp_path, marker_tl):
        data = "time\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(f'timeline import csv marker by-time --file {str(csv_path.resolve())} --target-ordinal 1')
        assert len(marker_tl) == 5
        for i in range(5):
            assert marker_tl[i].get_data('time') == i + 1

    def test_hierarchies_by_measure(self, cli, hierarchy_tl, beat_tl, tmp_path, tilia_state, actions):
        beat_tl.beat_pattern = [1]
        for i in range(6):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        data = "start,end,level\n1,2,1\n2,3,1\n3,4,1\n4,5,1\n5,6,1"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(
            f'timelines import csv hierarchy by-measure --target-ordinal 1 --reference-tl-ordinal 2 --file {str(csv_path.resolve())}')

        for i in range(5):
            assert hierarchy_tl[i].get_data('start') == i
            assert hierarchy_tl[i].get_data('end') == i + 1

    def test_hierarchies_by_time(self, cli, hierarchy_tl, tmp_path, tilia_state, actions):
        data = "start,end,level\n1,2,1\n2,3,1\n3,4,1\n4,5,1\n5,6,1"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(f'timeline import csv hierarchy by-time --file {str(csv_path.resolve())} --target-ordinal 1')
        for i in range(5):
            assert hierarchy_tl[i].get_data('start') == i + 1
            assert hierarchy_tl[i].get_data('end') == i + 2

    def test_beats(self, cli, beat_tl, tmp_path, tilia_state, actions):
        data = "time\n1\n2\n3\n4\n5"
        csv_path = tmp_csv(tmp_path, data)

        cli.parse_and_run(f'timeline import csv beat --file {str(csv_path.resolve())} --target-ordinal 1')
        assert len(beat_tl) == 5
        for i in range(5):
            assert beat_tl[i].get_data('time') == i + 1


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
            with Serve(Get.FROM_USER_BEAT_PATTERN, [2]):
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
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            (2, None, None, None, "by-time"),
            "marker2",
            None,
        )

        self.run_test_case(case, tls)

    def test_marker_by_time_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(None, "marker1", None, None, "by-time"),
            expected_tl="marker1",
            expected_ref_tl=None,
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_ordinal(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(2, None, 4, None, "by-measure"),
            expected_tl="marker2",
            expected_ref_tl="beat2",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(None, "marker1", None, "beat1", "by-measure"),
            expected_tl="marker1",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_name_ref_by_ordinal(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(None, "marker1", 3, None, "by-measure"),
            expected_tl="marker1",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_marker_by_measure_by_ordinal_ref_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(2, None, None, "beat1", "by-measure"),
            expected_tl="marker2",
            expected_ref_tl="beat1",
        )

        self.run_test_case(case, tls)

    def test_hierarchy_by_time_by_ordinal(self, tls):
        case = ImportTestCase(
            [
                (TimelineKind.MARKER_TIMELINE, "hierarchy1"),
                (TimelineKind.MARKER_TIMELINE, "hierarchy2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            (2, None, None, None, "by-time"),
            "hierarchy2",
            None,
        )

        self.run_test_case(case, tls)

    def test_hierarchy_by_time_by_name(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "hierarchy1"),
                (TimelineKind.MARKER_TIMELINE, "hierarchy2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(None, "hierarchy1", None, None, "by-time"),
            expected_tl="hierarchy1",
            expected_ref_tl=None,
        )

        self.run_test_case(case, tls)

    def test_beat_timeline_by_name(self, tls):
        case = ImportTestCase(
            [
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            (None, "beat1", None, None, "by-time"),
            "beat1",
            None,
        )

        self.run_test_case(case, tls)

    def test_beat_timeline_by_ordinal(self, tls):
        case = ImportTestCase(
            [
                (TimelineKind.MARKER_TIMELINE, "marker1"),
                (TimelineKind.MARKER_TIMELINE, "marker2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            (4, None, None, None, "by-time"),
            "beat2",
            None,
        )

        self.run_test_case(case, tls)

    def test_no_timeline_with_ordinal_raises_error(self, tls):
        case = ImportTestCase(
            timelines=[
                (TimelineKind.MARKER_TIMELINE, "hierarchy1"),
                (TimelineKind.MARKER_TIMELINE, "hierarchy2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
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
                (TimelineKind.MARKER_TIMELINE, "hierarchy1"),
                (TimelineKind.MARKER_TIMELINE, "hierarchy2"),
                (TimelineKind.BEAT_TIMELINE, "beat1"),
                (TimelineKind.BEAT_TIMELINE, "beat2"),
            ],
            get_timelines_params=(None, "wrong name", None, None, "by-time"),
            expected_tl=None,
            expected_ref_tl=None,
        )

        with pytest.raises(ValueError):
            self.run_test_case(case, tls)


class TestValidateTimelinesForImport:
    def test_tl_of_wrong_type_when_importing_marker_tl_raises_error(self, tls):
        tl = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        with pytest.raises(WrongTimelineForImport):
            validate_timelines_for_import(tl, None, "marker", "by-time")

    def test_tl_of_wrong_type_when_importing_hierarchy_tl_raises_error(self, tls):
        tl = tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        with pytest.raises(WrongTimelineForImport):
            validate_timelines_for_import(tl, None, "hierarchy", "by-time")

    def test_ref_tl_of_wrong_type_raises_error(self, tls):
        tl = tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        with pytest.raises(WrongTimelineForImport):
            validate_timelines_for_import(tl, tl, "marker", "by-time")

    def test_no_ref_tl_when_importing_by_measure_raises_error(self, tls):
        tl = tls.create_timeline(TimelineKind.MARKER_TIMELINE)
        with pytest.raises(ValueError):
            validate_timelines_for_import(tl, None, "marker", "by-measure")
