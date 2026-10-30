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

from tilia_core.tla.errors import FileChanged, FileInUse, NewerFormat, UnreadableFile
from tilia_core.tla.layout import FORMAT_VERSION
from tilia_core.tla.migrate.to_1 import Migrated
from tilia_core.tla.model import (
    Document,
    FileResult,
    FolderNotListed,
    MigrationReport,
    Outcome,
)
from tilia_core.tla.reader import read_with_migration
from tilia_core.tla.writer import fingerprint_of, write

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
    again writes nothing.

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

    again: list[tuple[str, Path]] = []
    for relative, path in corpus_files(root, on_error=not_listed):
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
        return (
            FileResult(path=relative, outcome=Outcome.UNREADABLE, reason=reason),
            None,
        )
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
    own = set(migrated.warnings)  # what `changes` counts
    result = FileResult(
        path=relative,
        outcome=Outcome.WOULD_MIGRATE,
        from_version=document.format_version,
        changes=dict(migrated.changes),
        warnings=[warning for warning in document.warnings if warning not in own],
    )
    if apply:
        result.outcome, result.reason = _write(path, document)
    return result


def _write(path: Path, document: Document) -> tuple[Outcome, str | None]:
    """Write a migrated document over the file it was read from, stating the
    fingerprint it had then; the outcome, and why when it wasn't written."""
    try:
        write(path, document, expect=fingerprint_of(document))
    except FileChanged:
        return Outcome.CHANGED_SINCE_READ, "changed since it was read"
    except FileInUse:
        return Outcome.IN_USE, "in use by another program"
    except (OSError, ValueError) as error:  # UnreadableFile is a ValueError
        logger.warning("can't write %s: %s", path, error)
        return Outcome.WRITE_FAILED, _cant("write", error, expected=True)
    except Exception as error:  # an error in the core (FR-052)
        logger.error("can't write %s", path, exc_info=error)
        return Outcome.WRITE_FAILED, _cant("write", error, expected=False)
    return Outcome.MIGRATED, None


def _cant(verb: str, error: Exception, *, expected: bool) -> str:
    """Why a file couldn't be read or written, without its path, which the
    report gives anyway. An error that isn't one of those reading or writing
    raises, an error in the core, is named by its type: its traceback is in
    the log."""
    if isinstance(error, UnreadableFile):
        where = "" if error.line is None else f" (line {error.line})"
        return f"can't {verb}{where}: {error.message}"
    if isinstance(error, OSError) and error.strerror:
        return f"can't {verb}: {error.strerror}"
    text = str(error)
    if not expected:
        name = type(error).__name__
        text = f"{name}: {text}" if text else name
    return f"can't {verb}: {text}"
