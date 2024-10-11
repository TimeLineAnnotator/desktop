from pathlib import Path


def ensure_tla_extension(path: Path) -> Path:
    if not path.suffix == ".tla":
        path = path.with_name(f"{path.name}.tla")
    return path
