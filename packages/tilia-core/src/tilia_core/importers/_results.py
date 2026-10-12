"""What an import gives: the components it created, each row it skipped and why, or the one failure."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class RowProblem:
    """Why one row wasn't imported, or was imported with a fallback."""

    path: Path  # the CSV
    line: int  # the row's line in the file
    column: str | None  # the column at fault, when there is one
    message: str  # TiLiA's wording, where TiLiA has one
    skipped: bool  # True: the row wasn't imported; False: imported with a fallback


@dataclass(kw_only=True)
class ImportResult:
    """What an import that ran gives back."""

    created: list[str] = field(default_factory=list)  # the new ids, in row order
    rows: int = 0  # rows read, empty rows left out
    problems: list[RowProblem] = field(default_factory=list)  # in row order
    notes: list[str] = field(default_factory=list)  # about the whole import

    @property
    def skipped(self) -> list[RowProblem]:
        """The problems whose row wasn't imported."""
        return [problem for problem in self.problems if problem.skipped]


class ImportFailed(Exception):
    """The import didn't run, and changed nothing."""

    def __init__(self, path: Path | None, message: str) -> None:
        super().__init__(path, message)
        self.path = path  # the CSV or JSON, when there is one
        self.message = message

    def __str__(self) -> str:
        if self.path is None:
            return self.message
        return f"{self.path.name}: {self.message}"
