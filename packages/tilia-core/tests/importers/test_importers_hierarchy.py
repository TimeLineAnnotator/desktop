"""Hierarchies by time. The tests ported from TiLiA's `test_hierarchies_from_csv.py`
keep its names and CSV text; where it looks for a value in an error, these give
the whole message. TiLiA's other cases there are by measure, for
TimeLineAnnotator/project-management#273. A value that isn't one reads as the
rules read it, not as TiLiA's importer does
(TimeLineAnnotator/project-management#298)."""

import copy
import json

import pytest
from import_docs import component, document, timeline

from tilia_core import rules, tla
from tilia_core.importers import hierarchy
from tilia_core.importers._results import ImportFailed, RowProblem


@pytest.fixture
def imported(tmp_path):
    """Writes a CSV, and imports it into a new hierarchy timeline."""

    def run(data, *, media_length=60.0, time_unit="seconds"):
        path = tmp_path / "phrases.csv"
        path.write_text(data, encoding="utf-8", newline="")
        target = timeline("hierarchy")
        doc = document(
            timelines=[target], media_length=media_length, time_unit=time_unit
        )
        return hierarchy.import_by_time(doc, target.id, path), target, path

    return run


def attrs(target):
    return [component.attrs for component in target.components.values()]


def values(target, *names):
    return [tuple(a.get(name) for name in names) for a in attrs(target)]


def test_hierarchies_by_time_from_csv(imported):
    data = "start,end,level,label\n0,1,1,first\n1,2,2,second\n2,3,3,third"

    result, target, _ = imported(data)

    defaults = {"color": "", "comments": ""}
    assert attrs(target) == [
        {"start": 0, "end": 1, "level": 1, "label": "first", **defaults},
        {"start": 1, "end": 2, "level": 2, "label": "second", **defaults},
        {"start": 2, "end": 3, "level": 3, "label": "third", **defaults},
    ]
    assert result.problems == []
    assert result.rows == 3


def test_component_creation_fail_reason_gets_into_errors(imported):
    data = "start,end,level\n101,1,1"

    result, target, path = imported(data, media_length=100)

    assert result.problems == [
        RowProblem(
            path=path,
            line=2,
            column="start",
            message="Start time '101.0' is bigger than media time '100.0'",
            skipped=True,
        )
    ]
    assert target.components == {}


