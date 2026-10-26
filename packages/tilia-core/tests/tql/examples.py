import hashlib
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


# SHA-256 of examples.toml with LF line endings. The file is a copy of
# library-manager/tql-examples.toml in TimeLineAnnotator/project-management,
# TQL 0.1.0's example list (#102; last changed there in 1949ac5, #104), with
# example 28's rows and why changed for Q36 (a chord on a unit's end counts for
# it), which the planning repo's copy does not have yet. Change the copy only
# together with the planning repo's, then this hash.
EXAMPLES_SHA256 = "25dfbf835dbd95c89cf9c25901dbc97d45f156f5a9f42130d7b7a3474bb78194"

PATH = Path(__file__).with_name("examples.toml")


def sha256() -> str:
    """The SHA-256 of examples.toml, read with LF line endings (a Windows
    checkout may have CRLF)."""
    return hashlib.sha256(PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@dataclass(frozen=True)
class Example:
    n: int
    query: str
    fixture: str
    rows: list[str]
    writes: list[str]
    plan: str
    why: str
    core_only: bool


def load() -> dict:
    with open(PATH, "rb") as f:
        data = tomllib.load(f)
    examples = [
        Example(
            n=n,
            query=e["query"],
            fixture=e["fixture"],
            rows=e["rows"],
            writes=e.get("writes", []),
            plan=e["plan"],
            why=e.get("why", ""),
            core_only=e.get("core_only", False),
        )
        for n, e in enumerate(data["example"], start=1)
    ]
    return {"fixtures": data["fixtures"], "examples": examples}
