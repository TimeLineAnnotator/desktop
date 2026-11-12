"""`tilia migrate`: convert a folder of `.tla` files to the current format.

`tilia migrate FOLDER` lists what migrating the folder would change, and
writes nothing; `tilia migrate FOLDER --apply` writes (FR-104). A thin layer
over `tla.migrate_folder` (FR-105): it prints the report, as
contracts/command.md shows it, and exits with its status: 0 when every file
it should migrate was migrated, or would be; 1 when one was left alone; 2
when the command was used wrongly.
"""

from __future__ import annotations

import argparse
import errno
import io
import ntpath
import os
import posixpath
import re
import shlex
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator
from typing import TextIO

from tilia_core.commands._report import ESCAPES
from tilia_core.commands._report import shown as _shown
from tilia_core.tla.folder import migrate_folder
from tilia_core.tla.layout import FORMAT_VERSION
from tilia_core.tla.model import FileResult, MigrationReport, Outcome

PROG = "tilia migrate"

# A row's text starts in this column or later: two spaces, then the path,
# as in contracts/command.md.
_PATH_WIDTH = 24

# How the report words what the migration counted, once and more than
# once, in the order it lists them. A count without words here is printed
# as its key and its number, unless it is one the report leaves out.
_CHANGES: dict[str, tuple[str, str]] = {
    "formal_values_dropped": (
        "dropped 1 formal_type or formal_function value",
        "dropped {} formal_type and formal_function values",
    ),
    "amplitude_bars_dropped": (
        "dropped 1 amplitude bar",
        "dropped {} amplitude bars",
    ),
    "marks_moved": (
        "moved 1 mark to metadata",
        "moved {} marks to metadata",
    ),
    "display_modes_renamed": (
        "changed 1 display mode from chord to letter",
        "changed {} display modes from chord to letter",
    ),
    "beats_dropped": (
        "dropped 1 beat",
        "dropped {} beats",
    ),
    "beat_units_dropped": (
        "dropped 1 beat unit",
        "dropped {} beat units",
    ),
    "measure_marks_dropped": (
        "dropped 1 measure mark",
        "dropped {} measure marks",
    ),
    "beat_timelines_tilia_cant_open": (
        "1 beat timeline TiLiA can't open",
        "{} beat timelines TiLiA can't open",
    ),
}
# Counts the report leaves out: a warning of the check's says each, with its line.
_SAID_BY_THEIR_WARNINGS = frozenset({"measures_with_two_beat_units"})

_ADVICE = (
    "Nothing was written. The migration rewrites every file it lists. Keep the\n"
    "originals first: commit them if the folder is in git, or copy the folder."
)


def main(argv: list[str] | None = None) -> int:
    _tolerate_unencodable(sys.stdout)
    parser = _parser()
    try:
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:  # --help, or wrong use, which argparse printed
        return stop.code if isinstance(stop.code, int) else 2
    # As given: the shell has expanded any "~" that names a home folder, so
    # one left is part of a name.
    folder: str = arguments.folder
    if not os.path.isdir(folder):
        what = "not a folder" if os.path.exists(folder) else "no such folder"
        return _wrong_use(parser, f"{what}: {_shown(folder)}")
    try:
        report = migrate_folder(folder, apply=arguments.apply)
    except OSError as error:
        why = error.strerror or str(error)
        print(f"{PROG}: can't read {_shown(folder)}: {why}", file=sys.stderr)
        return 1
    _print("\n".join(report_lines(report, folder, apply=arguments.apply)))
    _print_errors(report)
    return report.status


def _print(text: str) -> None:
    """Print `text`. A reader that stops reading, as `head` does once it has
    its lines, ends the output there, without an error."""
    try:
        print(text)
        sys.stdout.flush()
    except OSError as error:
        if not _reader_gone(error):
            raise
        # Python flushes stdout again as it exits: into nothing, now.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass


def _reader_gone(error: OSError) -> bool:
    """Whether writing failed because the other end of a pipe was closed:
    EPIPE, or EINVAL, as a write to a closed pipe can fail on Windows."""
    if isinstance(error, BrokenPipeError):
        return True
    return os.name == "nt" and error.errno == errno.EINVAL


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            f"List what migrating the .tla files below FOLDER to format"
            f" {FORMAT_VERSION} would change, and write nothing. With --apply,"
            " write them."
        ),
        # Its options are --apply and --help, spelled out (FR-104).
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "folder",
        metavar="FOLDER",
        help="every .tla file below it is taken, hidden files and folders left out",
    )
    parser.add_argument("--apply", action="store_true", help="write the migrated files")
    parser.add_argument("--help", action="help", help="show this help and exit")
    return parser


