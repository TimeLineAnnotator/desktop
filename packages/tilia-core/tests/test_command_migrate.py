"""`tilia migrate`, through the `tilia` command: the report of
contracts/command.md, `--apply`, `--help`, and the exit statuses."""

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.commands import migrate as migrate_command
from tilia_core.tla import folder as folder_module

TESTS = Path(__file__).parent / "tla"
OLD = TESTS / "old"
BROKEN = TESTS / "broken"
GOLDEN = TESTS / "golden"
FORMAT = tla.FORMAT_VERSION

ADVICE = (
    "Nothing was written. The migration rewrites every file it lists. Keep the\n"
    "originals first: commit them if the folder is in git, or copy the folder.\n"
)


def place(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, Path):
        shutil.copyfile(source, path)
    else:
        path.write_bytes(source)


def with_a_marker_in_a_hierarchy():
    """TiLiA 0.7.0's test file, with a marker among its hierarchies: the
    migrated file breaks a rule, which doesn't stop it being migrated."""
    old = json.loads((OLD / "0.7.0.tla").read_text(encoding="utf-8"))
    old["timelines"]["1"]["components"]["999"] = {
        "kind": "MARKER",
        "time": 1.0,
        "label": "",
        "color": "#999999",
        "comments": "",
    }
    return json.dumps(old).encode()


@pytest.fixture
def sqx(tmp_path):
    """A folder like contracts/command.md's: old files of three versions, two
    of them copies of one file, a current file, an unreadable one in a
    subfolder and one of a newer format."""
    root = tmp_path / "sqx"
    place(root / "broken" / "sqx_17.tla", BROKEN / "not-json.tla")
    place(root / "current.tla", GOLDEN / "every-kind.tla")
    place(root / "sqx_03.tla", OLD / "0.6.0-s4-10.tla")
    place(root / "sqx_03 copy.tla", OLD / "0.6.0-s4-10.tla")
    place(root / "sqx_08.tla", OLD / "0.7.0.tla")
    place(root / "sqx_21.tla", with_a_marker_in_a_hierarchy())
    place(root / "sqx_30.tla", OLD / "0.0.96.tla")
    place(root / "sqx_40.tla", BROKEN / "newer-format.tla")
    return root


@pytest.fixture
def clean(tmp_path):
    """Old files, a current one and one of a newer format."""
    root = tmp_path / "clean"
    place(root / "a.tla", OLD / "0.7.0.tla")
    place(root / "current.tla", GOLDEN / "every-kind.tla")
    place(root / "newer.tla", BROKEN / "newer-format.tla")
    place(root / "sub" / "b.tla", OLD / "0.5.15.tla")
    return root


def tilia(*arguments, cwd, utf8=True):
    """Run the installed `tilia` command, as a user would."""
    script = shutil.which("tilia", path=sysconfig.get_path("scripts"))
    assert script is not None
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONIOENCODING", "PYTHONUTF8")
    }
    if utf8:
        env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [script, *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8" if utf8 else None,
        timeout=120,
    )


def snapshot(top):
    files = {}
    for folder, _, names in os.walk(top):
        for name in names:
            path = Path(folder, name)
            files[path.relative_to(top).as_posix()] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return files


SQX_FILES = """\
Already in the new format: 1 file
Left alone: 2 files
  broken/sqx_17.tla       can't read (line 6): not valid JSON (Expecting ',' delimiter)
  sqx_40.tla              written by a newer TiLiA (format 2.0.0)
Share a document id (copies): sqx_03 copy.tla, sqx_03.tla
Changes the migration makes:
  sqx_03 copy.tla         dropped 5 formal_type and formal_function values
  sqx_03.tla              dropped 5 formal_type and formal_function values
  sqx_08.tla              dropped 2 formal_type and formal_function values; dropped 3 amplitude bars
  sqx_21.tla              dropped 2 formal_type and formal_function values; dropped 3 amplitude bars
                          the timeline "Formal analysis" holds a component of kind "MARKER", which a timeline of kind "Hierarchy" doesn't have: it is kept as it is
  sqx_30.tla              dropped 2 formal_type and formal_function values
"""
SQX_VERSIONS = """\
  from 0.0.96: 1 file
  from 0.6.0: 2 files
  from 0.7.0: 2 files
"""


def test_without_apply_it_lists_what_would_change_and_writes_nothing(sqx):
    before = snapshot(sqx.parent)

    result = tilia("migrate", "sqx", cwd=sqx.parent)

    assert result.stderr == ""
    assert result.stdout == (
        f"Would migrate 5 files to format {FORMAT}:\n"
        + SQX_VERSIONS
        + SQX_FILES
        + "\n"
        + ADVICE
        + "Then run: tilia migrate sqx --apply\n"
    )
    assert result.returncode == 1  # a file it should migrate can't be read
    assert snapshot(sqx.parent) == before