class TestColumnsAndCells:
    @pytest.mark.parametrize(
        "column, data",
        [
            ("start", "end,level\n1,1"),
            ("end", "start,level\n1,1"),
            ("level", "start,end\n1,2"),
        ],
    )
    def test_a_required_column_missing_fails_the_import(self, imported, column, data):
        with pytest.raises(ImportFailed) as failed:
            imported(data)

        assert failed.value.message == (
            f"Column '{column}' not found on first row of .csv file."
        )

    def test_the_optional_columns_are_stored(self, imported):
        data = (
            "start,end,level,pre_start,post_end,label,color,comments\n"
            "1,2,1,0.5,2.5,a,#ff0000,b\n"
        )

        result, target, _ = imported(data)

        assert attrs(target) == [
            {
                "start": 1,
                "end": 2,
                "level": 1,
                "pre_start": 0.5,
                "post_end": 2.5,
                "label": "a",
                "color": "#ff0000",
                "comments": "b",
            }
        ]
        assert result.problems == []

    @pytest.mark.parametrize(
        "row, column, message",
        [
            ("nonsense,1,1,,", "start", "nonsense is not a valid start."),
            ("1,nonsense,1,,", "end", "nonsense is not a valid end."),
            ("1,2,nonsense,,", "level", "nonsense is not a valid level."),
            ("1,2,1.5,,", "level", "1.5 is not a valid level."),
            ("1,2,1,nonsense,", "pre_start", "nonsense is not a valid pre start."),
            ("1,2,1,,nonsense", "post_end", "nonsense is not a valid post end."),
        ],
    )
    def test_a_value_it_cant_read_skips_the_row(self, imported, row, column, message):
        # TiLiA's importer raises on every one of these.
        data = f"start,end,level,pre_start,post_end\n{row}\n"

        result, target, path = imported(data)

        assert result.problems == [
            RowProblem(path=path, line=2, column=column, message=message, skipped=True)
        ]
        assert target.components == {}

    def test_one_problem_for_a_row_with_several_values_it_cant_read(self, imported):
        result, _, _ = imported("start,end,level\nnonsense1,nonsense2,1\n")

        assert [problem.message for problem in result.problems] == [
            "nonsense1 is not a valid start."
        ]
        assert len(result.skipped) == 1

    @pytest.mark.parametrize(
        "data, column",
        [
            ("start,end,level\n,1,1", "start"),
            ("start,end,level\n1,,1", "end"),
            ("start,end,level\n1,2,", "level"),
            ("start,end,level\n1", "end"),
            ('start,end,level\n"  ",1,1', "start"),
            ('start,end,level\n1,"  ",1', "end"),
            ('start,end,level\n1,2,"  "', "level"),
            ('start,end,level\n"\t",1,1', "start"),
            ('start,end,level\n1," ",1', "end"),
            ('start,end,level\n1,2,"\t "', "level"),
        ],
        ids=[
            "empty start",
            "empty end",
            "empty level",
            "too short",
            "start of only spaces",
            "end of only spaces",
            "level of only spaces",
            "start of a tab",
            "end of a no-break space",
            "level of a tab and a no-break space",
        ],
    )
    def test_a_row_without_a_required_value_is_skipped(self, imported, data, column):
        result, target, _ = imported(data)

        (problem,) = result.problems
        assert (problem.line, problem.column, problem.skipped) == (2, column, True)
        assert problem.message == f"an empty value is not a valid {column}."
        assert target.components == {}

    def test_a_row_too_short_for_an_optional_column_has_its_default(self, imported):
        _, target, _ = imported("start,end,level,label,comments\n1,2,1,a")

        assert attrs(target) == [
            {
                "start": 1,
                "end": 2,
                "level": 1,
                "label": "a",
                "color": "",
                "comments": "",
            }
        ]

    def test_columns_it_doesnt_know_are_ignored(self, imported):
        result, target, _ = imported("start,end,level,measure\n1,2,1,3")

        assert attrs(target) == [
            {"start": 1, "end": 2, "level": 1, "label": "", "color": "", "comments": ""}
        ]
        assert result.notes == []

    def test_each_component_has_a_new_id(self, imported):
        result, target, _ = imported("start,end,level\n1,2,1\n2,3,1\n")

        assert len(set(target.components)) == 2
        assert all(c.id == key for key, c in target.components.items())
        assert all(c.kind == "hierarchy" for c in target.components.values())
        assert result.created == list(target.components)


class TestCellsOfOnlyWhitespace:
    @pytest.mark.parametrize(
        "cell", [" ", "\t", " "], ids=["a space", "a tab", "a no-break space"]
    )
    def test_the_optional_ones_are_as_if_empty(self, imported, cell):
        result, target, _ = imported(
            "start,end,level,pre_start,post_end,label,color,comments\n"
            f'1,2,1,"{cell}","{cell}","{cell}","{cell}","{cell}"\n'
        )

        assert attrs(target) == [
            {"start": 1, "end": 2, "level": 1, "label": "", "color": "", "comments": ""}
        ]
        assert result.problems == []


