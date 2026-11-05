import hashlib
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


# SHA-256 of examples.toml with LF line endings. The file is a copy of
# library-manager/tql-examples.toml in TimeLineAnnotator/project-management,
# TQL 0.2's example list (last changed there in dc5d024, which changed only its
# first line: no example's rows change from 0.1.1). Change the copy only
# together with the planning repo's, then this hash.
EXAMPLES_SHA256 = "f145d3bd38686eda3a4bce23aff0e88621ae1baaf8b52f36477576d6407993b0"

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
