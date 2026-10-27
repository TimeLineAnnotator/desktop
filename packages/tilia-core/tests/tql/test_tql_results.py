"""Result.to_csv: the table of rows as a file."""

import csv

import examples
import fixture_index

from tilia_core import tql

FIXTURES = examples.load()["fixtures"]


def run(name, query):
    return tql.run(fixture_index.build_index(FIXTURES[name]), query)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_csv_read_back_is_the_table(tmp_path):
    result = run("pop", "verse THEN chorus IN form")
    path = tmp_path / "out.csv"
    result.to_csv(path)
    lines = read(path)
    columns = lines[0]
    assert columns[:3] == ["file", "title", "timeline"]
    assert len(lines) == len(result.rows) + 1 > 1
    for line, row in zip(lines[1:], result.rows, strict=True):
        for column, field in zip(columns, line, strict=True):
            value = row[column]
            if value is None:
                assert field == ""
            elif column in ("start", "end") or column.endswith((".start", ".end")):
                assert field == f"{value:.3f}"
            else:
                assert field == str(value)


def test_columns_are_the_rows_keys():
    for name, query in (
        ("pop", "verse THEN chorus IN form"),
        ("pop", "chorus"),
        ("harmony", "* IN chords DURING * IN keys"),
        ("harmony", "WHERE key = C"),
        ("pop", "WHERE tl.kind = hierarchy"),
        ("harmony", 'WHERE file.composer = "Mozart"'),
    ):
        result = run(name, query)
        assert result.rows, query
        for row in result.rows:
            assert list(row) == result.columns, query


def test_a_chord_row_carries_its_symbol_and_its_roman_numeral():
    # Felipe, 2026-10-27: label is the symbol, TiLiA's default display; the row
    # carries both, whatever each chord's display_mode
    result = run("harmony", "V7 THEN I IN harmony")
    got = [(r["label"], r["symbol"], r["roman"], r["$1.label"]) for r in result.rows]
    assert got == [
        ("G7 → C", "G7 → C", "V7 → I", "G7"),
        ("G7/B → C", "G7/B → C", "V65 → I", "G7/B"),
        ("G7 → C", "G7 → C", "V7 → I", "G7"),
        ("Bb7 → Eb", "Bb7 → Eb", "V7 → I", "Bb7"),
    ]
    row = run("harmony", "@V65 THEN I IN harmony").rows[0]
    assert (row["label"], row["symbol"], row["roman"]) == ("G7/B", "G7/B", "V65")
    row = run("pop", "chorus IN form").rows[0]
    assert (row["symbol"], row["roman"]) == (None, None)
    row = run("harmony", "Eb IN keys").rows[0]
    assert (row["label"], row["symbol"], row["roman"]) == ("Eb", None, None)


def test_an_empty_result_writes_the_header(tmp_path):
    path = tmp_path / "out.csv"
    full = run("pop", "verse THEN chorus IN form")
    empty = run("pop", "nothing THEN chorus IN form")
    assert empty.rows == []
    empty.to_csv(path)
    assert read(path) == [list(full.rows[0])]
    empty = run("harmony", 'WHERE file.composer = "Nobody"')
    assert empty.rows == [] and empty.grain == "file"
    empty.to_csv(path)
    assert read(path) == [["file", "title", "composer"]]
    empty = run("harmony", 'WHERE tl.kind = nothing')
    assert empty.rows == [] and empty.grain == "timeline"
    empty.to_csv(path)
    assert read(path) == [["file", "title", "timeline", "kind", "role", "author"]]


def test_no_bom_no_cr(tmp_path):
    path = tmp_path / "out.csv"
    run("pop", "chorus IN form").to_csv(path)
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"\n")


def test_times_have_three_decimals(tmp_path):
    path = tmp_path / "out.csv"
    run("pop", "verse THEN chorus IN form").to_csv(path)
    lines = read(path)
    columns = lines[0]
    first = dict(zip(columns, lines[1], strict=True))
    assert first["start"] == "8.000"
    assert first["end"] == "56.000"
    assert first["$1.start"] == "8.000"
    assert first["$2.end"] == "56.000"
    assert first["bar"] == "3"  # not a time: written as it is


def test_none_is_an_empty_field(tmp_path):
    path = tmp_path / "out.csv"
    run("pop", "chorus IN form").to_csv(path)
    lines = read(path)
    first = dict(zip(lines[0], lines[1], strict=True))
    assert first["title"] == ""


def test_non_ascii_labels_in_nfc(tmp_path):
    path = tmp_path / "out.csv"
    run("scripts", "主歌 OR Straße").to_csv(path)
    text = path.read_bytes().decode("utf-8")
    assert "主歌" in text and "Straße" in text
    lines = read(path)
    labels = [dict(zip(lines[0], line, strict=True))["label"] for line in lines[1:]]
    assert labels == ["主歌", "主歌", "Straße"]


def test_decomposed_label_is_written_in_nfc(tmp_path):
    fixture = {
        "length": 10,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [["Straśe", 1, 0, 10]],
            }
        ],
    }
    result = tql.run(fixture_index.build_index(fixture), "* IN form")
    path = tmp_path / "out.csv"
    result.to_csv(path)
    label = dict(zip(*read(path)[:2], strict=True))["label"]
    assert label == "Straśe"


def test_quoting_is_minimal(tmp_path):
    fixture = {
        "length": 10,
        "timelines": [
            {
                "name": "Form (X)",
                "kind": "hierarchy",
                "units": [['a, "b"', 1, 0, 10]],
            }
        ],
    }
    result = tql.run(fixture_index.build_index(fixture), "* IN form")
    path = tmp_path / "out.csv"
    result.to_csv(path)
    assert '"a, ""b"""' in path.read_text(encoding="utf-8")
    assert dict(zip(*read(path)[:2], strict=True))["label"] == 'a, "b"'