class TestPreStartAndPostEnd:
    # FR-031: unset follows the start or the end when it moves, where a number
    # stays fixed.

    @pytest.mark.parametrize(
        "row",
        [
            "1,2,1,1,2",
            "1,2,1,1.0,2.00",
            "1,2,1,,",
            '1,2,1," ","   "',
            '1,2,1,"\t"," "',
        ],
        ids=["equal", "equal as numbers", "empty", "only spaces", "only whitespace"],
    )
    def test_equal_or_empty_is_stored_unset(self, imported, row):
        result, target, _ = imported(f"start,end,level,pre_start,post_end\n{row}\n")

        assert values(target, "pre_start", "post_end") == [(None, None)]
        assert values(target, "start", "end") == [(1.0, 2.0)]
        assert result.problems == []

    @pytest.mark.parametrize(
        "data",
        ["start,end,level\n1,2,1\n", "start,end,level,pre_start,post_end\n1,2,1\n"],
        ids=["no column", "too short"],
    )
    def test_missing_is_stored_unset(self, imported, data):
        _, target, _ = imported(data)

        assert values(target, "pre_start", "post_end") == [(None, None)]

    def test_each_is_compared_on_its_own(self, imported):
        data = "start,end,level,pre_start,post_end\n1,2,1,1,3\n3,4,1,2,4\n"

        _, target, _ = imported(data)

        assert values(target, "pre_start", "post_end") == [(None, 3.0), (2.0, None)]

    def test_at_zero_equal_to_a_start_of_zero_is_unset(self, imported):
        # 0 is a number like any other, not the same as no value.
        _, target, _ = imported("start,end,level,pre_start\n0,2,1,0\n")

        assert values(target, "pre_start") == [(None,)]

    def test_unset_isnt_written_and_reads_back_unset(self, tmp_path):
        path = tmp_path / "phrases.csv"
        path.write_text(
            "start,end,level,pre_start,post_end\n1,2,1,1,2\n2,3,1,1.5,3.5\n",
            encoding="utf-8",
        )
        target = timeline("hierarchy", attrs={"height": 120})
        doc = document(timelines=[target])

        hierarchy.import_by_time(doc, target.id, path)
        written = tla.canonical_bytes(doc)

        stored = list(
            json.loads(written)["timelines"][target.id]["components"].values()
        )
        assert "pre_start" not in stored[0] and "post_end" not in stored[0]
        assert (stored[1]["pre_start"], stored[1]["post_end"]) == (1.5, 3.5)
        assert tla.loads(written).timelines[target.id].components == target.components


class TestTheRules:
    @pytest.mark.parametrize(
        "row, column, message",
        [
            ("nan,2,1,,", "start", "nan is not a valid start."),
            ("1,inf,1,,", "end", "inf is not a valid end."),
            ("1,2,1,nan,", "pre_start", "nan is not a valid pre start."),
            ("1,2,1,,inf", "post_end", "inf is not a valid post end."),
            (
                "61,62,1,,",
                "start",
                "Start time '61.0' is bigger than media time '60.0'",
            ),
            ("1,61,1,,", "end", "End time '61.0' is bigger than media time '60.0'"),
            ("-1,2,1,,", "start", "Start time can't be negative. Got '-1.0'"),
            (
                "2,1,1,,",
                "end",
                "End time '1.0' should be bigger than start time '2.0'",
            ),
            (
                "2,2,1,,",
                "end",
                "End time '2.0' should be bigger than start time '2.0'",
            ),
            ("1,2,0,,", "level", "Level can't be below 1. Got '0'"),
            ("1,2,-1,,", "level", "Level can't be below 1. Got '-1'"),
            ("1,2,1,-0.5,", "pre_start", "pre_start is outside media bounds."),
            ("1,2,1,1.5,", "pre_start", "pre_start can't be after start time."),
            ("1,2,1,,61", "post_end", "post_end is outside media bounds."),
            ("1,2,1,,1.5", "post_end", "post_end can't be before end time."),
        ],
    )
    def test_a_row_the_rules_refuse_is_skipped(self, imported, row, column, message):
        data = f"start,end,level,pre_start,post_end\n{row}\n10,11,1,,\n"

        result, target, path = imported(data)

        assert result.problems == [
            RowProblem(path=path, line=2, column=column, message=message, skipped=True)
        ]
        assert values(target, "start") == [(10.0,)]

    def test_the_later_of_two_at_the_same_place_is_skipped(self, imported):
        # Start, end and level together: there is no one column at fault.
        data = "start,end,level,label\n1,2,1,first\n1,2,1,second\n"

        result, target, path = imported(data)

        assert result.problems == [
            RowProblem(
                path=path,
                line=3,
                column=None,
                message="There is already a hierarchy component at the selected position.",
                skipped=True,
            )
        ]
        assert values(target, "label") == [("first",)]

    @pytest.mark.parametrize(
        "row",
        ["5,15,2", "0,5,1"],
        ids=["crossing", "the one inside at the same level"],
    )
    def test_the_later_of_two_that_dont_nest_is_skipped(self, imported, row):
        data = f"start,end,level,label\n0,10,1,first\n{row},second\n"

        result, target, path = imported(data)

        assert result.problems == [
            RowProblem(
                path=path,
                line=3,
                column=None,
                message="Component would overlap with existing component.",
                skipped=True,
            )
        ]
        assert values(target, "label") == [("first",)]

    def test_a_row_skipped_isnt_compared_with_those_after_it(self, imported):
        # The second crosses the first and is skipped; the third crosses only it.
        data = "start,end,level\n0,10,1\n5,15,1\n12,20,1\n"

        result, target, _ = imported(data)

        assert [problem.line for problem in result.problems] == [3]
        assert values(target, "start") == [(0.0,), (12.0,)]

    def test_nesting_ones_are_kept(self, imported):
        data = "start,end,level\n0,10,2\n0,5,1\n5,10,1\n"

        result, target, _ = imported(data)

        assert result.problems == []
        assert len(target.components) == 3

    def test_the_timeline_is_checked_once(self, imported, monkeypatch):
        calls = []
        check_timeline = rules.check_timeline

        def counted(media_length, components, **kwargs):
            calls.append((media_length, list(components), kwargs))
            return check_timeline(media_length, components, **kwargs)

        monkeypatch.setattr(rules, "check_timeline", counted)
        monkeypatch.setattr(
            rules, "hierarchy", lambda *_: pytest.fail("checked row by row")
        )

        imported("start,end,level\n1,2,1\nabc,3,1\n2,3,1\n", media_length=10.0)

        ((media_length, components, kwargs),) = calls
        assert media_length == 10.0
        assert [c.attrs["start"] for c in components] == [1.0, 2.0]
        assert kwargs == {"skip_broken": True}


