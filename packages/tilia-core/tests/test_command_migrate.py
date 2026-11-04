"""`tilia migrate`, through the `tilia` command: the report of
contracts/command.md, `--apply`, `--help`, and the exit statuses."""

import json
import os
import re
import shutil
import stat
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
    migrated file breaks a rule, which doesn't stop it being migrated. It is
    written on one line, so that is the line of what the report warns about."""
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
  sqx_08.tla              dropped 2 formal_type and formal_function values; dropped 3 amplitude bars; moved 3 marks to metadata
  sqx_21.tla              dropped 2 formal_type and formal_function values; dropped 3 amplitude bars; moved 3 marks to metadata
                          line 1: the timeline "Formal analysis" holds a component of kind "MARKER", which a timeline of kind "Hierarchy" doesn't have: it is kept as it is
  sqx_30.tla              dropped 2 formal_type and formal_function values; moved 2 marks to metadata
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


def test_help_reads_as_contracts_command_md_shows_it(monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "80")  # argparse wraps to the terminal

    assert migrate_command.main(["--help"]) == 0

    assert capsys.readouterr().out == (
        "usage: tilia migrate [--apply] [--help] FOLDER\n"
        "\n"
        f"List what migrating the .tla files below FOLDER to format {FORMAT} would\n"
        "change, and write nothing. With --apply, write them.\n"
        "\n"
        "positional arguments:\n"
        "  FOLDER   every .tla file below it is taken, hidden files and folders left\n"
        "           out\n"
        "\n"
        "options:\n"
        "  --apply  write the migrated files\n"
        "  --help   show this help and exit\n"
    )


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
    read = folder_module.read_with_migration
    write = folder_module.write

    def then_changed(path):
        read_result = read(path)
        if Path(path).name == "c.tla":
            shutil.copyfile(OLD / "0.5.15.tla", path)
        return read_result

    def held_open(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise tla.FileInUse(target)
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "read_with_migration", then_changed)
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
        " dropped 3 amplitude bars; moved 2 marks to metadata\n"
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


def test_one_mark_moved_is_worded_in_the_singular(tmp_path, capsys):
    old = json.loads((OLD / "0.0.96.tla").read_text(encoding="utf-8"))
    old["timelines"]["1"]["components"]["4"]["comments"] = "tag=p1 first theme"
    place(tmp_path / "piece.tla", json.dumps(old).encode())

    migrate_command.main([str(tmp_path)])

    assert (
        "  piece.tla               dropped 2 formal_type and formal_function values;"
        " moved 1 mark to metadata\n"
    ) in capsys.readouterr().out


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
        " dropped 3 amplitude bars; moved 3 marks to metadata; marks_counted: 4\n"
    ) in capsys.readouterr().out


def test_a_subfolder_that_cant_be_listed_is_listed_as_left_alone(
    clean, monkeypatch, capsys
):
    place(clean / "locked" / "piece.tla", OLD / "0.7.0.tla")
    scandir = os.scandir

    def refusing(path):
        if Path(path).name == "locked":
            raise PermissionError(13, "Permission denied", str(path))
        return scandir(path)

    monkeypatch.setattr(os, "scandir", refusing)

    assert migrate_command.main([str(clean)]) == 1

    assert (
        "Left alone: 2 files\n"
        "  locked/                 can't read: Permission denied\n"
        "  newer.tla               written by a newer TiLiA (format 2.0.0)\n"
    ) in capsys.readouterr().out


def test_every_outcome_has_its_place_in_the_report():
    from tilia_core.tla.model import FileResult, MigrationReport, Outcome

    # A migrated file is listed when the migration changes something in it.
    files = [
        FileResult(
            path=f"{outcome.value}.tla",
            outcome=outcome,
            reason="why",
            changes={"formal_values_dropped": 1},
        )
        for outcome in Outcome
    ]
    report = MigrationReport(files=files)

    text = "\n".join(migrate_command.report_lines(report, "corpus", apply=True))

    assert "Already in the new format: 1 file" in text
    for outcome in Outcome:
        if outcome is not Outcome.CURRENT:
            assert f"  {outcome.value}.tla" in text


# The folder, as given


def test_a_tilde_is_part_of_the_folder_name(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    place(home / "elsewhere.tla", OLD / "0.5.15.tla")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    place(tmp_path / "work" / "~" / "piece.tla", OLD / "0.7.0.tla")
    monkeypatch.chdir(tmp_path / "work")

    assert migrate_command.main(["~"]) == 0

    out = capsys.readouterr().out
    assert "  piece.tla " in out
    assert "elsewhere.tla" not in out


# Nothing but the report


PRINT_ONLY = """\
import os
import sys
from pathlib import Path

