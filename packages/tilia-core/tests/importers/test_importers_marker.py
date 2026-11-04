"""Markers by time. The tests ported from TiLiA's `test_markers_from_csv.py` keep
its names and CSV text; where it looks for a value in an error, these give the
whole message. A time that isn't one reads as the rules read it, not as TiLiA's
importer does (TimeLineAnnotator/project-management#298)."""

import copy
import json

import pytest
from import_docs import component, document, timeline

from tilia_core import rules, tla
from tilia_core.importers import marker
from tilia_core.importers._results import ImportFailed, RowProblem


@pytest.fixture
def imported(tmp_path):
    """Writes a CSV, and imports it into a new marker timeline."""

    def run(data, *, media_length=60.0, time_unit="seconds"):
        path = tmp_path / "markers.csv"
        path.write_text(data, encoding="utf-8", newline="")
        target = timeline("marker")
        doc = document(
            timelines=[target], media_length=media_length, time_unit=time_unit
        )
        return marker.import_by_time(doc, target.id, path), target, path

    return run


def attrs(target):
    return [component.attrs for component in target.components.values()]


def test_markers_by_time_from_csv(imported):
    data = "time,label,comments\n1,first,a\n5,second,b\n10,third,c"

    result, target, _ = imported(data)

    assert attrs(target) == [
        {"time": 1, "label": "first", "comments": "a", "color": None},
        {"time": 5, "label": "second", "comments": "b", "color": None},
        {"time": 10, "label": "third", "comments": "c", "color": None},
    ]
    assert result.problems == []
    assert result.rows == 3


def test_markers_by_time_from_csv_fails_if_no_time_column(imported):
    data = "label,comments\nfirst,a\nsecond,b\nthird,c"

    with pytest.raises(ImportFailed) as failed:
        imported(data)

    assert failed.value.message == "Column 'time' not found on first row of .csv file."
    assert str(failed.value) == (
        "markers.csv: Column 'time' not found on first row of .csv file."
    )


def test_markers_by_time_from_csv_outputs_error_if_bad_time_value(imported):
    data = "time\nnonsense"

    result, target, path = imported(data)

    assert result.problems == [
        RowProblem(
            path=path,
            line=2,
            column="time",
            message="nonsense is not a valid time.",
            skipped=True,
        )
    ]
    assert target.components == {}


def test_markers_by_time_from_csv_outputs_error_if_time_out_of_bound(imported):
    data = "time\n999"

    result, target, path = imported(data, media_length=100)

    assert result.problems == [
        RowProblem(
            path=path,
            line=2,
            column="time",
            message="Time '16:39.0' is bigger than media time '01:40.0'",
            skipped=True,
        )
    ]
    assert target.components == {}


def test_component_creation_fail_reason_gets_into_errors(imported):
    data = "time\n101"

    result, _, _ = imported(data, media_length=100)

    assert [problem.message for problem in result.problems] == [
        "Time '01:41.0' is bigger than media time '01:40.0'"
    ]


class TestColumnsAndCells:
    def test_label_and_comments_are_optional(self, imported):
        _, target, _ = imported("time\n1")

        assert attrs(target) == [
            {"time": 1, "label": "", "comments": "", "color": None}
        ]

    def test_a_row_too_short_for_an_optional_column_has_its_default(self, imported):
        _, target, _ = imported("time,label,comments\n1,first")

        assert attrs(target) == [
            {"time": 1, "label": "first", "comments": "", "color": None}
        ]

    @pytest.mark.parametrize(
        "data",
        ["time,label\n,first", "label,time\nfirst", 'time,label\n"   ",first'],
        ids=["empty", "too short", "only spaces"],
    )
    def test_a_row_without_a_time_is_skipped(self, imported, data):
        result, target, _ = imported(data)

        (problem,) = result.problems
        assert (problem.line, problem.column, problem.skipped) == (2, "time", True)
        assert problem.message == "an empty value is not a valid time."
        assert target.components == {}

    def test_a_label_or_a_comment_of_only_spaces_is_empty(self, imported):
        result, target, _ = imported("time,label,comments\n1,  ,   \n")

        assert attrs(target) == [
            {"time": 1, "label": "", "comments": "", "color": None}
        ]
        assert result.problems == []

    def test_columns_it_doesnt_know_are_ignored(self, imported):
        # A marker's color too: TiLiA's importer doesn't read one.
        _, target, _ = imported("time,color,measure\n1,#ff0000,3")

        assert attrs(target) == [
            {"time": 1, "label": "", "comments": "", "color": None}
        ]

    def test_times_are_read_as_tilia_reads_them(self, imported):
        # float's own forms, spaces around them included.
        _, target, _ = imported('time\n" 1"\n1e1\n2.50\n')

        assert [a["time"] for a in attrs(target)] == [1.0, 10.0, 2.5]

    def test_each_component_has_a_new_id(self, imported):
        result, target, _ = imported("time\n1\n2")

        assert len(set(target.components)) == 2
        assert all(c.id == key for key, c in target.components.items())
        assert all(c.kind == "marker" for c in target.components.values())
        assert result.created == list(target.components)