def test_with_apply_it_migrates_and_says_what_it_wrote(sqx):
    result = tilia("migrate", "sqx", "--apply", cwd=sqx.parent)

    assert result.stderr == ""
    assert result.stdout == (
        f"Migrated 5 files to format {FORMAT}:\n"
        + SQX_VERSIONS
        + SQX_FILES
        + "\n"
        + "Wrote 5 files.\n"
    )
    assert result.returncode == 1
    for name in ("sqx_03.tla", "sqx_03 copy.tla", "sqx_08.tla", "sqx_21.tla"):
        assert tla.read(sqx / name).format_version == FORMAT


def test_a_second_apply_writes_nothing(sqx):
    tilia("migrate", "sqx", "--apply", cwd=sqx.parent)
    before = snapshot(sqx.parent)

    result = tilia("migrate", "sqx", "--apply", cwd=sqx.parent)

    assert result.stdout == (
        f"Migrated 0 files to format {FORMAT}.\n"
        "Already in the new format: 6 files\n"
        "Left alone: 2 files\n"
        "  broken/sqx_17.tla       can't read (line 6): not valid JSON"
        " (Expecting ',' delimiter)\n"
        "  sqx_40.tla              written by a newer TiLiA (format 2.0.0)\n"
        "Share a document id (copies): sqx_03 copy.tla, sqx_03.tla\n"
        "\n"
        "Nothing was written.\n"
    )
    assert snapshot(sqx.parent) == before


def test_exit_status_0_when_every_old_file_migrates(clean):
    listed = tilia("migrate", "clean", cwd=clean.parent)
    applied = tilia("migrate", "clean", "--apply", cwd=clean.parent)
    again = tilia("migrate", "clean", "--apply", cwd=clean.parent)

    assert listed.returncode == 0, listed.stderr
    assert applied.returncode == 0, applied.stderr
    assert again.returncode == 0, again.stderr
    assert "Left alone: 1 file\n" in again.stdout  # the newer one
    assert again.stdout.endswith("\nNothing was written.\n")


def test_a_listing_with_nothing_to_migrate_only_says_nothing_was_written(tmp_path):
    place(tmp_path / "current" / "current.tla", GOLDEN / "every-kind.tla")

    result = tilia("migrate", "current", cwd=tmp_path)

    assert result.stdout == (
        f"Would migrate 0 files to format {FORMAT}.\n"
        "Already in the new format: 1 file\n"
        "Left alone: 0 files\n"
        "\n"
        "Nothing was written.\n"
    )
    assert result.returncode == 0


def test_a_long_path_widens_the_column(tmp_path):
    long = "a folder with a long name/and a long file name.tla"
    place(tmp_path / "corpus" / long, BROKEN / "newer-format.tla")
    place(tmp_path / "corpus" / "short.tla", BROKEN / "newer-format.tla")

    result = tilia("migrate", "corpus", cwd=tmp_path)

    assert (
        f"  {long}  written by a newer TiLiA (format 2.0.0)\n"
        f"  short.tla{' ' * (len(long) - 7)}written by a newer TiLiA (format 2.0.0)\n"
    ) in result.stdout


def test_the_folder_to_run_again_is_quoted_for_the_shell(tmp_path):
    place(tmp_path / "my corpus" / "a.tla", OLD / "0.7.0.tla")

    result = tilia("migrate", "my corpus", cwd=tmp_path)

    quoted = '"my corpus"' if sys.platform == "win32" else "'my corpus'"
    assert result.stdout.endswith(f"Then run: tilia migrate {quoted} --apply\n")


def test_a_name_the_terminal_cant_encode_is_still_printed(tmp_path):
    place(tmp_path / "corpus" / "交响曲.tla", OLD / "0.7.0.tla")

    result = tilia("migrate", "corpus", cwd=tmp_path, utf8=False)

    assert result.returncode == 0, result.stderr
    assert b"Would migrate 1 file to format" in result.stdout


# TiLiA 0.7 sees a migrated file as one from a newer version (SC-010)


