from pathlib import Path

import csv
from typing import Any, Optional, Callable

import tilia.errors


class TiliaCSVReader:
    def __init__(
        self,
        path: Path,
        file_kwargs: Optional[dict[str, Any]] = None,
        reader_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.path = path
        self.file_kwargs = file_kwargs or {}
        self.reader_kwargs = reader_kwargs or {}

    def __enter__(self):
        self.file = open(self.path, newline="", encoding="utf-8", **self.file_kwargs)
        return csv.reader(self.file, **self.reader_kwargs)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.file.close()


def display_column_not_found_error(column: str) -> None:
    tilia.errors.display(
        tilia.errors.CSV_IMPORT_FAILED,
        f"Column '{column}' not found on first row of .csv file.",
    )


def get_params_indices(params: list[str], headers: list[str]) -> dict[str, int]:
    """
    Returns a dictionary with parameters in 'params' as keys
    and their first index in 'headers'  as values.
    If the parameters is not found in 'headers',
    it is not included in the result.
    """

    result = {}

    for p in params:
        try:
            result[p] = headers.index(p)
        except ValueError:
            pass

    return result


AttributeData = tuple[str, Callable, int]
