from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


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
    with open(Path(__file__).with_name("examples.toml"), "rb") as f:
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
