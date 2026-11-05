import json
import re

import pytest
from import_docs import component, document, timeline

from tilia_core import rules, tla
from tilia_core.importers._results import ImportFailed
from tilia_core.importers.range import import_by_time


def old_row(name="Old", row_id="Old123"):
    return {"id": row_id, "name": name, "color": None, "height": None}


@pytest.fixture
def csv_file(tmp_path):
    def write(text, encoding="utf-8"):
        path = tmp_path / "ranges.csv"
        path.write_text(text, encoding=encoding, newline="")
        return path

    return write


@pytest.fixture
def target():
    return timeline("range", attrs={"rows": [old_row()]})


@pytest.fixture
def do_import(csv_file, target):
    """Imports a CSV's text into `target`, in a document with 60 s of media."""

    def run(text, **document_args):
        doc = document(timelines=[target], **document_args)
        return import_by_time(doc, target.id, csv_file(text))

    return run


def ranges_of(target):
    return list(target.components.values())


def by_start(target):
    return sorted(ranges_of(target), key=lambda r: r.attrs["start"])


def row_names(target):
    return [row["name"] for row in target.attrs["rows"]]


def row_id_of(target, name):
    return next(row["id"] for row in target.attrs["rows"] if row["name"] == name)


def messages(result):
    return [problem.message for problem in result.problems]


class TestImportByTime:
    # From TiLiA's tests/parsers/csv/test_range_from_csv.py, TestImportByTime.

    def test_basic(self, do_import, target):
        result = do_import("start,end,row,label\n0,1,RowA,first\n1,2,RowB,second")

        assert result.problems == []
        first, second = ranges_of(target)
        assert first.kind == second.kind == "range"
        assert first.attrs["start"] == 0
        assert first.attrs["end"] == 1
        assert first.attrs["label"] == "first"
        assert second.attrs["label"] == "second"

    def test_auto_creates_rows_by_name(self, do_import, target):
        do_import("start,end,row\n0,1,Verses\n1,2,Choruses")

        assert row_names(target) == ["Verses", "Choruses"]

    def test_reuses_row_for_duplicate_name(self, do_import, target):
        do_import("start,end,row\n0,1,Existing\n1,2,Existing")

        assert row_names(target) == ["Existing"]
        existing = row_id_of(target, "Existing")
        assert all(r.attrs["row_id"] == existing for r in ranges_of(target))

    def test_propagates_color_and_comments(self, do_import, target):
        result = do_import(
            "start,end,row,color,comments\n0,1,A,#abcdef,note one\n1,2,A,,note two"
        )

        assert result.problems == []
        first, second = ranges_of(target)
        assert first.attrs["color"] == "#abcdef"
        assert first.attrs["comments"] == "note one"
        assert second.attrs["color"] is None
        assert second.attrs["comments"] == "note two"

    def test_missing_required_column_fails(self, do_import, target):
        with pytest.raises(ImportFailed) as failed:
            do_import("start,end,label\n0,1,first")

        assert (
            failed.value.message == "Column 'row' not found on first row of .csv file."
        )

    def test_bad_start_value_yields_error(self, do_import, target):
        result = do_import("start,end,row\nnonsense,1,A")

        assert messages(result) == ["nonsense is not a valid start."]
        assert result.problems[0].column == "start"
        assert result.problems[0].skipped
        assert ranges_of(target) == []

    def test_bad_end_value_yields_error(self, do_import, target):
        result = do_import("start,end,row\n0,nonsense,A")

        assert messages(result) == ["nonsense is not a valid end."]
        assert result.problems[0].column == "end"
        assert result.problems[0].skipped
        assert ranges_of(target) == []

    def test_empty_row_name_skipped(self, do_import, target):
        result = do_import("start,end,row\n0,1,\n1,2,A")

        assert messages(result) == ["row name is empty; skipping."]
        assert result.problems[0].column == "row"
        assert result.problems[0].skipped
        assert len(ranges_of(target)) == 1

    def test_skips_blank_lines(self, do_import, target):
        result = do_import("start,end,row\n0,1,A\n\n2,3,A")

        assert result.problems == []
        assert result.rows == 2
        assert len(ranges_of(target)) == 2


