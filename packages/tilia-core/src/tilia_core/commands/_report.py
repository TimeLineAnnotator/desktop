"""What every `tilia` subcommand prints alike: its problems and notes, on standard
error, one per line, starting with the file and, where there is one, its line; and
its exit statuses."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from tilia_core.tla.errors import printable

if TYPE_CHECKING:
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