# Copied from TiLiA 0.7.0's tilia/file/migration.py (tag v0.7.0), where
# app_version defaults to that release's version.
def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of ints.

    Reads the leading integer of each dot-separated segment, so suffixes
    are ignored (``"0.7.0rc1"`` -> ``(0, 7, 0)``).
    """
    parts: list[int] = []
    for segment in version.split("."):
        digits = ""
        for char in segment:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def is_from_newer_version(data: dict, app_version: str = "0.7.0") -> bool:
    return _parse_version(data.get("version", "0.0.0")) > _parse_version(app_version)


def test_tilia_0_7_sees_a_migrated_file_as_from_a_newer_version(clean):
    path = clean / "a.tla"
    assert not is_from_newer_version(json.loads(path.read_text(encoding="utf-8")))

    result = tilia("migrate", "clean", "--apply", cwd=clean.parent)

    assert result.returncode == 0, result.stderr
    for name in ("a.tla", "sub/b.tla"):
        data = json.loads((clean / name).read_text(encoding="utf-8"))
        assert is_from_newer_version(data)


# Options and wrong use


def options(help_text):
    return set(re.findall(r"^\s+(-{1,2}[A-Za-z][\w-]*)", help_text, re.MULTILINE))


def test_help_lists_apply_and_nothing_else(tmp_path):
    result = tilia("migrate", "--help", cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("usage: tilia migrate ")
    assert options(result.stdout) == {"--apply", "--help"}


def test_tilia_lists_migrate_among_its_commands(tmp_path):
    result = tilia("--help", cwd=tmp_path)

    assert "  migrate" in result.stdout.splitlines()


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param([], id="no folder"),
        pytest.param(["nowhere"], id="a folder that doesn't exist"),
        pytest.param(["clean", "--force"], id="an unknown option"),
    ],
)
def test_wrong_use_exits_with_status_2(clean, arguments):
    before = snapshot(clean.parent)

    result = tilia("migrate", *arguments, cwd=clean.parent)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("usage: tilia migrate ")
    assert snapshot(clean.parent) == before


@pytest.mark.parametrize(
    "arguments, message",
    [
        ([], "the following arguments are required: FOLDER"),
        (["--apply"], "the following arguments are required: FOLDER"),
        (["nowhere"], "no such folder: nowhere"),
        (["nowhere", "--apply"], "no such folder: nowhere"),
        (["clean/a.tla"], "not a folder: clean/a.tla"),
        (["clean", "--force"], "unrecognized arguments: --force"),
        (["clean", "--app"], "unrecognized arguments: --app"),
        (["clean", "-h"], "unrecognized arguments: -h"),
        (["clean", "other"], "unrecognized arguments: other"),
    ],
)
def test_wrong_use_names_what_is_wrong(clean, monkeypatch, capsys, arguments, message):
    monkeypatch.chdir(clean.parent)
    before = snapshot(clean.parent)

    assert migrate_command.main(arguments) == 2

    out, err = capsys.readouterr()
    assert out == ""
    assert err.splitlines()[-1] == f"tilia migrate: error: {message}"
    assert snapshot(clean.parent) == before


def test_a_folder_that_cant_be_read_exits_with_status_1(clean, monkeypatch, capsys):
    def refusing(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(os, "scandir", refusing)

    assert migrate_command.main([str(clean)]) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"tilia migrate: can't read {clean}: Permission denied\n"


# What --apply lists besides


def test_apply_lists_files_changed_since_read_and_files_in_use(
    clean, monkeypatch, capsys
):
    place(clean / "c.tla", OLD / "0.0.96.tla")
    read = folder_module.read
    write = folder_module.write

    def then_changed(path):
        document = read(path)
        if Path(path).name == "c.tla":
            shutil.copyfile(OLD / "0.5.15.tla", path)
        return document

    def held_open(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise tla.FileInUse(target)
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "read", then_changed)
    monkeypatch.setattr(folder_module, "write", held_open)

    assert migrate_command.main([str(clean), "--apply"]) == 1

    assert capsys.readouterr().out == (
        f"Migrated 1 file to format {FORMAT}:\n"
        "  from 0.5.15: 1 file\n"
        "Already in the new format: 1 file\n"
        "Left alone: 2 files\n"
        "  c.tla                   changed since it was read\n"
        "  newer.tla               written by a newer TiLiA (format 2.0.0)\n"
        "In use by another program: 1 file\n"
        "  a.tla\n"
        "Changes the migration makes:\n"
        "  sub/b.tla               dropped 2 formal_type and formal_function values;"
        " dropped 3 amplitude bars\n"
        "\n"
        "Wrote 1 file.\n"
    )


def test_apply_lists_a_file_it_couldnt_write(clean, monkeypatch, capsys):
    write = folder_module.write

    def failing(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise OSError(28, "No space left on device", str(target))
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", failing)

    assert migrate_command.main([str(clean), "--apply"]) == 1

    out = capsys.readouterr().out
    assert (
        "Left alone: 2 files\n  a.tla                   can't write: No space left on device\n"
        in out
    )
    assert out.endswith("\nWrote 1 file.\n")


def test_a_change_the_command_has_no_words_for_is_printed_as_counted(
    clean, monkeypatch, capsys
):
    # A count a later step of the migration adds, before the command has a
    # sentence for it.
    migrate = folder_module.migrate_folder

    def with_a_new_count(folder, *, apply=False):
        report = migrate(folder, apply=apply)
        for result in report.files:
            if result.path == "a.tla":
                result.changes["marks_counted"] = 4
        return report

    monkeypatch.setattr(migrate_command, "migrate_folder", with_a_new_count)

    migrate_command.main([str(clean)])

    assert (
        "  a.tla                   dropped 2 formal_type and formal_function values;"
        " dropped 3 amplitude bars; marks_counted: 4\n"
    ) in capsys.readouterr().out
