import copy
import re
from pathlib import Path

import pytest
from import_docs import component, document, timeline

from tilia_core.importers import _commit
from tilia_core.importers._commit import commit
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem


def row(name, row_id="Ab12Cd"):
    return {"id": row_id, "name": name, "color": None, "height": None}


def problem(*, skipped):
    return RowProblem(
        path=Path("markers.csv"),
        line=3,
        column="time",
        message="'abc' is not a valid time",
        skipped=skipped,
    )


def test_commit_replaces_and_doesnt_append():
    target = timeline("marker", components=[component("MARKER", time=1.0)])
    doc = document(timelines=[target])
    new = [component("MARKER", time=2.0), component("MARKER", time=3.0)]

    commit(doc, target.id, new)

    assert list(target.components.values()) == new
    assert list(target.components) == [c.id for c in new]


def test_commit_with_no_components_empties_the_target():
    target = timeline("marker", components=[component("MARKER", time=1.0)])
    doc = document(timelines=[target])

    commit(doc, target.id, [])

    assert target.components == {}


def test_rows_replace_a_range_timelines_rows():
    target = timeline("range", attrs={"rows": [row("Old", "Old123")]})
    doc = document(timelines=[target])
    rows = [row("Bass", "Bass12"), row("Soprano", "Sopr12")]

    commit(doc, target.id, [], rows=rows)

    assert target.attrs["rows"] == rows


def test_a_range_with_no_rows_gets_one_blank_row():
    # As RangeTimeline.setup_blank_timeline makes it.
    target = timeline("range", attrs={"rows": [row("Old", "Old123")]})
    doc = document(timelines=[target])

    commit(doc, target.id, [], rows=[])

    (blank,) = target.attrs["rows"]
    assert list(blank) == ["id", "name", "color", "height"]
    assert re.fullmatch("[A-Za-z0-9]{6}", blank["id"])
    assert blank["name"] == "Row 0"
    assert blank["color"] is None
    assert blank["height"] is None


def test_a_new_row_id_is_none_of_those_taken(monkeypatch):
    drawn = iter(["Ab12Cd", "Ef34Gh", "Ij56Kl"])
    monkeypatch.setattr(
        _commit.random, "choices", lambda characters, k: list(next(drawn))
    )

    assert _commit.new_row_id({"Ab12Cd", "Ef34Gh"}) == "Ij56Kl"


def test_without_rows_the_rows_stay():
    rows = [row("Bass")]
    target = timeline("range", attrs={"rows": rows})
    doc = document(timelines=[target])

    commit(doc, target.id, [])

    assert target.attrs["rows"] == [row("Bass")]


def test_attrs_update_the_targets_attrs():
    target = timeline("marker", attrs={"height": 30, "measure_table": "earlier"})
    doc = document(timelines=[target])

    commit(doc, target.id, [], attrs={"measure_table": "beats"})

    assert target.attrs == {"height": 30, "measure_table": "beats"}


def test_nothing_else_of_the_document_changes():
    target = timeline(
        "range",
        name="Sections",
        ordinal=2,
        components=[component("RANGE", start=0.0, end=1.0, row_id="Old123")],
        attrs={"rows": [row("Old", "Old123")], "height": 40},
    )
    other = timeline("marker", components=[component("MARKER", time=5.0)])
    doc = document(timelines=[other, target])
    doc.metadata = {"title": "Untitled", "notes": ""}
    doc.media_path = "piece.wav"
    before = copy.deepcopy(doc)
    new = [component("RANGE", start=2.0, end=3.0, row_id="Bass12")]

    commit(doc, target.id, new, rows=[row("Bass", "Bass12")])

    expected = before
    expected.timelines[target.id].components = {c.id: c for c in new}
    expected.timelines[target.id].attrs["rows"] = [row("Bass", "Bass12")]
    assert doc == expected


def test_an_unknown_target_changes_nothing():
    target = timeline("marker", components=[component("MARKER", time=1.0)])
    doc = document(timelines=[target])
    before = copy.deepcopy(doc)

    with pytest.raises(KeyError):
        commit(doc, "no such timeline", [component("MARKER", time=2.0)])

    assert doc == before


def test_skipped_lists_the_problems_whose_row_wasnt_imported():
    skipped, note = problem(skipped=True), problem(skipped=False)

    result = ImportResult(created=["a"], rows=2, problems=[note, skipped])

    assert result.skipped == [skipped]


def test_an_import_result_starts_empty():
    result = ImportResult()

    assert (result.created, result.rows, result.problems, result.notes) == (
        [],
        0,
        [],
        [],
    )
    assert result.skipped == []


def test_import_failed_names_the_file():
    error = ImportFailed(
        Path("data") / "chords.csv",
        "Column 'time' not found on first row of .csv file.",
    )

    assert error.path == Path("data") / "chords.csv"
    assert error.message == "Column 'time' not found on first row of .csv file."
    assert (
        str(error) == "chords.csv: Column 'time' not found on first row of .csv file."
    )


def test_import_failed_names_its_file_once():
    path = Path("data") / "chords.csv"
    message = f"'{path}' is not a valid UTF-8 encoded CSV file."

    assert str(ImportFailed(path, message)) == message


def test_import_failed_without_a_file():
    error = ImportFailed(
        None, "Reference beat timeline is required for importing by measure"
    )

    assert error.path is None
    assert str(error) == "Reference beat timeline is required for importing by measure"