class TestImportReplacesExistingRows:
    def test_drops_pre_existing_rows(self, csv_file):
        old = component("range", start=0.0, end=1.0, row_id="Old123")
        target = timeline("range", attrs={"rows": [old_row()]}, components=[old])
        doc = document(timelines=[target])

        import_by_time(
            doc, target.id, csv_file("start,end,row\n0,1,Verses\n1,2,Choruses")
        )

        assert row_names(target) == ["Verses", "Choruses"]
        assert old.id not in target.components
        assert len(ranges_of(target)) == 2

    def test_creates_default_row_when_import_yields_none(self, do_import, target):
        # Every row fails, with an empty row name: zero rows imported.
        do_import("start,end,row\n0,1,\n1,2,")

        assert row_names(target) == ["Row 0"]
        assert ranges_of(target) == []


class TestEveryRowFailing:
    @pytest.mark.parametrize(
        "text",
        [
            "start,end,row\n0,1,\n1,2,",
            "start,end,row\nabc,1,A\n0,def,B",
            "start,end,row\n5,1,A\n1,61,B",
            "start,end,row\n",
        ],
        ids=[
            "with no row name",
            "that can't be read",
            "that the rules refuse",
            "no rows at all",
        ],
    )
    def test_leaves_one_blank_row(self, do_import, target, text):
        result = do_import(text)

        assert row_names(target) == ["Row 0"]
        assert ranges_of(target) == []
        assert result.created == []
        blank = target.attrs["rows"][0]
        assert blank["id"] != "Old123"
        assert rules.range_rows(target.attrs["rows"])


class TestRows:
    def test_row_ids_are_six_letters_and_digits(self, do_import, target):
        do_import("start,end,row\n0,1,A\n1,2,B\n2,3,C")

        ids = [row["id"] for row in target.attrs["rows"]]
        assert all(re.fullmatch("[A-Za-z0-9]{6}", row_id) for row_id in ids)
        assert len(set(ids)) == 3
        assert rules.range_rows(target.attrs["rows"])

    def test_a_row_has_the_layouts_keys(self, do_import, target):
        do_import("start,end,row\n0,1,A")

        row = target.attrs["rows"][0]
        assert list(row) == ["id", "name", "color", "height"]
        assert row["color"] is None
        assert row["height"] is None

    def test_rows_are_in_order_of_appearance(self, do_import, target):
        do_import("start,end,row\n5,6,Zebra\n0,1,Apple\n1,2,Zebra\n2,3,Mango")

        assert row_names(target) == ["Zebra", "Apple", "Mango"]

    def test_row_names_are_compared_in_nfc(self, do_import, target):
        do_import("start,end,row\n0,1,é\n1,2,é")

        assert row_names(target) == ["é"]
        assert len(ranges_of(target)) == 2

    def test_a_refused_range_still_makes_its_row(self, do_import, target):
        # As TiLiA's importer gets or creates the row before creating the range.
        result = do_import("start,end,row\n0,1,A\n5,1,B\n1,2,C")

        assert row_names(target) == ["A", "B", "C"]
        assert messages(result) == ["Start time must be before end time."]

    def test_a_row_that_cant_be_read_makes_no_row(self, do_import, target):
        do_import("start,end,row\nabc,1,A\n0,1,B")

        assert row_names(target) == ["B"]

    def test_each_range_names_its_row(self, do_import, target):
        do_import("start,end,row\n0,1,A\n1,2,B")

        first, second = ranges_of(target)
        assert first.attrs["row_id"] == row_id_of(target, "A")
        assert second.attrs["row_id"] == row_id_of(target, "B")


