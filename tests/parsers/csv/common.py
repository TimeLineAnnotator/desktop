from pathlib import Path


def assert_in_errors(string: str, errors: list[str]):
    all_errors = "".join(errors)
    assert string in all_errors


def write_csv(tmp_path: Path, content: str) -> Path:
    # Prefer this over patching builtins.open: Qt can open a real file while
    # the mock is live and crash (see commit message for the full story).
    path = tmp_path / "data.csv"
    path.write_text(content)
    return path
