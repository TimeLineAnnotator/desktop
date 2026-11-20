"""Migrating every `.tla` file in a folder, and the report of what changed.

`migrate_folder` is what `tilia migrate` does (FR-100–FR-105): it reads each
file a corpus at the folder takes, in path order, migrates the old ones in
memory and, with `apply`, writes them, each stating the fingerprint it had
when it was read, so that a file changed in between is left alone. Files in
the current format, of a newer format, or that can't be read are never
written. An error in one file doesn't stop the others (FR-052).

`corpus_files` is the walk, which files a corpus is made of
(TimeLineAnnotator/project-management#122 (which files make up a corpus)),
for anything else that walks a corpus too.
"""

from __future__ import annotations

import errno
import logging
import os
import stat
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from traceback import format_exception
from typing import NamedTuple

from tilia_core.tla.errors import (
    BrokenRules,
    FileChanged,
    FileInUse,
    NewerFormat,
    UnreadableFile,
)
from tilia_core.tla.layout import FORMAT_VERSION
from tilia_core.tla.migrate.to_1 import Migrated
from tilia_core.tla.model import (
    Document,
    FileResult,
    FolderNotListed,
    HardLinks,
    MigrationReport,
    Outcome,
)
from tilia_core.tla.problems import cant_check
from tilia_core.tla.reader import read_with_migration
from tilia_core.tla.writer import write

logger = logging.getLogger(__name__)

EXTENSION = ".tla"
# The files that can't be read are read once more, after one pause of this
# many seconds (T1): another program may have been writing them.
RETRY_AFTER = 0.2


def corpus_files(
    folder: str | os.PathLike[str],
    *,
    on_error: Callable[[str, OSError], None] | None = None,
) -> list[tuple[str, Path]]:
    """The `.tla` files a corpus at `folder` takes
    (TimeLineAnnotator/project-management#122 (which files make up a
    corpus)): every one below it, in any letter case, subfolders included;
    hidden files and folders, whose names start with ".", left out, and with
    them the writer's temporary files; links to folders, Windows' junctions
    among them, not followed. A link to a file is taken.

    Each file is given as its path relative to `folder`, with "/" and its
    names as the system gives them, and its path on disk. They are in the
    order of the paths' NFC forms, so in the same order whichever form a
    file system gives a name in. A subfolder that can't be listed, or an
    entry that can't be told to be a folder or not, is passed to `on_error`
    with its relative path, ending in "/", and the error, and left out;
    without `on_error`, the error is raised. An error listing `folder`
    itself is always raised.
    """
    found: list[tuple[str, Path]] = []
    pending = [("", Path(folder))]
    while pending:
        prefix, current = pending.pop()
        try:
            with os.scandir(current) as listing:
                entries = list(listing)
        except OSError as error:
            if not prefix or on_error is None:
                raise
            on_error(prefix, error)
            continue
        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue
            relative = prefix + name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not _is_junction(entry):
                        pending.append((relative + "/", Path(entry.path)))
                    continue
            except OSError as error:
                if on_error is None:
                    raise
                on_error(relative + "/", error)
                continue
            # is_file follows a link: one to a file is taken, one to a
            # folder isn't, nor is one that names nothing. One that can't be
            # followed is taken: reading it says why.
            if name.lower().endswith(EXTENSION) and _is_file(entry):
                found.append((relative, Path(entry.path)))
    found.sort(key=lambda item: _path_order(item[0]))
    return found


def _path_order(path: str) -> tuple[str, str]:
    """Paths in the order of their NFC forms, then of the forms given."""
    return unicodedata.normalize("NFC", path), path


def _is_junction(entry: os.DirEntry[str]) -> bool:
    """Whether an entry `is_dir` takes for a folder is a Windows junction, a
    link to a folder, which Python before 3.12 can't otherwise tell."""
    if os.name != "nt":
        return False
    tag = getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
    return tag == stat.IO_REPARSE_TAG_MOUNT_POINT


def _is_file(entry: os.DirEntry[str]) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return True