class TestJoinedWithNextByTime:
    def test_basic_join(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,1,A,true\n1,2,A,false")

        assert result.problems == []
        first, second = ranges_of(target)
        assert first.attrs["joined_right"] == second.id
        assert second.attrs["joined_right"] is None

    def test_chain_of_three(self, do_import, target):
        do_import("start,end,row,joined_with_next\n0,1,A,true\n1,2,A,true\n2,3,A,false")

        first, second, third = ranges_of(target)
        assert first.attrs["joined_right"] == second.id
        assert second.attrs["joined_right"] == third.id
        assert third.attrs["joined_right"] is None

    def test_join_only_within_same_row(self, do_import, target):
        # The next entry of the CSV lives on another row: the join goes to the
        # next one in its own row.
        do_import(
            "start,end,row,joined_with_next\n0,1,A,true\n0,1,B,false\n1,2,A,false"
        )

        a_first, b, a_second = ranges_of(target)
        assert a_first.attrs["joined_right"] == a_second.id
        assert b.attrs["joined_right"] is None

    def test_default_is_unjoined(self, do_import, target):
        do_import("start,end,row\n0,1,A\n1,2,A")

        assert all(r.attrs["joined_right"] is None for r in ranges_of(target))

    def test_join_target_uses_temporal_order_not_csv_order(self, do_import, target):
        do_import("start,end,row,joined_with_next\n1,2,A,false\n0,1,A,true\n")

        later, earlier = ranges_of(target)
        assert earlier.attrs["joined_right"] == later.id
        assert later.attrs["joined_right"] is None

    def test_invalid_boolean_reports_error(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,1,A,maybe\n1,2,A,false")

        problem = result.problems[0]
        assert problem.message == "maybe is not a valid joined with next."
        assert problem.column == "joined_with_next"
        # The row is imported, read as false.
        assert not problem.skipped
        first, second = ranges_of(target)
        assert first.attrs["joined_right"] is None
        assert second.attrs["joined_right"] is None

    def test_a_row_the_rules_refuse_gets_no_note_about_its_join(
        self, do_import, target
    ):
        # It wasn't imported, so nothing was read as false.
        result = do_import("start,end,row,joined_with_next\n2,1,A,maybe\n")

        assert messages(result) == ["Start time must be before end time."]
        assert result.problems[0].column is None
        assert result.problems[0].skipped
        assert ranges_of(target) == []

    def test_a_kept_row_gets_both_its_notes(self, do_import, target):
        result = do_import(
            "start,end,row,joined_with_next,color\n0,1,A,maybe,notacolor\n"
        )

        assert messages(result) == [
            "maybe is not a valid joined with next.",
            "notacolor is not a valid color: the default color is used.",
        ]
        assert not any(problem.skipped for problem in result.problems)
        assert len(ranges_of(target)) == 1

    @pytest.mark.parametrize("cell", ["true", "TRUE", "True", " true "])
    def test_true_in_any_case(self, do_import, target, cell):
        result = do_import(f"start,end,row,joined_with_next\n0,1,A,{cell}\n1,2,A,")

        assert result.problems == []
        first, second = ranges_of(target)
        assert first.attrs["joined_right"] == second.id

    @pytest.mark.parametrize("cell", ["false", "FALSE", "", "  "])
    def test_false_in_any_case_or_blank(self, do_import, target, cell):
        result = do_import(f"start,end,row,joined_with_next\n0,1,A,{cell}\n1,2,A,")

        assert result.problems == []
        assert ranges_of(target)[0].attrs["joined_right"] is None


class TestJoinValidation:
    def test_flag_on_last_range_reports_error(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,1,A,false\n1,2,A,true")

        assert messages(result) == [
            "joined_with_next=true on last range of row 'A'; no next neighbor to join with"
        ]
        # The ranges are still created; only the join is dropped.
        assert len(ranges_of(target)) == 2
        assert ranges_of(target)[-1].attrs["joined_right"] is None

    def test_gap_between_joined_ranges_reports_error(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,10,A,true\n20,30,A,false")

        assert messages(result) == [
            "joined_with_next=true but next range on row 'A' starts at 20.0"
            " (must equal 10.0 for ranges to join)"
        ]
        assert ranges_of(target)[0].attrs["joined_right"] is None

    def test_overlap_between_joined_ranges_reports_error(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,10,A,true\n5,15,A,false")

        assert messages(result) == [
            "joined_with_next=true but next range on row 'A' starts at 5.0"
            " (must equal 10.0 for ranges to join)"
        ]
        assert ranges_of(target)[0].attrs["joined_right"] is None

    def test_only_invalid_join_is_dropped(self, do_import, target):
        result = do_import(
            "start,end,row,joined_with_next\n0,10,A,true\n10,20,A,true\n30,40,A,false"
        )

        assert len(result.problems) == 1
        first, second, third = ranges_of(target)
        assert first.attrs["joined_right"] == second.id
        assert second.attrs["joined_right"] is None
        assert third.attrs["joined_right"] is None

    def test_a_broken_join_keeps_the_row_and_is_a_problem(self, do_import, target):
        # contracts/rules.md, Decisions 19: only the join is refused, the row is
        # imported without it, and the problem counts, for tilia run's status 1.
        result = do_import("start,end,row,joined_with_next\n0,1,A,true")

        only = ranges_of(target)[0]
        assert result.created == [only.id]
        problem = result.problems[0]
        assert problem.line == 2
        assert problem.column == "joined_with_next"
        assert problem.skipped

    def test_a_range_whose_join_is_broken_is_still_joined_to(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n0,1,A,true\n1,2,A,true")

        first, second = ranges_of(target)
        assert first.attrs["joined_right"] == second.id
        assert second.attrs["joined_right"] is None
        assert [problem.line for problem in result.problems] == [3]


class TestJoinsAmongTheRangesKept:
    # contracts/rules.md, Decisions 15: joins are made among the ranges the check
    # kept, as TiLiA joins only the ranges it created.

    def test_joined_to_the_next_range_kept(self, do_import, target):
        result = do_import(
            "start,end,row,joined_with_next\n1,2,A,true\n2,61,A,false\n2,3,A,false"
        )

        first, kept = ranges_of(target)
        assert first.attrs["joined_right"] == kept.id
        assert kept.attrs["start"] == 2
        assert kept.attrs["end"] == 3
        assert messages(result) == ["Range is outside media bounds."]

    def test_the_next_range_kept_doesnt_start_where_it_ends(self, do_import, target):
        result = do_import(
            "start,end,row,joined_with_next\n1,2,A,true\n2,61,A,false\n5,6,A,false"
        )

        assert messages(result) == [
            "joined_with_next=true but next range on row 'A' starts at 5.0"
            " (must equal 2.0 for ranges to join)",
            "Range is outside media bounds.",
        ]
        assert ranges_of(target)[0].attrs["joined_right"] is None

    def test_no_next_range_kept(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n1,2,A,true\n2,61,A,false")

        assert messages(result) == [
            "joined_with_next=true on last range of row 'A'; no next neighbor to join with",
            "Range is outside media bounds.",
        ]
        assert ranges_of(target)[0].attrs["joined_right"] is None

    def test_a_refused_range_is_never_joined(self, do_import, target):
        result = do_import("start,end,row,joined_with_next\n1,61,A,true\n61,62,A,false")

        assert messages(result) == [
            "Range is outside media bounds.",
            "Range is outside media bounds.",
        ]
        assert ranges_of(target) == []

    def test_the_first_in_the_csv_when_the_next_ranges_share_a_start(
        self, do_import, target
    ):
        # contracts/rules.md, Decisions 11.
        result = do_import(
            "start,end,row,joined_with_next\n0,1,A,true\n1,3,A,false\n1,2,A,false"
        )

        assert result.problems == []
        first, second, _ = ranges_of(target)
        assert first.attrs["joined_right"] == second.id

    def test_a_range_with_the_flagged_ones_start_isnt_next(self, do_import, target):
        # The rule's next range starts after this one starts (contracts/rules.md,
        # Range). TiLiA's importer sorts this row by start and takes what follows,
        # so it reports the join as starting at 0.0.
        result = do_import(
            "start,end,row,joined_with_next\n0,1,A,true\n0,2,A,false\n1,2,A,false"
        )

        assert result.problems == []
        first, _, third = ranges_of(target)
        assert first.attrs["joined_right"] == third.id

    def test_two_flagged_at_one_start_join_the_same_next_range(self, do_import, target):
        # TiLiA's importer takes what follows in its sorted list, so it reports
        # "must equal" for the first.
        result = do_import(
            "start,end,row,joined_with_next\n0,1,A,true\n0,1,A,true\n1,2,A,false"
        )

        assert result.problems == []
        first, second, third = ranges_of(target)
        assert first.attrs["joined_right"] == third.id
        assert second.attrs["joined_right"] == third.id


class TestTheRules:
    # Every range is checked with the core's one set of rules.

    @pytest.mark.parametrize(
        "row, message, column",
        [
            ("1,1,A", "Start time must be before end time.", None),
            ("2,1,A", "Start time must be before end time.", None),
            ("-1,1,A", "Range is outside media bounds.", None),
            ("0,61,A", "Range is outside media bounds.", None),
            ("nan,1,A", "nan is not a valid start.", "start"),
            ("0,nan,A", "nan is not a valid end.", "end"),
            ("inf,1,A", "inf is not a valid start.", "start"),
            ("0,inf,A", "inf is not a valid end.", "end"),
        ],
    )
    def test_a_row_the_rules_refuse_is_skipped_and_reported(
        self, do_import, target, row, message, column
    ):
        result = do_import(f"start,end,row\n0,1,Kept\n{row}\n")

        assert messages(result) == [message]
        assert result.problems[0].column == column
        assert result.problems[0].line == 3
        assert result.problems[0].skipped
        assert len(ranges_of(target)) == 1

    def test_a_time_at_the_media_length_is_kept(self, do_import, target):
        result = do_import("start,end,row\n0,60,A")

        assert result.problems == []

    def test_one_check_per_import_without_joins(self, do_import, monkeypatch):
        calls = count_checks(monkeypatch)

        do_import("start,end,row\n0,1,A\n1,2,A\n2,3,B")

        assert len(calls) == 1
        assert calls[0]["skip_broken"] is True

    def test_the_joins_are_checked_once_more_with_the_ranges_kept(
        self, do_import, target, monkeypatch
    ):
        # T007: the joins are made among the ranges kept, then checked with them.
        calls = count_checks(monkeypatch)

        do_import("start,end,row,joined_with_next\n0,1,A,true\n1,2,A,\n5,1,B,")

        assert len(calls) == 2
        assert len(calls[0]["components"]) == 3  # every range built
        assert len(calls[1]["components"]) == 2  # those kept

    def test_the_kinds_function_isnt_called_row_by_row(self, do_import, monkeypatch):
        def refuse(*_args, **_kwargs):
            raise AssertionError("checked row by row")

        monkeypatch.setattr(rules, "range_", refuse)

        do_import("start,end,row\n0,1,A")

    def test_every_range_goes_through_the_check(self, do_import, target, monkeypatch):
        # Whatever the rules say is what the importer does: it has no check of
        # its own that would keep or refuse a range without them.
        def refuse_all(_media, components, **_kwargs):
            return {
                c.id: rules.Checked(rules.Outcome(False, "refused")) for c in components
            }

        monkeypatch.setattr(rules, "check_timeline", refuse_all)

        result = do_import("start,end,row\n0,1,A")

        assert messages(result) == ["refused"]
        assert ranges_of(target) == []


def count_checks(monkeypatch):
    calls = []
    check_timeline = rules.check_timeline

    def counted(media_length, components, **kwargs):
        components = list(components)
        calls.append({"components": components, **kwargs})
        return check_timeline(media_length, components, **kwargs)

    monkeypatch.setattr(rules, "check_timeline", counted)
    return calls


class TestColor:
    # contracts/rules.md, Decisions 4: a color that isn't one keeps its row.

    def test_a_color_that_isnt_one_uses_the_default_with_a_note(
        self, do_import, target
    ):
        result = do_import("start,end,row,color\n0,1,A,notacolor")

        assert ranges_of(target)[0].attrs["color"] is None
        problem = result.problems[0]
        assert (
            problem.message
            == "notacolor is not a valid color: the default color is used."
        )
        assert problem.column == "color"
        assert problem.line == 2
        assert not problem.skipped
        assert result.skipped == []

    def test_a_bad_color_doesnt_hide_a_broken_rule(self, do_import, target):
        result = do_import("start,end,row,color\n5,1,A,notacolor")

        assert messages(result) == ["Start time must be before end time."]
        assert result.problems[0].skipped
        assert ranges_of(target) == []

    @pytest.mark.parametrize("color", ["#abc", "#AABBCC", "red", "transparent"])
    def test_a_color_is_stored_as_written(self, do_import, target, color):
        result = do_import(f"start,end,row,color\n0,1,A,{color}")

        assert result.problems == []
        assert ranges_of(target)[0].attrs["color"] == color

    def test_a_bad_color_keeps_the_range_among_those_joined(self, do_import, target):
        do_import(
            "start,end,row,color,joined_with_next\n0,1,A,notacolor,true\n1,2,A,,false"
        )

        first, second = ranges_of(target)
        assert first.attrs["joined_right"] == second.id


class TestShortRows:
    # A column the row is too short for reads as an empty cell. TiLiA's range
    # importer raises IndexError there; a row is reported, never raised (FR-022).

    @pytest.mark.parametrize(
        "row, column, message",
        [
            ("0", "end", "an empty value is not a valid end."),
            ("0,1", "row", "row name is empty; skipping."),
        ],
        ids=["end", "row"],
    )
    def test_a_required_cell_missing_skips_the_row(
        self, do_import, target, row, column, message
    ):
        result = do_import(f"start,end,row\n{row}\n0,1,A\n")

        assert messages(result) == [message]
        problem = result.problems[0]
        assert problem.column == column
        assert problem.line == 2
        assert problem.skipped
        assert len(ranges_of(target)) == 1

    def test_an_empty_required_cell_reads_the_same(self, do_import):
        result = do_import("start,end,row\n0,,A\n")

        assert messages(result) == ["an empty value is not a valid end."]

    @pytest.mark.parametrize(
        "column", ["label", "color", "comments", "joined_with_next"]
    )
    def test_an_optional_cell_missing_is_its_default(self, do_import, target, column):
        result = do_import(f"start,end,row,{column}\n0,1,A\n")

        assert result.problems == []
        attrs = ranges_of(target)[0].attrs
        assert attrs["label"] == ""
        assert attrs["color"] is None
        assert attrs["comments"] == ""
        assert attrs["joined_right"] is None


class TestCellsOfOnlySpaces:
    @pytest.mark.parametrize(
        "row, column, message",
        [
            ('"  ",1,A', "start", "an empty value is not a valid start."),
            ('0,"  ",A', "end", "an empty value is not a valid end."),
            ('0,1,"  "', "row", "row name is empty; skipping."),
        ],
        ids=["start", "end", "row"],
    )
    def test_a_required_one_reads_as_an_empty_one(
        self, do_import, target, row, column, message
    ):
        result = do_import(f"start,end,row\n{row}\n")

        assert messages(result) == [message]
        assert result.problems[0].column == column
        assert result.problems[0].skipped
        assert ranges_of(target) == []
        assert row_names(target) == ["Row 0"]

    def test_the_optional_ones_are_as_if_empty(self, do_import, target):
        result = do_import(
            "start,end,row,label,color,comments,joined_with_next\n"
            '0,1,A," "," "," "," "\n'
        )

        assert result.problems == []
        attrs = ranges_of(target)[0].attrs
        assert attrs["label"] == ""
        assert attrs["color"] is None
        assert attrs["comments"] == ""
        assert attrs["joined_right"] is None


class TestResult:
    def test_created_is_the_new_ids_in_the_order_of_the_rows(self, do_import, target):
        result = do_import("start,end,row\n1,2,A\n5,1,A\n0,1,A")

        assert result.created == list(target.components)
        assert [target.components[i].attrs["start"] for i in result.created] == [1, 0]

    def test_each_range_gets_a_new_id(self, do_import, target):
        do_import("start,end,row\n0,1,A\n1,2,A")

        first, second = ranges_of(target)
        assert first.id != second.id
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-.{4}-.{12}", first.id
        )

    def test_rows_counts_those_read_and_leaves_empty_ones_out(self, do_import):
        result = do_import("start,end,row\n0,1,A\n\nabc,1,A\n\n5,1,A")

        assert result.rows == 3

    def test_problems_are_in_row_order_whichever_step_found_them(self, do_import):
        result = do_import(
            "start,end,row,color,joined_with_next\n"
            "0,0.5,A,,true\n"  # the join, found last
            "abc,1,A,,\n"  # read
            "5,1,A,,\n"  # the rules
            "1,2,A,notacolor,maybe\n"  # read, then the color
            "2,3,,,\n"  # read
        )

        assert [(p.line, p.column) for p in result.problems] == [
            (2, "joined_with_next"),
            (3, "start"),
            (4, None),
            (5, "joined_with_next"),
            (5, "color"),
            (6, "row"),
        ]

    def test_a_problems_path_is_the_csv(self, do_import, tmp_path):
        result = do_import("start,end,row\nabc,1,A")

        assert result.problems[0].path == tmp_path / "ranges.csv"

    def test_a_line_break_in_a_quoted_cell_keeps_the_lines_right(self, do_import):
        result = do_import('start,end,row,label\n0,1,A,"two\nlines"\nabc,1,A,\n')

        assert result.problems[0].line == 4

    def test_a_label_and_a_comment_absent_from_the_csv_are_empty(
        self, do_import, target
    ):
        do_import("start,end,row\n0,1,A")

        attrs = ranges_of(target)[0].attrs
        assert attrs["label"] == ""
        assert attrs["comments"] == ""
        assert attrs["color"] is None
        assert attrs["joined_right"] is None
        assert "pre_start" not in attrs
        assert "post_end" not in attrs

    def test_unknown_columns_are_ignored(self, do_import, target):
        result = do_import("start,end,row,ignored,pre_start\n0,1,A,x,0.5")

        assert result.problems == []
        assert "ignored" not in ranges_of(target)[0].attrs
        assert "pre_start" not in ranges_of(target)[0].attrs


class TestTheDocument:
    def test_importing_twice_gives_the_same_new_ids_aside(self, csv_file, target):
        doc = document(timelines=[target])
        path = csv_file(
            "start,end,row,label,joined_with_next\n0,1,A,x,true\n1,2,A,y,\n2,3,B,z,"
        )

        import_by_time(doc, target.id, path)
        first = [_without_ids(target, r) for r in ranges_of(target)]
        first_rows = row_names(target)
        import_by_time(doc, target.id, path)

        assert [_without_ids(target, r) for r in ranges_of(target)] == first
        assert row_names(target) == first_rows
        assert len(target.components) == 3

    def test_a_quarters_document_reads_times_as_they_are(self, do_import, target):
        result = do_import(
            "start,end,row\n0,120,A", time_unit="quarters", media_length=240.0
        )

        assert result.problems == []
        assert ranges_of(target)[0].attrs["end"] == 120

    @pytest.mark.parametrize(
        "text, encoding",
        [
            ("start,end,label\n0,1,x", "utf-8"),
            ("", "utf-8"),
            ("start,end,row\n0,1,café", "cp1252"),
        ],
        ids=["a missing column", "an empty file", "a file that isn't UTF-8"],
    )
    def test_a_failed_import_changes_nothing(self, csv_file, text, encoding):
        old = component("range", start=0.0, end=1.0, row_id="Old123")
        target = timeline("range", attrs={"rows": [old_row()]}, components=[old])
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed):
            import_by_time(doc, target.id, csv_file(text, encoding))

        assert list(target.components) == [old.id]
        assert row_names(target) == ["Old"]

    def test_a_file_that_doesnt_exist_changes_nothing(self, tmp_path):
        old = component("range", start=0.0, end=1.0, row_id="Old123")
        target = timeline("range", attrs={"rows": [old_row()]}, components=[old])
        doc = document(timelines=[target])

        with pytest.raises(OSError):
            import_by_time(doc, target.id, tmp_path / "missing.csv")

        assert list(target.components) == [old.id]
        assert row_names(target) == ["Old"]

    def test_a_document_with_no_media_length_changes_nothing(self, csv_file):
        # TimeLineAnnotator/project-management#418: a file can bring a timeline and
        # no media length.
        old = component("range", start=0.0, end=1.0, row_id="Old123")
        target = timeline("range", attrs={"rows": [old_row()]}, components=[old])
        doc = document(timelines=[target], media_length=None)

        with pytest.raises(ImportFailed) as failed:
            import_by_time(doc, target.id, csv_file("start,end,row\n0,1,A"))

        assert failed.value.message.startswith("No media loaded and no duration set.")
        assert list(target.components) == [old.id]
        assert row_names(target) == ["Old"]

    def test_a_component_of_a_kind_the_core_doesnt_know_stays(self, csv_file):
        # FR-032, and WP3's FR-015.
        old = component("range", start=0.0, end=1.0, row_id="Old123")
        unknown = tla.Component(
            id=tla.new_id(), kind=tla.UnknownKind("LYRIC"), extra={"start": 0.0}
        )
        target = timeline(
            "range",
            attrs={"rows": [old_row()], "height": 80},
            components=[old, unknown],
        )
        written = tla.canonical_bytes(document(timelines=[target]))
        read = tla.loads(written)

        result = import_by_time(read, target.id, csv_file("start,end,row\n0,1,A"))

        kept = read.timelines[target.id]
        assert set(kept.components) == {unknown.id, *result.created}
        assert kept.components[unknown.id] == unknown
        assert [row["name"] for row in kept.attrs["rows"]] == ["A"]
        assert (
            json.loads(tla.canonical_bytes(read))["timelines"][target.id]["components"][
                unknown.id
            ]
            == json.loads(written)["timelines"][target.id]["components"][unknown.id]
        )

    def test_the_path_can_be_text(self, csv_file, target):
        path = csv_file("start,end,row\nabc,1,A")
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, str(path))

        assert result.problems[0].path == path

    def test_the_required_columns_are_named_in_tilias_order(self, do_import):
        with pytest.raises(ImportFailed) as failed:
            do_import("label\nx")

        assert failed.value.message == (
            "Column 'start' not found on first row of .csv file."
        )

    def test_the_timelines_other_attributes_stay(self, csv_file):
        target = timeline(
            "range", attrs={"rows": [old_row()], "height": 80, "default_row_height": 20}
        )
        doc = document(timelines=[target])

        import_by_time(doc, target.id, csv_file("start,end,row\n0,1,A"))

        assert target.attrs["height"] == 80
        assert target.attrs["default_row_height"] == 20

    def test_an_imported_document_can_be_written_and_read_back(self, csv_file, target):
        target.attrs["height"] = 80  # a written timeline has one
        doc = document(timelines=[target])
        import_by_time(
            doc,
            target.id,
            csv_file(
                "start,end,row,label,color,comments,joined_with_next\n"
                "0,1,A,one,#abcdef,first,true\n"
                "1,2,A,two,,,\n"
                "0,2,B,three,,,\n"
            ),
        )

        read = tla.loads(tla.canonical_bytes(doc))

        again = read.timelines[target.id]
        assert again.attrs["rows"] == target.attrs["rows"]
        assert [
            {key: value for key, value in c.attrs.items() if value is not None}
            for c in again.components.values()
        ] == [
            {key: value for key, value in c.attrs.items() if value is not None}
            for c in target.components.values()
        ]


def _without_ids(target, component):
    """A range's attributes, its row by name and its join by the next one's start."""
    attrs = dict(component.attrs)
    attrs["row_id"] = next(
        row["name"] for row in target.attrs["rows"] if row["id"] == attrs["row_id"]
    )
    joined = attrs["joined_right"]
    attrs["joined_right"] = (
        None if joined is None else target.components[joined].attrs["start"]
    )
    return attrs
