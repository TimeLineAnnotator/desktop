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
