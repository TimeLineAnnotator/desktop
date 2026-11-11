"""`tilia query`: run a TQL query on a folder of TiLiA files.

`tilia query FOLDER QUERY` opens FOLDER as a corpus and prints the query's
matches as a table; `--file PATH` reads the query from a file. A thin layer
over `open_corpus(path)` and `tql.run` (FR-047): the same matches, warnings and
`stopped`. Rows go to standard output; problems, warnings and the "stopped"
line to standard error.

It exits 0 when it did everything it should; 1 when the run stopped (a limit,
or Ctrl+C) or files were left out as unreadable; 2 when it was used wrongly,
the query included (`tql.TQLError`).
"""

from __future__ import annotations

import argparse
import signal
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from types import FrameType
from typing import Any

from tilia_core import corpus, tql
from tilia_core.commands._report import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_WRONG_USE,
    folder_problem,
    print_bytes,
    print_out,
    print_problem,
    shown,
    tolerate_unencodable,
    wrong_use,
)
from tilia_core.tql.stats import NAMES as STATS

PROG = "tilia query"

# What the table leaves out of a result's columns: the document id, the
# units' ids, a chord's two names (`label` shows the one `--labels` picks) and
# each numbered unit's own columns. The CSV has every column.
_NOT_IN_THE_TABLE = frozenset({"file", "ids", "symbol", "roman"})
_TIME_COLUMNS = frozenset({"start", "end"})
_WHY_STOPPED = {
    "max_matches": "--max-matches",
    "time_limit": "--time-limit",
    "cancelled": "cancelled",
}
_STANDARD_OUTPUT = "-"


def main(argv: list[str] | None = None) -> int:
    tolerate_unencodable(sys.stdout)
    tolerate_unencodable(sys.stderr)
    parser = _parser()
    try:
        # Intermixed: Python 3.12's parse_args takes no option between FOLDER
        # and QUERY, as their nargs="?" consumes both before the option.
        arguments = parser.parse_intermixed_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:  # --help, or wrong use, which argparse printed
        return stop.code if isinstance(stop.code, int) else EXIT_WRONG_USE
    try:
        return _query(parser, arguments)
    except KeyboardInterrupt:  # before the run, or a second Ctrl+C during it
        print(f"{PROG}: cancelled", file=sys.stderr)
        return EXIT_FAILED


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        usage=(
            "%(prog)s [options] FOLDER QUERY\n"
            "       %(prog)s [options] --file PATH FOLDER\n"
            "       %(prog)s --explain QUERY"
        ),
        description=(
            "Run a TQL query on the TiLiA files below FOLDER and print its"
            " matches as a table. Rows go to standard output; problems,"
            " warnings and the stopped line to standard error."
        ),
        epilog=(
            "Exit status: 0 when everything was done; 1 when the run stopped"
            " or files were left out as unreadable; 2 when the command was"
            " used wrongly or the query is malformed."
        ),
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "first",
        nargs="?",
        metavar="FOLDER",
        help="every .tla file below it is read, hidden files and folders left out",
    )
    parser.add_argument(
        "second",
        nargs="?",
        metavar="QUERY",
        help="the query, as one argument (quote it)",
    )
    parser.add_argument(
        "--file", metavar="PATH", help="read the query from this file (UTF-8)"
    )
    parser.add_argument(
        "--csv",
        nargs="?",
        const=_STANDARD_OUTPUT,
        metavar="PATH",
        help=(
            "write CSV instead of the table: to PATH, or to standard output"
            " without one. Give it after FOLDER and QUERY, or as --csv=PATH"
        ),
    )
    shown_instead = parser.add_mutually_exclusive_group()
    shown_instead.add_argument(
        "--stats",
        choices=STATS,
        metavar="NAME",
        help=f"print a statistics table instead of the rows: {', '.join(STATS)}",
    )
    shown_instead.add_argument(
        "--sql",
        action="store_true",
        help="print the SQL the run used instead of the rows",
    )
    shown_instead.add_argument(
        "--explain",
        action="store_true",
        help="print what the query means, and run nothing (no FOLDER needed)",
    )
    parser.add_argument(
        "--by",
        metavar="KEY[,KEY]",
        help="with --stats: the key to group by (label unless given), or two",
    )
    parser.add_argument(
        "--fold-subtypes",
        action="store_true",
        help="with --stats: count a subtype category as its supertype",
    )
    parser.add_argument(
        "--max-matches",
        type=_positive_int,
        metavar="N",
        help="stop once N matches are found (some N, not the first N); no limit unless given",
    )
    parser.add_argument(
        "--time-limit",
        type=_positive_float,
        metavar="SECONDS",
        help="stop after SECONDS; no limit unless given",
    )
    parser.add_argument(
        "--labels",
        choices=("letter", "roman"),
        default="letter",
        help="a chord's label: its symbol (letter, the default) or its Roman numeral",
    )
    parser.add_argument("--help", action="help", help="show this help and exit")
    return parser


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more: {text!r}")
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be more than 0: {text!r}")
    return value


