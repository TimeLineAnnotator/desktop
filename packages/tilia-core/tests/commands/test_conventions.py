"""What every `tilia` subcommand prints alike (contracts/conventions.md): a problem's
and a note's form, character for character from contracts/run.md's examples, on
standard error and nowhere else; and the exit statuses."""

from pathlib import Path

import pytest

from tilia_core.commands._report import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_WRONG_USE,
    Report,
    print_problem,
)
from tilia_core.commands._script import ScriptLine
from tilia_core.importers import RowProblem

SCRIPT = "import-script.txt"
SYMBOL = "V/bVI is not a valid symbol."


def line(number):
    return ScriptLine(number=number, text="any", args=["any"])


def row(*, path="chords.csv", number=212, column="symbol", skipped=True):
    return RowProblem(
        path=Path(path),
        line=number,
        column=column,
        message=SYMBOL,
        skipped=skipped,
    )


@pytest.mark.parametrize(
    "number,message,printed",
    [
        (
            9,
            "chords.csv: Column 'measure' not found on first row of .csv file.",
            "import-script.txt, line 9: chords.csv:"
            " Column 'measure' not found on first row of .csv file.",
        ),
        (
            9,
            "'/data/K279-1/chords.csv' is not a valid UTF-8 encoded CSV file.",
            "import-script.txt, line 9:"
            " '/data/K279-1/chords.csv' is not a valid UTF-8 encoded CSV file.",
        ),
        (
            4,
            '"timeline" isn\'t a command: use "timelines"',
            'import-script.txt, line 4: "timeline" isn\'t a command: use "timelines"',
        ),
        (
            8,
            '"-f" isn\'t an option of timelines import beat: use "--file"',
            'import-script.txt, line 8: "-f" isn\'t an option of timelines import beat:'
            ' use "--file"',
        ),
        (
            11,
            "a quote isn't closed",
            "import-script.txt, line 11: a quote isn't closed",
        ),
        (
            12,
            "K279-1.tla already exists: add --overwrite, or run with --yes",
            "import-script.txt, line 12:"
            " K279-1.tla already exists: add --overwrite, or run with --yes",
        ),
    ],
)
def test_a_problem_names_the_script_and_its_line(capsys, number, message, printed):
    Report(line=line(number), kind="problem", message=message).print(SCRIPT)

    captured = capsys.readouterr()
    assert captured.err == printed + "\n"
    assert captured.out == ""


def test_a_note_says_it_is_one(capsys):
    message = "phrases.csv: formal_type and formal_function are no longer stored"

    Report(line=line(10), kind="note", message=message).print(SCRIPT)

    captured = capsys.readouterr()
    assert captured.err == (
        "import-script.txt, line 10: note:"
        " phrases.csv: formal_type and formal_function are no longer stored\n"
    )
    assert captured.out == ""


def test_a_row_names_its_csv_its_line_and_its_column(capsys):
    report = Report(line=line(9), kind="problem", message=SYMBOL, row=row())

    report.print(SCRIPT)

    captured = capsys.readouterr()
    assert captured.err == (
        "import-script.txt, line 9:"
        " chords.csv, line 212, symbol: V/bVI is not a valid symbol.\n"
    )
    assert captured.out == ""


def test_a_row_names_its_csv_by_its_name_not_its_folders(capsys):
    problem = row(path="some/folder/chords.csv")

    Report(line=line(9), kind="problem", message=SYMBOL, row=problem).print(SCRIPT)

    assert capsys.readouterr().err.startswith(
        "import-script.txt, line 9: chords.csv, line 212, symbol: "
    )


def test_a_row_without_a_column_leaves_it_out(capsys):
    problem = row(column=None)

    Report(line=line(9), kind="problem", message=SYMBOL, row=problem).print(SCRIPT)

    assert capsys.readouterr().err == (
        "import-script.txt, line 9: chords.csv, line 212: V/bVI is not a valid symbol.\n"
    )


def test_a_row_imported_with_a_fallback_is_a_note(capsys):
    problem = row(skipped=False)

    Report(line=line(9), kind="note", message=SYMBOL, row=problem).print(SCRIPT)

    assert capsys.readouterr().err == (
        "import-script.txt, line 9: note:"
        " chords.csv, line 212, symbol: V/bVI is not a valid symbol.\n"
    )


@pytest.mark.parametrize(
    "line_number,printed",
    [
        (14, "piece.tla, line 14: not valid JSON (…)\n"),
        (None, "piece.tla: not valid JSON (…)\n"),
    ],
)
def test_any_subcommand_starts_a_problem_with_the_file(capsys, line_number, printed):
    print_problem("piece.tla", "not valid JSON (…)", line=line_number)

    captured = capsys.readouterr()
    assert captured.err == printed
    assert captured.out == ""


@pytest.mark.parametrize(
    "text,printed",
    [
        ("a\nb", "a\\nb"),
        ("a\r\nb", "a\\r\\nb"),
        ("a\x1b[2Jb", "a\\x1b[2Jb"),
        ("a\x00b", "a\\x00b"),
        ("a\x9bb", "a\\x9bb"),
        ("caf\udce9", "caf\\udce9"),
    ],
)
def test_a_report_stays_on_its_line_and_can_be_encoded(capsys, text, printed):
    # A name or a value from a file: a CSV's cell can hold a line break, a file
    # name on Linux a lone surrogate, and a path in a script a NUL.
    problem = RowProblem(
        path=Path(f"{text}.csv"),
        line=1,
        column=text,
        message=text,
        skipped=True,
    )

    Report(line=line(9), kind="problem", message=text, row=problem).print(text)

    err = capsys.readouterr().err
    assert err == f"{printed}, line 9: {printed}.csv, line 1, {printed}: {printed}\n"
    err.encode("utf-8")


def test_the_exit_statuses():
    assert (EXIT_OK, EXIT_FAILED, EXIT_WRONG_USE) == (0, 1, 2)
