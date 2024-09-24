from pathlib import Path
from unittest.mock import patch
import argparse
import pytest

from tests.mock import Serve
from tilia.exceptions import WrongTimelineForImport
from tilia.requests import Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.imp import (
    import_timeline,
    get_timelines_for_import,
    validate_timelines_for_import,
)

GET_TIMELINES_FOR_IMPORT_PATH = "tilia.ui.cli.timelines.imp.get_timelines_for_import"
CSV_PARSER_PATH = "tilia.parsers.csv"


class DummyMarkerTl:
    KIND = TimelineKind.MARKER_TIMELINE

    def clear(self):
        pass


class DummyHierarchyTl:
    KIND = TimelineKind.HIERARCHY_TIMELINE

    def clear(self):
        pass


class DummyBeatTl:
    KIND = TimelineKind.BEAT_TIMELINE

    def clear(self):
        pass


class TestImportTimeline:
    def test_markers_by_measure(self):
        namespace = argparse.Namespace(
            target_ordinal=1,
            target_name="target_name",
            reference_tl_ordinal=2,
            reference_tl_name="ref_name",
            measure_or_time="by-measure",
            tl_kind="marker",
            file="test.csv",
        )

        tl, ref_tl = DummyMarkerTl(), DummyBeatTl()

        with (
            patch(
                GET_TIMELINES_FOR_IMPORT_PATH,
                return_value=(tl, ref_tl),
            ) as get_tls_mock,
            patch(
                CSV_PARSER_PATH + ".markers_by_measure_from_csv",
                return_value="csv_data",
            ) as parse_mock,
        ):
            import_timeline(namespace)
            get_tls_mock.assert_called_with(
                1, "target_name", 2, "ref_name", "by-measure"
            )
            parse_mock.assert_called_once_with(tl, ref_tl, Path("test.csv"))

    def test_markers_by_time(self):
        namespace = argparse.Namespace(
            target_ordinal=1,
            target_name="target_name",
            reference_tl_ordinal=2,
            reference_tl_name="ref_name",
            measure_or_time="by-time",
            tl_kind="marker",
            file="test.csv",
        )

        tl, ref_tl = DummyMarkerTl(), DummyBeatTl()

        with (
            patch(
                GET_TIMELINES_FOR_IMPORT_PATH,
                return_value=(tl, ref_tl),
            ) as get_tls_mock,
            patch(
                CSV_PARSER_PATH + ".markers_by_time_from_csv", return_value="csv_data"
            ) as parse_mock,
        ):
            import_timeline(namespace)
            get_tls_mock.assert_called_with(1, "target_name", 2, "ref_name", "by-time")
            parse_mock.assert_called_once_with(tl, Path("test.csv"))

    def test_hierarchies_by_measure(self):
        namespace = argparse.Namespace(
            target_ordinal=1,
            target_name="target_name",
            reference_tl_ordinal=2,
            reference_tl_name="ref_name",
            measure_or_time="by-measure",
            tl_kind="hierarchy",
            file="test.csv",
        )

        tl, ref_tl = DummyHierarchyTl(), DummyBeatTl()

        with (
            patch(
                GET_TIMELINES_FOR_IMPORT_PATH,
                return_value=(tl, ref_tl),
            ) as get_tls_mock,
            patch(
                CSV_PARSER_PATH + ".hierarchies_by_measure_from_csv",
                return_value="csv_data",
            ) as parse_mock,
        ):
            import_timeline(namespace)
            get_tls_mock.assert_called_with(
                1, "target_name", 2, "ref_name", "by-measure"
            )
            parse_mock.assert_called_once_with(tl, ref_tl, Path("test.csv"))

    def test_hierarchies_by_time(self):
        namespace = argparse.Namespace(
            target_ordinal=1,
            target_name="target_name",
            reference_tl_ordinal=2,
            reference_tl_name="ref_name",
            measure_or_time="by-time",
            tl_kind="hierarchy",
            file="test.csv",
        )

        tl, ref_tl = DummyHierarchyTl(), DummyBeatTl()

        with (
            patch(
                GET_TIMELINES_FOR_IMPORT_PATH,
                return_value=(tl, ref_tl),
            ) as get_tls_mock,
            patch(
                CSV_PARSER_PATH + ".hierarchies_by_time_from_csv",
                return_value="csv_data",
            ) as parse_mock,
        ):
            import_timeline(namespace)
            get_tls_mock.assert_called_with(1, "target_name", 2, "ref_name", "by-time")
            parse_mock.assert_called_once_with(tl, Path("test.csv"))

    def test_beats(self):
        namespace = argparse.Namespace(
            target_ordinal=1,
            target_name="target_name",
            reference_tl_ordinal=2,
            reference_tl_name="ref_name",
            tl_kind="beat",
            file="test.csv",
        )

        tl, ref_tl = DummyBeatTl(), None

        with (
            patch(
                GET_TIMELINES_FOR_IMPORT_PATH,
                return_value=(tl, ref_tl),
            ) as get_tls_mock,
            patch(
                CSV_PARSER_PATH + ".beats_from_csv",
                return_value="csv_data",
            ) as parse_mock,
        ):
            import_timeline(namespace)
            get_tls_mock.assert_called_with(1, "target_name", 2, "ref_name", None)
            parse_mock.assert_called_once_with(tl, Path("test.csv"))


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