def _wrong_use(parser: argparse.ArgumentParser, message: str) -> int:
    """Say what is wrong as argparse does, and give the status for it."""
    parser.print_usage(sys.stderr)
    print(f"{PROG}: error: {message}", file=sys.stderr)
    return 2


def _tolerate_unencodable(stream: TextIO) -> None:
    """Print a character the terminal's encoding lacks as its escape, rather
    than stop: a file name may hold any character. A lone surrogate, from a
    file name that isn't UTF-8, is printed as its escape too, as
    `errors.printable` writes it."""
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(errors="backslashreplace")


# The part of the report that lists the files of each outcome. Every outcome
# has one, so that no file is left out of the report.
_SECTIONS: dict[Outcome, str] = {
    Outcome.WOULD_MIGRATE: "migrated",
    Outcome.MIGRATED: "migrated",
    Outcome.CURRENT: "current",
    Outcome.NEWER: "left alone",
    Outcome.UNREADABLE: "left alone",
    Outcome.CHANGED_SINCE_READ: "left alone",
    Outcome.WRITE_FAILED: "left alone",
    Outcome.IN_USE: "in use",
}


def report_lines(report: MigrationReport, folder: str, *, apply: bool) -> list[str]:
    """The report, as contracts/command.md shows it, one line each; `folder`
    as given."""
    files = report.files
    sections: dict[str, list[FileResult]] = {name: [] for name in _SECTIONS.values()}
    for f in files:
        sections[_SECTIONS[Outcome(f.outcome)]].append(f)
    migrated, current = sections["migrated"], sections["current"]
    in_use = sections["in use"]
    # A folder that couldn't be listed is left alone too, among the files.
    left = [
        (_shown(path), _shown(reason))
        for path, reason in sorted(
            [(f.path, f.reason or "") for f in sections["left alone"]]
            + [
                (unlisted.path, unlisted.reason)
                for unlisted in report.folders_not_listed
            ],
            key=lambda row: _path_order(row[0]),
        )
    ]
    changed = [(_shown(f.path), texts) for f in migrated if (texts := _change_texts(f))]
    paths = [path for path, _ in left] + [path for path, _ in changed]
    width = max([_PATH_WIDTH, *(len(path) + 2 for path in paths)])

    def row(path: str, text: str) -> str:
        return f"  {path:<{width}}{text}"

    verb = "Migrated" if apply else "Would migrate"
    head = f"{verb} {_files(len(migrated))} to format {FORMAT_VERSION}"
    lines = [head + (":" if migrated else ".")]
    versions = Counter(f.from_version or "" for f in migrated)
    for version in sorted(versions, key=_version_order):
        lines.append(f"  from {_shown(version)}: {_files(versions[version])}")
    lines.append(f"Already in the new format: {_files(len(current))}")
    lines.append(f"Left alone: {_files(len(left))}")
    lines += [row(path, reason) for path, reason in left]
    if in_use:
        lines.append(f"In use by another program: {_files(len(in_use))}")
        lines += [f"  {_shown(f.path)}" for f in in_use]
    for group in report.shared_ids:
        copies = ", ".join(_shown(path) for path in group)
        lines.append(f"Share a document id (copies): {copies}")
    if changed:
        lines.append("Changes the migration makes:")
        for path, texts in changed:
            lines.append(row(path, texts[0]))
            lines += [row("", text) for text in texts[1:]]
    lines.append("")
    written = sum(Outcome(f.outcome) is Outcome.MIGRATED for f in files)
    if apply and written:
        lines.append(f"Wrote {_files(written)}.")
    elif not apply and migrated:
        lines += _ADVICE.split("\n")
        again = _shown(_folder_to_run(folder))
        lines.append(f"Then run: tilia migrate {again} --apply")
    else:
        lines.append("Nothing was written.")
    return lines


def _print_errors(report: MigrationReport) -> None:
    """After the report, on stderr, the traceback of each error in the core
    that left a file alone, after the file's path, so that it can be sent
    with the report of the fault. Its control characters are escaped, but
    for its line breaks: its last line can hold text from the file."""
    for f in report.files:
        if f.traceback is not None:
            print(f"{_shown(f.path)}:", file=sys.stderr)
            print(f.traceback.translate(_ESCAPES_BUT_LINES), end="", file=sys.stderr)