class TestTheRules:
    @pytest.mark.parametrize(
        "value, message",
        [
            ("nan", "nan is not a valid time."),
            ("inf", "inf is not a valid time."),
            ("-1", "Time can't be negative. Got '-00:01.0'"),
            ("60.5", "Time '01:00.5' is bigger than media time '01:00.0'"),
        ],
    )
    def test_a_time_the_rules_refuse_is_skipped(self, imported, value, message):
        result, target, path = imported(f"time\n1\n{value}\n2\n")

        assert result.problems == [
            RowProblem(path=path, line=3, column="time", message=message, skipped=True)
        ]
        assert [a["time"] for a in attrs(target)] == [1.0, 2.0]

    def test_a_time_at_the_media_length_is_kept(self, imported):
        result, target, _ = imported("time\n60")

        assert result.problems == []
        assert [a["time"] for a in attrs(target)] == [60.0]

    def test_the_later_of_two_at_the_same_time_is_skipped(self, imported):
        result, target, path = imported("time,label\n1,first\n1,second\n")

        assert result.problems == [
            RowProblem(
                path=path,
                line=3,
                column="time",
                message="There is already a marker component at the selected position.",
                skipped=True,
            )
        ]
        assert [a["label"] for a in attrs(target)] == ["first"]

    def test_a_row_skipped_isnt_compared_with_those_after_it(self, imported):
        # The first is beyond the media, so the third is the first at its time.
        _, target, _ = imported(
            "time,label\n70,beyond\n1,first\n1,second\n", media_length=60.0
        )

        assert [a["label"] for a in attrs(target)] == ["first"]

    def test_the_timeline_is_checked_once_with_the_kept_ones_in_the_csvs_order(
        self, imported, monkeypatch
    ):
        calls = []
        check_timeline = rules.check_timeline

        def counted(media_length, components, **kwargs):
            calls.append((media_length, list(components), kwargs))
            return check_timeline(media_length, components, **kwargs)

        monkeypatch.setattr(rules, "check_timeline", counted)
        monkeypatch.setattr(
            rules, "marker", lambda *_: pytest.fail("checked row by row")
        )

        result, _, _ = imported("time\n3\nabc\n1\n", media_length=10.0)

        ((media_length, components, kwargs),) = calls
        assert media_length == 10.0
        assert [c.attrs["time"] for c in components] == [3.0, 1.0]
        assert kwargs == {"skip_broken": True}
        assert result.rows == 3


class TestWhatItReports:
    def test_a_rows_line_counts_a_quoted_fields_line_breaks(self, imported):
        data = 'time,label\n1,"two\nlines"\n\nabc,x\n99,y\n'

        result, _, _ = imported(data)

        assert [problem.line for problem in result.problems] == [5, 6]

    def test_problems_are_in_row_order(self, imported):
        # One the rules refuse before one it can't read.
        result, _, _ = imported("time\n99\nabc\n98\nxyz\n")

        assert [problem.line for problem in result.problems] == [2, 3, 4, 5]

    def test_created_and_skipped(self, imported):
        result, target, _ = imported("time\n1\nabc\n2\n99\n")

        assert result.created == list(target.components)
        assert len(result.created) == 2
        assert result.rows == 4
        assert result.skipped == result.problems
        assert len(result.skipped) == 2
        assert result.notes == []