def migrate_folder(
    folder: str | os.PathLike[str], *, apply: bool = False
) -> MigrationReport:
    """Migrate every old `.tla` file a corpus at `folder` takes, and report
    on each file it took, in path order (FR-100–FR-105). `folder` is taken
    as it is given: a "~" in it is part of a name.

    Without `apply`, nothing is written: the report says what would be.
    With it, each old file is written atomically, stating the fingerprint
    it had when it was read; one changed since, held open by another program
    or that can't be written is left as it was, and reported. The files that
    can't be read are read once more, after one pause of `RETRY_AFTER`
    seconds for them all, then reported. An error in one file, even one in
    the core, is reported for that file, and the others go on. Running it
    again writes nothing. An old file with harmonies or modes can't be written
    without the `harmony` extra, since they can't be checked (FR-054): with or
    without `apply`, it is reported as left alone, naming the command. The
    report lists the files with more than one name (hard links) that it
    writes, or would write (`MigrationReport.hard_links`): the names of each
    file are noted before anything is written, so that `apply` lists what the
    listing listed.

    Raises `FileNotFoundError` for a folder that doesn't exist,
    `NotADirectoryError` for a path that isn't a folder, and the system's
    `OSError` when the folder can't be listed.
    """
    root = Path(folder)
    if not root.is_dir():
        code = errno.ENOTDIR if root.exists() else errno.ENOENT
        error = NotADirectoryError if root.exists() else FileNotFoundError
        raise error(code, os.strerror(code), os.fspath(folder))

    folders: list[FolderNotListed] = []

    def not_listed(relative: str, error: OSError) -> None:
        logger.warning("can't list %s: %s", relative, error)
        reason = f"can't read: {error.strerror or error}"
        folders.append(FolderNotListed(path=relative, reason=reason))

    results: list[FileResult] = []
    ids: dict[str, list[str]] = {}

    def taken(relative: str, path: Path, *, last: bool) -> bool:
        """Whether the file was read, or this was its last try."""
        migrated = _migrate_file(relative, path, apply, last=last)
        if migrated is None:
            return False
        result, document = migrated
        results.append(result)
        if document is not None:
            ids.setdefault(document.document_id, []).append(relative)
        return True

    files = corpus_files(root, on_error=not_listed)
    names = _names(files)
    again: list[tuple[str, Path]] = []
    for relative, path in files:
        if not taken(relative, path, last=False):
            again.append((relative, path))
    if again:
        time.sleep(RETRY_AFTER)
        for relative, path in again:
            taken(relative, path, last=True)
    results.sort(key=lambda result: _path_order(result.path))
    shared = [
        sorted(paths, key=_path_order) for paths in ids.values() if len(paths) > 1
    ]
    folders.sort(key=lambda unlisted: _path_order(unlisted.path))
    return MigrationReport(
        files=results,
        shared_ids=sorted(shared, key=lambda paths: _path_order(paths[0])),
        folders_not_listed=folders,
        hard_links=_hard_links(
            results, names, root, {relative for relative, _ in files}
        ),
    )


def _migrate_file(
    relative: str, path: Path, apply: bool, *, last: bool
) -> tuple[FileResult, Document | None] | None:
    """One file's result, and its document when it could be read; None for
    a file that couldn't be read, to read again unless this was the `last`
    try. A file of a newer format isn't read again: it won't change."""
    try:
        document, migrated = read_with_migration(path)
    except NewerFormat as error:
        result = FileResult(path=relative, outcome=Outcome.NEWER, reason=error.message)
        return result, None
    except Exception as error:  # an error in the core too (FR-052)
        expected = isinstance(error, (UnreadableFile, OSError))
        if not last:
            return None
        if not expected:
            logger.error("can't read %s", path, exc_info=error)
        reason = _cant("read", error, expected=expected)
        result = FileResult(
            path=relative,
            outcome=Outcome.UNREADABLE,
            reason=reason,
            traceback=None if expected else _traceback(error),
        )
        return result, None
    return _result(relative, path, document, migrated, apply), document


def _result(
    relative: str,
    path: Path,
    document: Document,
    migrated: Migrated | None,
    apply: bool,
) -> FileResult:
    if migrated is None:  # in the current format
        return FileResult(
            path=relative, outcome=Outcome.CURRENT, from_version=FORMAT_VERSION
        )
    result = FileResult(
        path=relative,
        outcome=Outcome.WOULD_MIGRATE,
        from_version=document.format_version,
        changes=dict(migrated.changes),
        # A document's warnings are the migration's, which `changes` counts,
        # then the check's and the core's rules'. By their order: the reader adds
        # each one's line.
        warnings=document.warnings[len(migrated.warnings) :],
    )
    if apply:
        result.outcome, result.reason, result.traceback = _write(path, document)
    elif (unable := cant_check(document)) is not None:
        # What `apply` would find: the report says what would be
        # (TimeLineAnnotator/project-management#490).
        result.outcome = Outcome.WRITE_FAILED
        result.reason = f"can't write: {unable}"
    return result