def _misused_options(arguments: argparse.Namespace) -> str | None:
    if arguments.stats is None:
        if arguments.by is not None:
            return "--by goes with --stats"
        if arguments.fold_subtypes:
            return "--fold-subtypes goes with --stats"
    if arguments.csv is not None and (arguments.sql or arguments.explain):
        return "--csv goes with the rows or --stats, not with --sql or --explain"
    return None


def _query(parser: argparse.ArgumentParser, arguments: argparse.Namespace) -> int:
    misused = _misused_options(arguments)
    if misused is not None:
        return wrong_use(parser, misused)
    folder: str | None = arguments.first
    text: str | None = arguments.second
    source: str | None = arguments.file
    if source is not None:
        if text is not None:
            return wrong_use(parser, "give the query as QUERY or with --file, not both")
        try:
            text = Path(source).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return wrong_use(parser, f"no such file: {shown(source)}")
        except (OSError, UnicodeDecodeError) as error:
            why = getattr(error, "strerror", None) or str(error)
            return wrong_use(parser, f"can't read {shown(source)}: {why}")
    elif text is None:  # one argument: the query, which only --explain takes alone
        if folder is None or not arguments.explain:
            return wrong_use(parser, "FOLDER and QUERY are needed")
        folder, text = None, folder

    if arguments.explain:  # runs nothing, so it reads no folder
        folder = None
    elif folder is None:
        return wrong_use(parser, "FOLDER is needed")
    elif (problem := folder_problem(folder)) is not None:
        return wrong_use(parser, problem)
    try:
        parsed = tql.parse(text)
    except tql.TQLError as error:
        return _query_error(source, text, error)
    if folder is None:  # --explain
        print_out(tql.explain(parsed))
        return EXIT_OK

    try:
        # Read once: a rescan before the run would read every file again.
        opened = corpus.open_corpus(folder, rescan_before_reads=False)
    except NotImplementedError as error:  # no .tla reader in this version
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_FAILED
    except OSError as error:
        why = error.strerror or str(error)
        print(f"{PROG}: can't read {shown(folder)}: {why}", file=sys.stderr)
        return EXIT_FAILED
    with opened:
        unreadable = opened.open_report.unreadable
        for path, _line, reason in unreadable:
            # The reason says the line, where there is one.
            print_problem(path, reason)
        try:
            result = _run(opened, parsed, arguments)
        except tql.TQLError as error:  # a lane or a field the corpus lacks
            return _query_error(source, text, error)
        try:
            status = _print_result(result, arguments)
        except ValueError as error:  # a statistics name or key it doesn't know
            return wrong_use(parser, str(error))
    for warning in result.warnings:
        print(f"warning: {shown(warning)}", file=sys.stderr)
    if result.stopped is not None:
        n = len(result.rows)
        matches = "match" if n == 1 else "matches"
        why = _WHY_STOPPED.get(result.stopped, result.stopped)
        print(f"stopped: some {n} {matches} ({why})", file=sys.stderr)
    if status == EXIT_OK and (unreadable or result.stopped is not None):
        return EXIT_FAILED
    return status