class TestWhatItChanges:
    def test_it_replaces_the_components_the_timeline_had(self, tmp_path):
        # US3 scenario 6, FR-032.
        path = tmp_path / "markers.csv"
        path.write_text("time\n5\n", encoding="utf-8")
        old = component("marker", time=1.0, label="", comments="", color=None)
        target = timeline("marker", components=[old])
        doc = document(timelines=[target])

        marker.import_by_time(doc, target.id, path)

        assert [a["time"] for a in attrs(target)] == [5.0]
        assert old.id not in target.components

    def test_a_component_of_a_kind_the_core_doesnt_know_stays(self, tmp_path):
        # FR-032, and WP3's FR-015.
        path = tmp_path / "markers.csv"
        path.write_text("time,label\n5,new\n", encoding="utf-8")
        old = component("marker", time=1.0, label="", comments="", color=None)
        unknown = tla.Component(
            id=tla.new_id(),
            kind=tla.UnknownKind("LYRIC"),
            extra={"time": 1.0, "text": "la"},
        )
        target = timeline("marker", attrs={"height": 30}, components=[old, unknown])
        written = tla.canonical_bytes(document(timelines=[target]))
        read = tla.loads(written)

        result = marker.import_by_time(read, target.id, path)

        components = read.timelines[target.id].components
        assert result.problems == []
        assert set(components) == {unknown.id, *result.created}
        assert components[unknown.id] == unknown
        again = json.loads(tla.canonical_bytes(read))["timelines"][target.id]
        assert (
            again["components"][unknown.id]
            == json.loads(written)["timelines"][target.id]["components"][unknown.id]
        )

    def test_importing_twice_gives_the_same_components_with_new_ids(self, tmp_path):
        # FR-032; the second time, the first's components don't count as others.
        path = tmp_path / "markers.csv"
        path.write_text("time,label\n1,a\n2,b\n", encoding="utf-8")
        target = timeline("marker")
        doc = document(timelines=[target])

        first = marker.import_by_time(doc, target.id, path)
        before = attrs(target)
        second = marker.import_by_time(doc, target.id, path)

        assert second.problems == []
        assert attrs(target) == before
        assert list(target.components) == second.created
        assert not set(first.created) & set(second.created)

    @pytest.mark.parametrize(
        "content",
        [b"label\nfirst\n", b"", "time\né\n".encode("cp1252")],
        ids=["no time column", "empty", "not UTF-8"],
    )
    def test_an_import_that_fails_changes_nothing(self, tmp_path, content):
        # FR-024.
        path = tmp_path / "markers.csv"
        path.write_bytes(content)
        old = component("marker", time=1.0, label="", comments="", color=None)
        target = timeline("marker", components=[old])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed):
            marker.import_by_time(doc, target.id, path)

        assert doc == before

    def test_a_file_that_cant_be_opened_changes_nothing(self, tmp_path):
        target = timeline("marker")
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(OSError):
            marker.import_by_time(doc, target.id, tmp_path / "none.csv")

        assert doc == before

    def test_the_path_can_be_text(self, tmp_path):
        path = tmp_path / "markers.csv"
        path.write_text("time\nabc\n", encoding="utf-8")
        target = timeline("marker")

        result = marker.import_by_time(
            document(timelines=[target]), target.id, str(path)
        )

        assert result.problems[0].path == path


class TestTimeUnits:
    def test_a_quarters_document_reads_times_as_they_are(self, imported):
        # US3 scenario 7, FR-033: nothing converts them, and the length is in
        # quarters too.
        result, target, _ = imported(
            "time,label\n2.5,a\n16,b\n16.5,c\n", media_length=16, time_unit="quarters"
        )

        assert [a["time"] for a in attrs(target)] == [2.5, 16.0]
        assert [problem.line for problem in result.problems] == [4]


class TestAnUnknownMediaLength:
    def test_it_fails_and_changes_nothing(self, tmp_path):
        # TimeLineAnnotator/project-management#418: a file can hold a timeline and
        # no length, which only a new timeline refuses.
        path = tmp_path / "markers.csv"
        path.write_text("time\n1\n", encoding="utf-8")
        old = component("marker", time=1.0, label="", comments="", color=None)
        target = timeline("marker", components=[old])
        doc = document(timelines=[target], media_length=None)
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed) as failed:
            marker.import_by_time(doc, target.id, path)

        assert failed.value.message == (
            "No media loaded and no duration set. Load a media file with"
            " 'load-media' or set a duration with 'metadata set-media-length'."
        )
        assert doc == before


def test_what_it_imports_reads_back_as_it_is(tmp_path):
    path = tmp_path / "markers.csv"
    path.write_text("time,label\n1,first\n2,\n", encoding="utf-8")
    target = timeline("marker", attrs={"height": 30})
    doc = document(timelines=[target])

    marker.import_by_time(doc, target.id, path)

    read = tla.loads(tla.canonical_bytes(doc))
    assert read.timelines[target.id].components == target.components