# A file, whatever its name: its device and inode numbers; or, on a file system
# that gives no inode numbers, its real path, which a link to it shares.
_FileKey = tuple[int, int] | str

# A name in a folder, as a file system that ignores case and Unicode form
# compares it: the folder, as `_FileKey`, and the name, in NFC, casefolded.
_NameKey = tuple[_FileKey, str]

# The outcomes of a file written, or that would be.
_WRITTEN = frozenset({Outcome.MIGRATED, Outcome.WOULD_MIGRATE})


class _Name(NamedTuple):
    """A name of a file with more than one name (hard links)."""

    file: _FileKey  # which file it is
    names: int  # how many names the file has
    link: bool  # a symbolic link to the file, not one of its names
    name: _NameKey  # the name, or for a link the name it gives


def _names(files: list[tuple[str, Path]]) -> dict[str, _Name]:
    """Each file with more than one name (hard links), by its path relative
    to the folder. Taken before anything is written, as a write gives the
    name written a file of its own (FR-044). A link to a file counts the
    names of the file it names, and a write through it replaces the name it
    gives, not the link. A file that can't be looked at is left out: reading
    it says why."""
    noted: dict[str, _Name] = {}
    for relative, path in files:
        try:
            info = os.stat(path)
            if info.st_nlink < 2:
                continue
            real = os.path.realpath(path)
            link = os.path.islink(path)
            name = _name_key(real if link else os.fspath(path))
        except OSError:
            continue
        file = (info.st_dev, info.st_ino) if info.st_ino else real
        noted[relative] = _Name(file, info.st_nlink, link, name)
    return noted


def _name_key(path: str) -> _NameKey:
    """The name at `path`: its folder, whatever the folder's name, and the
    name in NFC, casefolded. On POSIX a link's real path keeps the link's
    spelling, which a case-insensitive file system, as macOS's, takes for the
    name of another case or Unicode form."""
    folder, name = os.path.split(path)
    info = os.stat(folder)
    where = (info.st_dev, info.st_ino) if info.st_ino else os.path.realpath(folder)
    return where, unicodedata.normalize("NFC", name).casefold()


def _hard_links(
    results: list[FileResult],
    names: dict[str, _Name],
    folder: Path,
    taken: set[str],
) -> list[HardLinks]:
    """The files with more than one name that the run writes, or would
    write, under one name or more: each with all its names in the folder,
    written or not, in path order, and how many names it has outside the
    folder, which keep the old version. The names in the folder are those
    that aren't links, which are exact, and the names the links give that
    aren't among them: first those the walk took, from `results`; then, for
    a file that still has names unaccounted for, those the walk skips,
    hidden or with another extension (TimeLineAnnotator/project-management#626)."""
    noted = [result for result in results if result.path in names]
    written = {
        names[result.path].file
        for result in noted
        if Outcome(result.outcome) in _WRITTEN
    }
    paths: dict[_FileKey, list[str]] = {}
    exact: dict[_FileKey, list[_NameKey]] = {}
    linked: dict[_FileKey, set[_NameKey]] = {}
    for result in noted:
        name = names[result.path]
        if name.file in written:
            paths.setdefault(name.file, []).append(result.path)
            if name.link:
                linked.setdefault(name.file, set()).add(name.name)
            else:
                exact.setdefault(name.file, []).append(name.name)

    def outside(file: _FileKey) -> int:
        not_links = exact.get(file, [])
        in_folder = len(not_links) + len(linked.get(file, set()) - set(not_links))
        # A name added to the file while its names were counted could make
        # more names in the folder than the count taken before it.
        return max(names[paths[file][0]].names - in_folder, 0)

    # How many names each file still has unaccounted for. Only a file told by
    # its inode number can be found by it.
    missing = {
        file: outside(file)
        for file in paths
        if isinstance(file, tuple) and outside(file) > 0
    }
    if missing:
        for file, found in _names_the_walk_skips(folder, taken, missing).items():
            for path, name in found:
                paths[file].append(path)
                exact.setdefault(file, []).append(name)
    lines = [
        HardLinks(paths=tuple(sorted(found, key=_path_order)), outside=outside(file))
        for file, found in paths.items()
    ]
    return sorted(lines, key=lambda line: _path_order(line.paths[0]))


