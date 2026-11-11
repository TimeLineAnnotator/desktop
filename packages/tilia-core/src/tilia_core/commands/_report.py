"""What every `tilia` subcommand prints alike: its problems and notes, on standard
error, one per line, starting with the file and, where there is one, its line; its
output, which ends quietly when the reader stops reading; and its exit statuses."""

from __future__ import annotations

import errno
import io
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TextIO

from tilia_core.tla.errors import printable

if TYPE_CHECKING:
    import argparse

    from tilia_core.commands._script import ScriptLine
    from tilia_core.importers import RowProblem

# It did everything it should.
EXIT_OK = 0
# Something it should have done wasn't done.
EXIT_FAILED = 1
# It was used wrongly: a missing argument, a file or folder that doesn't exist, an
# unknown option.
EXIT_WRONG_USE = 2

_IN_A_FILE = "{}: {}"
_ON_A_LINE = "{}, line {}: {}"
_ROW = "{}, line {}"
_ROW_COLUMN = "{}, line {}, {}"
_NOTE = "note: {}"

# Control characters (C0, DEL and C1), which could add lines to the report or
# erase some, each as Python escapes it.
ESCAPES = {
    code: {"\t": "\\t", "\n": "\\n", "\r": "\\r"}.get(chr(code), f"\\x{code:02x}")
    for code in (*range(0x20), 0x7F, *range(0x80, 0xA0))
}


def shown(text: str) -> str:
    """`text` from a file or the system, a name, a reason or a version, with
    each control character escaped (`\\n`, `\\x1b`), so that it prints on one
    line and changes nothing else on the terminal."""
    return text.translate(ESCAPES)


def print_problem(file: str, message: str, *, line: int | None = None) -> None:
    """Print to standard error what's wrong with `file`, on one line, whatever a
    name or a value in it holds."""
    if line is None:
        text = _IN_A_FILE.format(file, message)
    else:
        text = _ON_A_LINE.format(file, line, message)
    print(printable(shown(text)), file=sys.stderr)


def wrong_use(parser: argparse.ArgumentParser, message: str) -> int:
    """Say what is wrong as argparse does, and give the status for it."""
    parser.print_usage(sys.stderr)
    print(f"{parser.prog}: error: {message}", file=sys.stderr)
    return EXIT_WRONG_USE


def folder_problem(path: str) -> str | None:
    """What is wrong with `path` as the folder to read, or None if nothing is."""
    if os.path.isdir(path):
        return None
    what = "not a folder" if os.path.exists(path) else "no such folder"
    return f"{what}: {shown(path)}"


def tolerate_unencodable(stream: TextIO) -> None:
    """Print a character the terminal's encoding lacks as its escape, rather
    than stop: a file name may hold any character. A lone surrogate, from a
    file name that isn't UTF-8, is printed as its escape too, as
    `errors.printable` writes it."""
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(errors="backslashreplace")


def print_out(text: str) -> None:
    """Print `text`. A reader that stops reading, as `head` does once it has
    its lines, ends the output there, without an error."""
    try:
        print(text)
        sys.stdout.flush()
    except OSError as error:
        if not _reader_gone(error):
            raise
        _end_output()


def print_bytes(data: bytes) -> None:
    """Write `data` to standard output as it is. A reader that stops reading
    ends the output there, without an error, as `print_out` does."""
    try:
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except OSError as error:
        if not _reader_gone(error):
            raise
        _end_output()


def _reader_gone(error: OSError) -> bool:
    """Whether writing failed because the other end of a pipe was closed:
    EPIPE, or EINVAL, as a write to a closed pipe can fail on Windows."""
    if isinstance(error, BrokenPipeError):
        return True
    return os.name == "nt" and error.errno == errno.EINVAL


def _end_output() -> None:
    """Point standard output at nothing: Python flushes it again as it exits."""
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError):
        pass


@dataclass(frozen=True, kw_only=True)
class Report:
    """A problem, which sets exit status 1, or a note, which doesn't, about a line
    of a script, and the row of a CSV when it's about one."""

    line: ScriptLine
    kind: Literal["problem", "note"]
    message: str
    row: RowProblem | None = None

    def print(self, script: str) -> None:
        """Print it to standard error, `script` being the name to call the script by."""
        message = self.message
        if self.row is not None:
            message = _IN_A_FILE.format(_row_named(self.row), message)
        if self.kind == "note":
            message = _NOTE.format(message)
        print_problem(script, message, line=self.line.number)


def _row_named(row: RowProblem) -> str:
    if row.column is None:
        return _ROW.format(row.path.name, row.line)
    return _ROW_COLUMN.format(row.path.name, row.line, row.column)