class TestAColorThatIsntOne:
    def test_it_keeps_the_row_with_the_default_color_and_a_note(self, imported):
        # contracts/rules.md, Decisions 4.
        result, target, path = imported("start,end,level,color\n1,2,1,notacolor\n")

        assert result.problems == [
            RowProblem(
                path=path,
                line=2,
                column="color",
                message="notacolor is not a valid color: the default color is used.",
                skipped=False,
            )
        ]
        assert result.skipped == []
        assert result.created == list(target.components)
        assert values(target, "color") == [("",)]

    def test_a_row_that_breaks_another_rule_is_skipped_without_the_note(self, imported):
        # It wasn't imported, so no color is used; the color doesn't hide the rule.
        result, target, _ = imported("start,end,level,color\n1,2,0,notacolor\n")

        (problem,) = result.problems
        assert problem.skipped
        assert problem.message == "Level can't be below 1. Got '0'"
        assert target.components == {}

    def test_it_counts_as_kept_for_the_rows_after_it(self, imported):
        data = "start,end,level,color,label\n0,10,1,notacolor,a\n5,15,1,,b\n"

        result, target, _ = imported(data)

        assert [(p.line, p.skipped) for p in result.problems] == [(2, False), (3, True)]
        assert values(target, "label") == [("a",)]

    @pytest.mark.parametrize("color", ["", "#f00", "red", "transparent"])
    def test_a_color_that_is_one_is_stored(self, imported, color):
        result, target, _ = imported(f"start,end,level,color\n1,2,1,{color}\n")

        assert result.problems == []
        assert values(target, "color") == [(color,)]


class TestTheFormalColumns:
    # FR-039.
    NOTE = "formal_type and formal_function are no longer stored"

    @pytest.mark.parametrize(
        "columns, cells",
        [
            ("formal_type,formal_function", "sonata,opening"),
            ("formal_type", "sonata"),
            ("formal_function", "opening"),
        ],
    )
    def test_one_note_for_the_import_and_nothing_stored(self, imported, columns, cells):
        data = f"start,end,level,{columns}\n1,2,1,{cells}\n2,3,1,{cells}\n"

        result, target, _ = imported(data)

        assert result.notes == [self.NOTE]
        assert result.problems == []
        assert all(
            "formal_type" not in a and "formal_function" not in a for a in attrs(target)
        )

    def test_no_note_without_them(self, imported):
        result, _, _ = imported("start,end,level\n1,2,1\n")

        assert result.notes == []

    def test_the_note_doesnt_depend_on_the_rows(self, imported):
        result, _, _ = imported("start,end,level,formal_type\n")

        assert result.notes == [self.NOTE]