scandir = os.scandir


def refusing(path):
    if Path(path).name == "locked":
        raise PermissionError(13, "Permission denied", str(path))
    return scandir(path)


os.scandir = refusing
from tilia_core.commands import main

sys.exit(main())
"""


def test_the_command_prints_its_report_and_nothing_else(clean):
    place(clean / "locked" / "piece.tla", OLD / "0.7.0.tla")
    read_only = clean / "a.tla"
    os.chmod(read_only, stat.S_IREAD)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        result = subprocess.run(
            [sys.executable, "-c", PRINT_ONLY, "migrate", "clean", "--apply"],
            cwd=clean.parent,
            env=env,
            capture_output=True,
            encoding="utf-8",
            timeout=120,
        )
    finally:
        os.chmod(read_only, stat.S_IREAD | stat.S_IWRITE)

    assert result.returncode == 1
    assert "  a.tla                   can't write: " in result.stdout
    assert "  locked/                 can't read: Permission denied" in result.stdout
    assert result.stderr == ""


def test_a_reader_that_stops_reading_doesnt_end_in_a_traceback(sqx):
    script = shutil.which("tilia", path=sysconfig.get_path("scripts"))
    process = subprocess.Popen(
        [script, "migrate", "sqx"],
        cwd=sqx.parent,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process.stdout.close()  # as `| head` does once it has its lines
    err = process.stderr.read().decode("utf-8")
    process.wait(timeout=120)

    assert err == ""
    assert process.returncode == 1  # the report's status: a file can't be read


# Then run: the folder, quoted for the shell


@pytest.mark.parametrize(
    "folder, quoted",
    [
        ("sqx", "sqx"),
        (r"C:\corpora\sqx", r"C:\corpora\sqx"),
        ("my corpus", '"my corpus"'),
        ("Bach&Handel", "'Bach&Handel'"),
        ("a $b", "'a $b'"),
        ("it's", "'it''s'"),
        ("it\u2019s", "'it\u2019\u2019s'"),  # PowerShell takes ’ for a quote
        ("50%", "'50%'"),
        ("a;b", "'a;b'"),
        ("a`b", "'a`b'"),
        ('a"b', "'a\"b'"),
        ("a|b", "'a|b'"),
        ("(draft)", "'(draft)'"),
        ("a^b", "'a^b'"),
        ("@corpus", "'@corpus'"),
        ("a,b", "'a,b'"),
    ],
)
def test_on_windows_a_folder_is_quoted_for_powershell(folder, quoted):
    assert migrate_command._quoted(folder, windows=True) == quoted


@pytest.mark.parametrize(
    "folder, quoted",
    [
        ("sqx", "sqx"),
        ("my corpus", "'my corpus'"),
        ("Bach&Handel", "'Bach&Handel'"),
        ("it's", "'it'\"'\"'s'"),
    ],
)
def test_on_macos_and_linux_a_folder_is_quoted_for_the_shell(folder, quoted):
    assert migrate_command._quoted(folder, windows=False) == quoted


@pytest.mark.parametrize("name", ["Bach&Handel", "a $b"])
def test_then_run_quotes_a_folder_the_shell_would_misread(
    tmp_path, monkeypatch, capsys, name
):
    place(tmp_path / name / "a.tla", OLD / "0.7.0.tla")
    monkeypatch.chdir(tmp_path)

    migrate_command.main([name])

    out = capsys.readouterr().out
    assert out.endswith(f"Then run: tilia migrate '{name}' --apply\n")


@pytest.mark.parametrize("space", [0x3000, 0x00A0, 0x2002, 0x200A])
def test_on_windows_a_folder_with_any_space_is_quoted(space):
    # PowerShell splits an argument at these too.
    folder = "楽譜" + chr(space) + "コーパス"

    assert migrate_command._quoted(folder, windows=True) == f'"{folder}"'


@pytest.mark.parametrize(
    "folder, shown",
    [
        ("corpora", "corpora"),
        ("corpora\\", "corpora"),
        ("corpora/", "corpora"),
        ("corpora\\\\", "corpora"),
        ("C:\\my corpus\\", '"C:\\my corpus"'),
        # PowerShell 5.1 would pass 'C:\my $corpus\' as C:\my $corpus" --apply.
        ("C:\\my $corpus\\", "'C:\\my $corpus'"),
        ("C:\\", "C:\\"),
        ("C:/", "C:/"),
        ("\\\\server\\share\\", "\\\\server\\share"),
        ("\\\\server\\share", "\\\\server\\share"),
        # Without its separator, each of these names a drive, which isn't a folder.
        ("\\\\?\\C:\\", "\\\\?\\C:\\"),
        ("\\\\.\\C:\\", "\\\\.\\C:\\"),
        ("//?/C:/", "//?/C:/"),
        ("//./C:/", "//./C:/"),
        ("\\\\?\\Volume{1b2c}\\", "'\\\\?\\Volume{1b2c}\\'"),
        # A folder on one is as any other, and so is a share by its device path.
        ("\\\\?\\C:\\corpora\\", "\\\\?\\C:\\corpora"),
        ("\\\\.\\C:\\corpora\\", "\\\\.\\C:\\corpora"),
        ("\\\\?\\UNC\\server\\share\\", "\\\\?\\UNC\\server\\share"),
        ("\\\\?\\unc\\server\\share\\", "\\\\?\\unc\\server\\share"),
        ("//?/UNC/server/share/", "//?/UNC/server/share"),
        ("-draft", ".\\-draft"),
        ("-my draft", '".\\-my draft"'),
        ("-a&b", "'.\\-a&b'"),
        ("-draft\\", ".\\-draft"),
    ],
)
def test_on_windows_the_folder_to_run_again(folder, shown):
    assert migrate_command._folder_to_run(folder, windows=True) == shown


@pytest.mark.parametrize(
    "folder, shown",
    [
        ("corpora", "corpora"),
        ("corpora/", "corpora"),
        ("corpora//", "corpora"),
        ("/home/anne/corpora/", "/home/anne/corpora"),
        ("/", "/"),
        ("//", "//"),
        ("my corpus/", "'my corpus'"),
        ("-draft", "./-draft"),
        ("-my draft", "'./-my draft'"),
    ],
)
def test_on_macos_and_linux_the_folder_to_run_again(folder, shown):
    assert migrate_command._folder_to_run(folder, windows=False) == shown


def test_then_run_gives_the_folder_without_a_trailing_separator(
    tmp_path, monkeypatch, capsys
):
    place(tmp_path / "corpora" / "a.tla", OLD / "0.7.0.tla")
    monkeypatch.chdir(tmp_path)

    migrate_command.main(["corpora" + os.sep])

    out = capsys.readouterr().out
    assert out.endswith("Then run: tilia migrate corpora --apply\n")


def test_then_run_gives_a_folder_named_like_an_option_as_a_path(
    tmp_path, monkeypatch, capsys
):
    place(tmp_path / "-draft" / "a.tla", OLD / "0.7.0.tla")
    monkeypatch.chdir(tmp_path)

    migrate_command.main(["--", "-draft"])

    out = capsys.readouterr().out
    assert out.endswith(f"Then run: tilia migrate .{os.sep}-draft --apply\n")


def test_then_run_escapes_a_control_character_in_the_folder():
    from tilia_core.tla.model import FileResult, MigrationReport, Outcome

    old = FileResult(path="a.tla", outcome=Outcome.WOULD_MIGRATE, from_version="0.7")
    report = MigrationReport(files=[old])

    lines = migrate_command.report_lines(report, "corp" + chr(0x1B) + "us", apply=False)

    assert lines[-1].startswith("Then run: tilia migrate ")
    assert "corp\\x1bus" in lines[-1]
    assert chr(0x1B) not in lines[-1]


def test_a_folder_that_doesnt_exist_is_named_escaped(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert migrate_command.main(["no" + chr(0x1B) + "where"]) == 2

    err = capsys.readouterr().err
    assert err.splitlines()[-1] == "tilia migrate: error: no such folder: no\\x1bwhere"
    assert chr(0x1B) not in err


def test_a_folder_that_cant_be_listed_is_named_escaped(monkeypatch, capsys):
    folder = "corp" + chr(0x1B) + "us"

    def refused(path, *, apply=False):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(os.path, "isdir", lambda path: path == folder)
    monkeypatch.setattr(migrate_command, "migrate_folder", refused)

    assert migrate_command.main([folder]) == 1

    err = capsys.readouterr().err
    assert err == "tilia migrate: can't read corp\\x1bus: Permission denied\n"


# An error in the core: named, and its traceback after the report


def test_a_traceback_is_printed_with_its_control_characters_escaped(capsys):
    from tilia_core.tla.model import FileResult, MigrationReport, Outcome

    esc = chr(0x1B)
    failed = FileResult(
        path=f"a{esc}.tla",
        outcome=Outcome.UNREADABLE,
        reason="can't read: an error in tilia-core (ValueError); please report it",
        # Its last line can carry text from the file.
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "step.py", line 1, in step\n'
            f"ValueError: a label {esc}[2J\r\n"
        ),
    )

    migrate_command._print_errors(MigrationReport(files=[failed]))

    assert capsys.readouterr().err == (
        "a\\x1b.tla:\n"
        "Traceback (most recent call last):\n"
        '  File "step.py", line 1, in step\n'
        "ValueError: a label \\x1b[2J\\r\n"
    )


FAILING_READ = """\
import sys
from pathlib import Path

