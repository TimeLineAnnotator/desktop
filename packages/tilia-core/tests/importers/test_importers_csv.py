import csv

import pytest

from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed


def write(tmp_path, data: bytes):
    path = tmp_path / "data.csv"
    path.write_bytes(data)
    return path


def lines_and_values(rows):
    return [(row.line, row.values) for row in rows]


def test_header_and_rows_by_column_name(tmp_path):
    path = write(tmp_path, b"time,label\n1,a\n2,b\n")

    header, rows = read_csv(path)

    assert header == ["time", "label"]
    assert rows == [
        CsvRow(line=2, values={"time": "1", "label": "a"}),
        CsvRow(line=3, values={"time": "2", "label": "b"}),
    ]


def test_takes_a_path_as_text(tmp_path):
    path = write(tmp_path, b"time\n1\n")

    assert read_csv(str(path)) == (["time"], [CsvRow(line=2, values={"time": "1"})])


def test_a_byte_order_mark_before_time_is_read_as_time(tmp_path):
    path = write(tmp_path, b"\xef\xbb\xbftime,label\n1,a\n")

    header, rows = read_csv(path)

    assert header == ["time", "label"]
    assert rows[0].values == {"time": "1", "label": "a"}


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
def test_any_line_ending(tmp_path, ending):
    path = write(tmp_path, ending.join(["time,label", "1,a", "2,b", ""]).encode())

    header, rows = read_csv(path)

    assert header == ["time", "label"]
    assert lines_and_values(rows) == [
        (2, {"time": "1", "label": "a"}),
        (3, {"time": "2", "label": "b"}),
    ]


def test_no_line_ending_after_the_last_row(tmp_path):
    path = write(tmp_path, b"time\r\n1\r\n2")

    assert lines_and_values(read_csv(path)[1]) == [
        (2, {"time": "1"}),
        (3, {"time": "2"}),
    ]


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_a_quoted_line_break_keeps_the_next_rows_line(tmp_path, ending):
    text = ending.join(["time,label", '1,"two', 'lines"', "2,b", ""])
    path = write(tmp_path, text.encode())

    _, rows = read_csv(path)

    assert [row.line for row in rows] == [2, 4]
    assert rows[0].values["label"] == f"two{ending}lines"


def test_a_row_starts_on_the_line_after_a_quoted_line_break(tmp_path):
    path = write(tmp_path, b'time,label\n1,"a\nb\nc"\n\n2,"d\ne"\n3,f\n')

    _, rows = read_csv(path)

    assert [row.line for row in rows] == [2, 6, 8]


def test_text_is_put_in_nfc(tmp_path):
    # "é" as an "e" and a combining acute accent, as macOS may type it.
    path = write(tmp_path, "time,label\n1,é\n".encode())

    _, rows = read_csv(path)

    assert rows[0].values["label"] == "é"


def test_column_names_are_put_in_nfc(tmp_path):
    path = write(tmp_path, "time,café\n1,a\n".encode())

    header, rows = read_csv(path)

    assert header == ["time", "café"]
    assert rows[0].values == {"time": "1", "café": "a"}


def test_empty_rows_are_left_out_without_a_report(tmp_path):
    path = write(tmp_path, b"time\n\n1\n\n\n2\n")

    _, rows = read_csv(path)

    assert lines_and_values(rows) == [(3, {"time": "1"}), (6, {"time": "2"})]


def test_a_row_of_empty_cells_is_kept(tmp_path):
    # TiLiA's importers skip only rows with no cells.
    path = write(tmp_path, b"time,label\n,\n")

    assert read_csv(path)[1] == [CsvRow(line=2, values={"time": "", "label": ""})]


def test_a_column_the_row_is_too_short_for_is_missing(tmp_path):
    path = write(tmp_path, b"time,label,comments\n1,a\n")

    assert read_csv(path)[1][0].values == {"time": "1", "label": "a"}


def test_cells_beyond_the_header_are_left_out(tmp_path):
    path = write(tmp_path, b"time\n1,extra\n")

    assert read_csv(path)[1][0].values == {"time": "1"}


def test_a_repeated_column_name_takes_the_first_column(tmp_path):
    # As TiLiA's importers find a column, with `headers.index`.
    path = write(tmp_path, b"time,label,label\n1,a,b\n")

    header, rows = read_csv(path)

    assert header == ["time", "label", "label"]
    assert rows[0].values == {"time": "1", "label": "a"}


def test_a_header_with_no_rows(tmp_path):
    path = write(tmp_path, b"time,label\n")

    assert read_csv(path) == (["time", "label"], [])


def test_a_blank_first_line_is_an_empty_header(tmp_path):
    # As in TiLiA, whose importers then find no required column.
    path = write(tmp_path, b"\ntime\n1\n")

    assert read_csv(path) == (
        [],
        [CsvRow(line=2, values={}), CsvRow(line=3, values={})],
    )


@pytest.mark.parametrize(
    "data", [b"", b"\xef\xbb\xbf"], ids=["no bytes", "a byte-order mark only"]
)
def test_an_empty_file_fails(tmp_path, data):
    path = write(tmp_path, data)

    with pytest.raises(ImportFailed) as info:
        read_csv(path)

    assert info.value.path == path
    assert info.value.message == "Can't import: file is empty."
    assert str(info.value) == "data.csv: Can't import: file is empty."


def test_a_cp1252_file_fails_with_tilias_text(tmp_path):
    path = write(tmp_path, "time,label\n1,café\n".encode("cp1252"))

    with pytest.raises(ImportFailed) as info:
        read_csv(path)

    assert info.value.path == path
    assert info.value.message == f"'{path}' is not a valid UTF-8 encoded CSV file."


def test_a_byte_that_isnt_utf8_at_the_end_fails_the_whole_file(tmp_path):
    # The whole file is read before anything is returned.
    good = "".join(f"{time},é\n" for time in range(5000)).encode()
    path = write(tmp_path, b"time,label\n" + good + "9999,é\n".encode("cp1252"))

    with pytest.raises(ImportFailed):
        read_csv(path)


def test_a_row_the_csv_module_refuses_fails_with_its_line(tmp_path):
    path = write(tmp_path, b"time,label\n1,a\n2," + b"x" * 20 + b"\n")
    limit = csv.field_size_limit(10)
    try:
        with pytest.raises(ImportFailed) as info:
            read_csv(path)
    finally:
        csv.field_size_limit(limit)

    assert info.value.path == path
    assert info.value.message == (
        "can't read, line 3: field larger than field limit (10)"
    )


def test_a_missing_file_raises_os_error(tmp_path):
    # The caller reports it, as for any file it can't open.
    with pytest.raises(FileNotFoundError):
        read_csv(tmp_path / "missing.csv")