def _query_error(source: str | None, text: str, error: tql.TQLError) -> int:
    """Print `tql.format_error`'s text, after the query file and the line of
    the culprit when the query came from a file."""
    message = tql.format_error(text, error)
    if source is not None:
        where = shown(source)
        if error.pos is not None:
            where += f", line {text.count(chr(10), 0, error.pos) + 1}"
        message = f"{where}: {message}"
    print(message, file=sys.stderr)
    return EXIT_WRONG_USE


def _run(
    index: corpus.Corpus, query: tql.Query, arguments: argparse.Namespace
) -> tql.Result:
    """`tql.run`, with Ctrl+C setting its `cancel`: the run ends at its next
    check and gives what it found. A second Ctrl+C interrupts at once."""
    cancel = threading.Event()

    def interrupted(signum: int, frame: FrameType | None) -> None:
        cancel.set()
        signal.signal(signal.SIGINT, signal.default_int_handler)

    try:
        previous = signal.signal(signal.SIGINT, interrupted)
    except ValueError:  # not the main thread: Ctrl+C isn't ours to take
        previous = None
    try:
        return tql.run(
            index,
            query,
            max_matches=arguments.max_matches,
            time_limit=arguments.time_limit,
            cancel=cancel,
        )
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def _print_result(result: tql.Result, arguments: argparse.Namespace) -> int:
    """Print the rows, a statistics table or the SQL, and give the status."""
    if arguments.sql:
        print_out(result.sql)
        return EXIT_OK
    if arguments.stats is not None:
        by = _keys(arguments.by)
        stats = result.stats(arguments.stats, by, fold_subtypes=arguments.fold_subtypes)
        if arguments.csv is not None:
            return _write_csv(stats.to_csv, arguments.csv)
        _print_table(stats.columns, stats.rows)
        return EXIT_OK
    rows = _labelled(result.rows, arguments.labels)
    if arguments.csv is not None:
        return _write_csv(replace(result, rows=rows).to_csv, arguments.csv)
    columns = [
        c
        for c in result.columns
        if c not in _NOT_IN_THE_TABLE and not c.startswith("$")
    ]
    _print_table(columns, [[row.get(c) for c in columns] for row in rows])
    return EXIT_OK


def _keys(by: str | None) -> list[str] | None:
    """`--by`'s keys: `Result.stats` takes one key alone or in a list alike."""
    return None if by is None else [key.strip() for key in by.split(",")]


def _labelled(rows: list[dict[str, Any]], labels: str) -> list[dict[str, Any]]:
    """`rows` with a chord's `label` its Roman numeral when `labels` is
    "roman"; its symbol, as `tql.run` gives it, otherwise."""
    if labels != "roman":
        return rows
    return [
        {**row, "label": row["roman"]} if row.get("roman") is not None else row
        for row in rows
    ]


def _print_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """An aligned table: a line of column names, then a line per row, each
    column as wide as its widest cell, two spaces between columns."""
    lines = [[shown(c) for c in columns]]
    lines += [
        [_cell(c, value) for c, value in zip(columns, row, strict=True)] for row in rows
    ]
    widths = [max(len(line[i]) for line in lines) for i in range(len(columns))]
    print_out(
        "\n".join(
            "  ".join(
                text.ljust(w) for text, w in zip(line, widths, strict=True)
            ).rstrip()
            for line in lines
        )
    )


def _cell(column: str, value: Any) -> str:
    """A value as the table prints it: as in the CSV, times in seconds with
    three decimals and None empty, on one line."""
    if value is None:
        return ""
    if column in _TIME_COLUMNS and isinstance(value, (int, float)):
        return f"{value:.3f}"
    return shown(str(value))


def _write_csv(to_csv: Callable[[str | Path], str | None], path: str) -> int:
    """Write the CSV `to_csv` writes to `path`, or its bytes to standard
    output when `path` is "-"."""
    if path != _STANDARD_OUTPUT:
        try:
            to_csv(path)
        except OSError as error:
            why = error.strerror or str(error)
            print_problem(path, f"can't write: {why}")
            return EXIT_FAILED
        return EXIT_OK
    with tempfile.TemporaryDirectory() as folder:
        written = Path(folder, "result.csv")
        to_csv(written)
        print_bytes(written.read_bytes())
    return EXIT_OK