class TestWhatItReports:
    def test_a_rows_line_counts_a_quoted_fields_line_breaks(self, imported):
        data = 'start,end,level,label\n1,2,1,"two\nlines"\n\nabc,3,1,x\n50,99,1,y\n'

        result, _, _ = imported(data)

        assert [problem.line for problem in result.problems] == [5, 6]

    def test_problems_are_in_row_order(self, imported):
        # One the rules refuse, one it can't read, a note, and one the rules refuse.
        data = "start,end,level,color\n1,2,0,\nabc,2,1,\n3,4,1,notacolor\n5,4,1,\n"

        result, target, _ = imported(data)

        assert [(p.line, p.skipped) for p in result.problems] == [
            (2, True),
            (3, True),
            (4, False),
            (5, True),
        ]
        assert len(result.skipped) == 3
        assert result.rows == 4
        assert result.created == list(target.components)
        assert len(result.created) == 1


class TestWhatItChanges:
    def test_it_replaces_the_components_the_timeline_had(self, tmp_path):
        # US3 scenario 6, FR-032: and they don't count as others.
        path = tmp_path / "phrases.csv"
        path.write_text("start,end,level\n5,15,1\n", encoding="utf-8")
        old = component("hierarchy", start=0.0, end=10.0, level=1)
        target = timeline("hierarchy", components=[old])
        doc = document(timelines=[target])

        result = hierarchy.import_by_time(doc, target.id, path)

        assert result.problems == []
        assert values(target, "start") == [(5.0,)]
        assert old.id not in target.components

    def test_importing_twice_gives_the_same_components_with_new_ids(self, tmp_path):
        path = tmp_path / "phrases.csv"
        path.write_text("start,end,level,label\n1,2,1,a\n2,3,1,b\n", encoding="utf-8")
        target = timeline("hierarchy")
        doc = document(timelines=[target])

        first = hierarchy.import_by_time(doc, target.id, path)
        before = attrs(target)
        second = hierarchy.import_by_time(doc, target.id, path)

        assert second.problems == []
        assert attrs(target) == before
        assert list(target.components) == second.created
        assert not set(first.created) & set(second.created)

    @pytest.mark.parametrize(
        "content",
        [b"start,end\n1,2\n", b"", "start,end,level,label\n1,2,1,é\n".encode("cp1252")],
        ids=["no level column", "empty", "not UTF-8"],
    )
    def test_an_import_that_fails_changes_nothing(self, tmp_path, content):
        # FR-024.
        path = tmp_path / "phrases.csv"
        path.write_bytes(content)
        old = component("hierarchy", start=0.0, end=10.0, level=1)
        target = timeline("hierarchy", components=[old])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed):
            hierarchy.import_by_time(doc, target.id, path)

        assert doc == before

    def test_the_path_can_be_text(self, tmp_path):
        path = tmp_path / "phrases.csv"
        path.write_text("start,end,level\nabc,2,1\n", encoding="utf-8")
        target = timeline("hierarchy")

        result = hierarchy.import_by_time(
            document(timelines=[target]), target.id, str(path)
        )

        assert result.problems[0].path == path


class TestTimeUnits:
    def test_a_quarters_document_reads_times_as_they_are(self, imported):
        # US3 scenario 7, FR-033.
        result, target, _ = imported(
            "start,end,level\n0,2.5,1\n2.5,16,1\n16,17,1\n",
            media_length=16,
            time_unit="quarters",
        )

        assert values(target, "start", "end") == [(0.0, 2.5), (2.5, 16.0)]
        assert [problem.line for problem in result.problems] == [4]


class TestAnUnknownMediaLength:
    def test_it_fails_and_changes_nothing(self, tmp_path):
        # TimeLineAnnotator/project-management#418: as for markers.
        path = tmp_path / "phrases.csv"
        path.write_text("start,end,level\n1,2,1\n", encoding="utf-8")
        old = component("hierarchy", start=0.0, end=10.0, level=1)
        target = timeline("hierarchy", components=[old])
        doc = document(timelines=[target], media_length=None)
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed) as failed:
            hierarchy.import_by_time(doc, target.id, path)

        assert failed.value.message == (
            "No media loaded and no duration set. Load a media file with"
            " 'load-media' or set a duration with 'metadata set-media-length'."
        )
        assert doc == before
