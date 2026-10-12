"""Reading a CSV as TiLiA's importers read it, keeping each row's line in the file."""

from __future__ import annotations

import csv
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from tilia_core.importers._results import ImportFailed

# TiLiA's texts: its importers' (tilia/parsers/csv/) and tilia/ui/strings.py's.
EMPTY_FILE = "Can't import: file is empty."
UTF8_DECODE_FAILED = "'{}' is not a valid UTF-8 encoded {} file."


@dataclass(frozen=True)
class CsvRow:
    line: int  # the row's first line in the file, 1-based, the header being line 1
    # By column name, in NFC; a column the row is too short for is missing.
    values: dict[str, str]


def read_csv(path: str | os.PathLike[str]) -> tuple[list[str], list[CsvRow]]:
    """The header and the rows of a CSV in UTF-8, with or without a byte-order mark.

    A row with no cells is left out. Where a column name is repeated, the first
    column with it is read, as TiLiA's importers find columns. The whole file is
    read before anything is returned, so a file that fails changes nothing.

    Raises `ImportFailed` for an empty file, a file that isn't UTF-8, or a row
    the `csv` module can't read; `OSError` for a file that can't be opened.
    """
    path = Path(path)
    header: list[str] | None = None
    rows: list[CsvRow] = []
    with open(path, encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        line = 1
        try:
            for cells in reader:
                if header is None:
                    header = [_nfc(cell) for cell in cells]
                elif cells:
                    values: dict[str, str] = {}
                    for name, value in zip(header, cells, strict=False):
                        values.setdefault(name, _nfc(value))
                    rows.append(CsvRow(line=line, values=values))
                # A quoted field's line breaks count, so the next row starts here.
                line = reader.line_num + 1
        except UnicodeDecodeError:
            raise ImportFailed(path, UTF8_DECODE_FAILED.format(path, "CSV")) from None
        except csv.Error as error:
            raise ImportFailed(
                path, f"can't read, line {reader.line_num}: {error}"
            ) from None
    if header is None:
        raise ImportFailed(path, EMPTY_FILE)
    return header, rows


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)