def _names_the_walk_skips(
    folder: Path, taken: set[str], missing: dict[tuple[int, int], int]
) -> dict[tuple[int, int], list[tuple[str, _NameKey]]]:
    """The names of the files in `missing`, by device and inode, in `folder`
    that the walk of `corpus_files` didn't take, `taken` being those it took:
    hidden ones, with other extensions, in hidden folders. Each is its path
    relative to `folder`, with "/", and its name as `_name_key` gives it. The
    walk reads the folder's entries once, and stops once it has found as many
    names of each file as `missing` says are missing. Links aren't names, and
    links to folders aren't followed, as in the walk. A folder that can't be
    listed, or a name that can't be looked at, is left out, and so isn't
    found."""
    left = dict(missing)
    inodes = {inode for _, inode in left}
    found: dict[tuple[int, int], list[tuple[str, _NameKey]]] = {}
    pending = [("", folder)]
    while pending:
        prefix, current = pending.pop()
        try:
            with os.scandir(current) as listing:
                entries = list(listing)
        except OSError:
            continue
        for entry in entries:
            relative = prefix + entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not _is_junction(entry):
                        pending.append((relative + "/", Path(entry.path)))
                    continue
                if relative in taken or not entry.is_file(follow_symlinks=False):
                    continue
                # On POSIX the listing gives each entry's inode number, so
                # only a match is looked at, and the look confirms it, as on
                # overlayfs the two can differ. On Windows the listing gives
                # none, and the entry's own stat gives none either.
                if os.name != "nt" and entry.inode() not in inodes:
                    continue
                info = os.stat(entry.path)
                file = (info.st_dev, info.st_ino)
                if file not in left:
                    continue
                name = _name_key(entry.path)
            except OSError:
                continue
            found.setdefault(file, []).append((relative, name))
            left[file] -= 1
            if not left[file]:
                del left[file]
                if not left:
                    return found
    return found


def _write(path: Path, document: Document) -> tuple[Outcome, str | None, str | None]:
    """Write a migrated document over the file it was read from, stating the
    fingerprint it was read with: `fingerprint_of(document)` isn't an old file's
    fingerprint, which takes the media and PDF paths as the file stores them
    (FR-043). The outcome; why, when it wasn't written; and the traceback of an
    error in the core that stopped it."""
    try:
        write(path, document, expect=document.fingerprint)
    except FileChanged:
        return Outcome.CHANGED_SINCE_READ, "changed since it was read", None
    except FileInUse:
        return Outcome.IN_USE, "in use by another program", None
    except (OSError, ValueError) as error:  # UnreadableFile is a ValueError
        logger.warning("can't write %s: %s", path, error)
        return Outcome.WRITE_FAILED, _cant("write", error, expected=True), None
    except Exception as error:  # an error in the core (FR-052)
        logger.error("can't write %s", path, exc_info=error)
        reason = _cant("write", error, expected=False)
        return Outcome.WRITE_FAILED, reason, _traceback(error)
    return Outcome.MIGRATED, None, None


def _traceback(error: Exception) -> str:
    """The error's traceback, as Python prints it. Kept as text, it holds
    none of the frames the error went through, nor what they held: after a
    MemoryError, that is the memory that ran out."""
    return "".join(format_exception(error))


def _cant(verb: str, error: Exception, *, expected: bool) -> str:
    """Why a file couldn't be read or written, without its path, which the
    report gives anyway. An error that reading or writing doesn't otherwise
    raise is an error in the core, to report: it is named by its type, and
    its traceback is logged and kept in the file's result."""
    if isinstance(error, UnreadableFile):
        where = "" if error.line is None else f" (line {error.line})"
        return f"can't {verb}{where}: {error.message}"
    if isinstance(error, BrokenRules):
        return f"can't {verb}: {'; '.join(str(p) for p in error.problems)}"
    if isinstance(error, OSError) and error.strerror:
        return f"can't {verb}: {error.strerror}"
    if expected:
        return f"can't {verb}: {error}"
    text = str(error)
    named = f"{type(error).__name__}: {text}" if text else type(error).__name__
    return f"can't {verb}: an error in tilia-core ({named}); please report it"
