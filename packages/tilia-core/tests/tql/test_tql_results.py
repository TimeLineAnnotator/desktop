"""Result.to_csv: the table of rows as a file."""

import csv
import logging
import re
import threading

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


def exposition(**limits):
    return tql.run(
        fixture_index.build_index(FIXTURES["exposition"]), "* IN form", **limits
    )


class TestStoppedResult:
    """A result that stopped early hands the reason back when it is written."""

    def test_a_cut_result_returns_the_reason(self, tmp_path):
        result = exposition(max_matches=3)
        assert result.stopped == "max_matches"
        assert result.to_csv(tmp_path / "out.csv") == "max_matches"

    def test_a_complete_result_returns_none(self, tmp_path):
        result = exposition()
        assert result.stopped is None
        assert result.to_csv(tmp_path / "out.csv") is None

    def test_a_result_the_limit_did_not_reach_returns_none(self, tmp_path):
        assert exposition(max_matches=100).to_csv(tmp_path / "out.csv") is None

    def test_a_run_cancelled_before_it_started_returns_cancelled(self, tmp_path):
        cancel = threading.Event()
        cancel.set()
        result = exposition(cancel=cancel)
        assert result.to_csv(tmp_path / "out.csv") == "cancelled"

    def test_a_run_stopped_by_its_time_limit_returns_the_reason(self, tmp_path):
        assert exposition(time_limit=0).to_csv(tmp_path / "out.csv") == "time_limit"

    def test_the_file_of_a_cut_result_is_exactly_its_table(self, tmp_path):
        result = exposition(max_matches=3)
        assert len(result.rows) == 3
        path = tmp_path / "out.csv"
        result.to_csv(path)
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in data
        assert data.endswith(b"\n")
        lines = read(path)
        assert len(lines) == len(result.rows) + 1
        assert len(data.splitlines()) == len(result.rows) + 1
        for line in lines:
            assert len(line) == len(lines[0])
        assert b"max_matches" not in data and b"stopped" not in data

    def test_the_file_of_a_cut_result_is_the_file_of_the_same_rows_whole(
        self, tmp_path
    ):
        result = exposition(max_matches=3)
        cut_path = tmp_path / "cut.csv"
        result.to_csv(cut_path)
        result.stopped = None  # the same rows, as if they were all there are
        whole_path = tmp_path / "whole.csv"
        assert result.to_csv(whole_path) is None
        assert cut_path.read_bytes() == whole_path.read_bytes()


class TestStoppedWarning:
    """Writing a result that stopped logs one WARNING that names the reason."""

    def warnings(self, caplog):
        return [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_a_cut_result_logs_one_warning_naming_the_reason(self, tmp_path, caplog):
        with caplog.at_level(logging.DEBUG):
            exposition(max_matches=3).to_csv(tmp_path / "out.csv")
        [record] = self.warnings(caplog)
        assert "max_matches" in record.getMessage()
        assert record.name == "tilia_core.tql.result"

    def test_each_reason_is_named(self, tmp_path, caplog):
        cancel = threading.Event()
        cancel.set()
        cancelled = exposition(cancel=cancel)
        timed_out = exposition(time_limit=0)
        with caplog.at_level(logging.DEBUG):
            cancelled.to_csv(tmp_path / "a.csv")
            timed_out.to_csv(tmp_path / "b.csv")
        messages = [r.getMessage() for r in self.warnings(caplog)]
        assert len(messages) == 2
        assert "cancelled" in messages[0] and "time_limit" in messages[1]

    def test_a_complete_result_logs_nothing(self, tmp_path, caplog):
        result = exposition()
        with caplog.at_level(logging.DEBUG):
            result.to_csv(tmp_path / "out.csv")
        assert caplog.records == []

    def test_a_cut_statistics_table_logs_one_warning(self, tmp_path, caplog):
        table = exposition(max_matches=3).stats("counts")
        with caplog.at_level(logging.DEBUG):
            table.to_csv(tmp_path / "out.csv")
        [record] = self.warnings(caplog)
        assert "max_matches" in record.getMessage()
        assert record.name == "tilia_core.tql.stats"

    def test_a_complete_statistics_table_logs_nothing(self, tmp_path, caplog):
        table = exposition().stats("counts")
        with caplog.at_level(logging.DEBUG):
            table.to_csv(tmp_path / "out.csv")
        assert caplog.records == []

    def test_a_sql_table_cut_by_max_rows_logs_one_warning(self, tmp_path, caplog):
        index = fixture_index.build_index(FIXTURES["exposition"])
        table = tql.sql(index, "SELECT id FROM components", max_rows=2)
        with caplog.at_level(logging.DEBUG):
            assert table.to_csv(tmp_path / "out.csv") == "max_rows"
        [record] = self.warnings(caplog)
        assert "max_rows" in record.getMessage()


class TestDocstring:
    def test_result_says_what_stopped_holds(self):
        doc = " ".join(tql.Result.__doc__.split())
        for reason in ("max_matches", "time_limit", "cancelled"):
            assert reason in doc
        assert re.search(r"\bsome\b", doc)
        assert "not necessarily the first N" in doc

    def test_result_says_stats_and_to_csv_carry_the_mark(self):
        doc = " ".join(tql.Result.__doc__.split())
        assert "``stats`` and ``to_csv`` carry the mark" in doc

    def test_to_csv_says_what_it_returns_and_logs(self):
        doc = " ".join(tql.Result.to_csv.__doc__.split())
        assert "Returns ``stopped``" in doc
        assert "WARNING" in doc

    def test_stats_says_the_table_carries_the_mark(self):
        doc = " ".join(tql.Result.stats.__doc__.split())
        assert "its ``stopped`` is this result's ``stopped``" in doc