def _path_order(path: str) -> tuple[str, str]:
    """Paths in the order of their NFC forms, as `migrate_folder` orders them."""
    return unicodedata.normalize("NFC", path), path


def _files(count: int) -> str:
    return "1 file" if count == 1 else f"{count} files"


def _change_texts(file: FileResult) -> list[str]:
    """What the report says a file's migration changes, line by line: its
    counts, then its warnings."""
    texts = [_shown(str(warning)) for warning in file.warnings]
    counts = "; ".join(_changes(file.changes))
    return [counts, *texts] if counts else texts


def _changes(changes: dict[str, int]) -> Iterator[str]:
    """What the migration counted, in words where the report has them."""
    for key, (once, more) in _CHANGES.items():
        if key in changes:
            count = changes[key]
            yield once if count == 1 else more.format(count)
    for key in sorted(changes.keys() - _CHANGES.keys() - _SAID_BY_THEIR_WARNINGS):
        yield f"{key}: {changes[key]}"


_LEADING_DIGITS = re.compile(r"[0-9]+")


def _version_order(version: str) -> tuple[tuple[tuple[int, str], ...], str]:
    """Versions in TiLiA's order, by the leading number of each dot-separated
    part, then as text. The numbers are compared by length, then digit by
    digit, as int() refuses very long ones."""
    numbers = []
    for part in version.split("."):
        match = _LEADING_DIGITS.match(part)
        if match is None:
            break
        digits = match.group().lstrip("0")
        numbers.append((len(digits), digits))
    return tuple(numbers), version


# What PowerShell or cmd.exe read specially in an argument. PowerShell takes
# the typographic quotes for quotes too.
_SINGLE_QUOTES = "'‘’‚‛"
_SPECIAL_ON_WINDOWS = frozenset('&|<>^%!;,=$`"(){}[]@#' + _SINGLE_QUOTES + "“”„")


def _quoted(argument: str, *, windows: bool = os.name == "nt") -> str:
    """`argument` as the system's shell takes it back. On macOS and Linux, as
    a POSIX shell does. On Windows, as typed, or in double quotes when it
    holds a space of any kind, at each of which PowerShell splits; but in
    single quotes, for PowerShell, the shell Windows opens by default, when
    it holds a character PowerShell or cmd.exe read specially, each single
    quote doubled inside them."""
    if not windows:
        return shlex.quote(argument)
    if any(char in _SPECIAL_ON_WINDOWS for char in argument):
        doubled = "".join(
            char * 2 if char in _SINGLE_QUOTES else char for char in argument
        )
        return f"'{doubled}'"
    if any(char.isspace() for char in argument):
        return f'"{argument}"'
    return argument


# A drive by its Windows device path, such as `\\?\C:` or `\\.\C:`, which without
# the separator after it is the drive and not its root folder. `\\?\UNC\` starts
# a server's share instead, which is a folder either way.
_WINDOWS_DEVICE = re.compile(r"[\\/]{2}[?.][\\/](?!UNC[\\/])", re.IGNORECASE)


def _folder_to_run(folder: str, *, windows: bool = os.name == "nt") -> str:
    """FOLDER as `Then run:` gives it back, for the system's shell (`_quoted`):
    without a trailing separator, which Windows PowerShell 5.1 passes on
    before a closing quote as a quote of the folder's name, but a root, such
    as "/", "C:\\" or "\\\\?\\C:\\", as it is; and a folder whose name starts
    with "-", which would be taken for an option, after "./" (".\\" on
    Windows)."""
    paths = ntpath if windows else posixpath
    separators = "\\/" if windows else "/"
    drive, rest = paths.splitdrive(folder)
    if rest.rstrip(separators):
        folder = drive + rest.rstrip(separators)
    elif drive[:1] in separators and drive and not _WINDOWS_DEVICE.match(drive):
        folder = drive  # a share's root, \\server\share\
    if folder.startswith("-"):
        folder = (".\\" if windows else "./") + folder
    return _quoted(folder, windows=windows)


# Control characters, as `_shown` escapes them, but for line breaks.
_ESCAPES_BUT_LINES = {code: escape for code, escape in ESCAPES.items() if code != 0x0A}