from tilia_core.tla import folder

read = folder.read_with_migration


def failing(path):
    if Path(path).name == "a.tla":
        raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")
    return read(path)


folder.read_with_migration = failing
from tilia_core.commands import main

sys.exit(main())
"""


def test_an_error_in_the_core_is_reported_and_its_traceback_follows(clean):
    result = subprocess.run(
        [sys.executable, "-c", FAILING_READ, "migrate", "clean"],
        cwd=clean.parent,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # in the order printed
        encoding="utf-8",
        timeout=120,
    )

    assert result.returncode == 1
    out = result.stdout
    assert (
        "  a.tla                   can't read: an error in tilia-core (TypeError:"
        " unsupported operand type(s) for +: 'int' and 'str'); please report it\n"
    ) in out
    report, _, after = out.partition("Then run: tilia migrate clean --apply\n")
    assert "Traceback" not in report
    assert after.startswith("a.tla:\nTraceback (most recent call last):\n")
    assert after.endswith(
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'\n"
    )


def test_each_error_in_the_core_has_its_traceback(clean, monkeypatch, capsys):
    read = folder_module.read_with_migration
    write = folder_module.write

    def failing_read(path):
        if Path(path).name == "a.tla":
            raise MemoryError()
        return read(path)

    def failing_write(target, doc, **kwargs):
        if Path(target).name == "b.tla":
            raise KeyError("ordinal")
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "read_with_migration", failing_read)
    monkeypatch.setattr(folder_module, "write", failing_write)
    monkeypatch.setattr(folder_module.time, "sleep", lambda seconds: None)

    assert migrate_command.main([str(clean), "--apply"]) == 1

    out, err = capsys.readouterr()
    assert (
        "  a.tla                   can't read: an error in tilia-core (MemoryError);"
        " please report it\n"
    ) in out
    assert (
        "  sub/b.tla               can't write: an error in tilia-core"
        " (KeyError: 'ordinal'); please report it\n"
    ) in out
    first, second = err.split("Traceback (most recent call last):\n")[1:]
    assert err.startswith("a.tla:\n")
    assert first.endswith("MemoryError\nsub/b.tla:\n")
    assert second.endswith("KeyError: 'ordinal'\n")


# Characters that would change the report are printed escaped


def with_version(source, version):
    content = json.loads(source.read_text(encoding="utf-8"))
    content["version"] = version
    return json.dumps(content).encode()


def test_a_version_cant_add_lines_to_the_report_or_erase_any(
    tmp_path, monkeypatch, capsys
):
    place(tmp_path / "old.tla", with_version(OLD / "0.7.0.tla", "0.7.0\x1b[2J"))
    place(
        tmp_path / "newer.tla", with_version(BROKEN / "newer-format.tla", "2.0\nWrote")
    )

    migrate_command.main([str(tmp_path)])

    out = capsys.readouterr().out
    assert "  from 0.7.0\\x1b[2J: 1 file\n" in out
    assert (
        "  newer.tla               written by a newer TiLiA (format 2.0\\nWrote)\n"
    ) in out
    assert "\x1b" not in out
    assert "\nWrote" not in out


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuses such names")
def test_a_file_name_cant_add_lines_to_the_report(tmp_path, capsys):
    place(tmp_path / "evil\nWrote 9 files.tla", OLD / "0.7.0.tla")
    place(tmp_path / "erase\x1b[1A.tla", BROKEN / "newer-format.tla")

    migrate_command.main([str(tmp_path)])

    out = capsys.readouterr().out
    assert "  evil\\nWrote 9 files.tla  " in out
    assert "  erase\\x1b[1A.tla  " in out
    assert "\x1b" not in out
    assert "\nWrote 9" not in out


def test_every_control_character_is_escaped_where_the_report_shows_text():
    from tilia_core.tla.model import (
        FileResult,
        FolderNotListed,
        MigrationReport,
        Outcome,
        ReadWarning,
    )

    controls = "".join(map(chr, [*range(0x20), 0x7F, *range(0x80, 0xA0)]))
    report = MigrationReport(
        files=[
            FileResult(
                path=f"a{controls}.tla",
                outcome=Outcome.WOULD_MIGRATE,
                from_version=f"0.7{controls}",
                warnings=[ReadWarning(place="/x", line=None, message=f"w{controls}")],
            ),
            FileResult(
                path=f"b{controls}.tla",
                outcome=Outcome.UNREADABLE,
                reason=f"r{controls}",
            ),
            FileResult(path=f"c{controls}.tla", outcome=Outcome.IN_USE),
        ],
        shared_ids=[[f"a{controls}.tla", f"b{controls}.tla"]],
        folders_not_listed=[
            FolderNotListed(path=f"d{controls}/", reason=f"f{controls}")
        ],
    )

    lines = migrate_command.report_lines(report, "corpus", apply=False)

    text = "\n".join(lines)
    assert not set(controls) & set(text.replace("\n", ""))
    for line in lines:
        assert "\n" not in line
    # Each name, version, reason and warning: the paths of a, b, c and d, a
    # and b again in the copies' line, a's version and warning, b's and d's
    # reasons.
    assert text.count("\\x00\\x01\\x02") == 10
    assert text.count("\\x07\\x08\\t\\n\\x0b\\x0c\\r\\x0e") == 10
    assert text.count("\\x1f\\x7f\\x80") == 10
    assert text.count("\\x9f") == 10
