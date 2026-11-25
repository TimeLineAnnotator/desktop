import os
from pathlib import Path


def ensure_tla_extension(path: Path) -> Path:
    if not path.suffix == ".tla":
        path = path.with_name(f"{path.name}.tla")
    return path


def as_given(path: Path) -> str:
    """`path` absolute, as a script's `open` and `save` take it: a link to a folder
    isn't followed, nor a short name made long, so that the media `load-media` takes
    as given is stored relative to the folder `path` gives (FR-095).

    Only where that would name another folder than the system reads, when macOS and
    Linux go up from a link's target at `..`, are links followed."""
    absolute = os.path.abspath(path)
    by_name = os.path.dirname(absolute)
    if os.path.isdir(path.parent) and not (
        os.path.isdir(by_name) and os.path.samefile(path.parent, by_name)
    ):
        return str(path.resolve())
    return absolute
