"""Migrating every `.tla` file in a folder, and the report of what changed.

`migrate_folder` is what `tilia migrate` does (FR-100–FR-105): it reads each
file a corpus at the folder takes, in path order, migrates the old ones in
memory and, with `apply`, writes them, each stating the fingerprint it had
when it was read, so that a file changed in between is left alone. Files in
the current format, of a newer format, or that can't be read are never
written.

`corpus_files` is the walk, which files a corpus is made of
(TimeLineAnnotator/project-management#122), for anything else that walks a
corpus too.
"""

from __future__ import annotations

import errno
import logging
import os
import stat
import time
import unicodedata
from collections.abc import Callable
from operator import itemgetter
from pathlib import Path

from tilia_core.tla.errors import FileChanged, FileInUse, UnreadableFile
from tilia_core.tla.layout import FORMAT_VERSION
from tilia_core.tla.model import Document, FileResult, MigrationReport
from tilia_core.tla.reader import read
from tilia_core.tla.writer import fingerprint_of, write

logger = logging.getLogger(__name__)

EXTENSION = ".tla"
# A file that can't be read is read once more after this many seconds (T1):
# another program may have been writing it.
RETRY_AFTER = 0.2

# The reader's message for a file of a newer format (FR-014).
_NEWER = "written by a newer TiLiA"


def corpus_files(
    folder: str | os.PathLike[str],
    *,
    on_error: Callable[[str, OSError], None] | None = None,
) -> list[tuple[str, Path]]:
    """The `.tla` files a corpus at `folder` takes (#122): every one below
    it, in any letter case, subfolders included; hidden files and folders,
    whose names start with ".", left out, and with them the writer's
    temporary files; links to folders, Windows' junctions among them, not
    followed. A link to a file is taken.

    Each file is given as its path relative to `folder`, with "/" and in NFC,
    and its path on disk, in path order. A subfolder that can't be listed, or
    an entry that can't be looked at, is passed to `on_error` with its
    relative path (a folder's ending in "/") and the error, and left out;
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
            relative = prefix + unicodedata.normalize("NFC", name)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not _is_junction(entry):
                        pending.append((relative + "/", Path(entry.path)))
                # is_file follows a link: one to a file is taken, one to a
                # folder isn't, nor is one that names nothing.
                elif name.lower().endswith(EXTENSION) and entry.is_file():
                    found.append((relative, Path(entry.path)))
            except OSError as error:
                if on_error is None:
                    raise
                on_error(relative, error)
    found.sort(key=itemgetter(0))
    return found


def _is_junction(entry: os.DirEntry[str]) -> bool:
    """Whether an entry `is_dir` takes for a folder is a Windows junction, a
    link to a folder, which Python before 3.12 can't otherwise tell."""
    if os.name != "nt":
        return False
    tag = getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
    return tag == stat.IO_REPARSE_TAG_MOUNT_POINT


def migrate_folder(
    folder: str | os.PathLike[str], *, apply: bool = False
) -> MigrationReport:
    """Migrate every old `.tla` file a corpus at `folder` takes, and report
    on each file it took, in path order (FR-100–FR-105).

    Without `apply`, nothing is written: the report says what would be.
    With it, each old file is written atomically, stating the fingerprint
    it had when it was read; one changed since, held open by another program
    or that can't be written is left as it was, and reported. A file that
    can't be read is read once more after `RETRY_AFTER` seconds, then
    reported. Running it again writes nothing.

    Raises `FileNotFoundError` for a folder that doesn't exist,
    `NotADirectoryError` for a path that isn't a folder, and the system's
    `OSError` when the folder can't be listed.
    """
    root = Path(os.path.expanduser(folder))
    if not root.is_dir():
        code = errno.ENOTDIR if root.exists() else errno.ENOENT
        error = NotADirectoryError if root.exists() else FileNotFoundError
        raise error(code, os.strerror(code), os.fspath(folder))

    results: list[FileResult] = []

    def not_listed(relative: str, error: OSError) -> None:
        logger.warning("can't read %s: %s", relative, error)
        reason = f"can't read: {_why(error)}"
        results.append(FileResult(path=relative, outcome="unreadable", reason=reason))

    ids: dict[str, list[str]] = {}
    for relative, path in corpus_files(root, on_error=not_listed):
        result, document = _migrate_file(relative, path, apply)
        results.append(result)
        if document is not None:
            ids.setdefault(document.document_id, []).append(relative)
    results.sort(key=lambda result: result.path)
    return MigrationReport(
        files=results,
        shared_ids=[paths for paths in ids.values() if len(paths) > 1],
    )


def _migrate_file(
    relative: str, path: Path, apply: bool
) -> tuple[FileResult, Document | None]:
    """One file's result, and its document when it could be read."""
    try:
        document = _read(path)
    except UnreadableFile as error:
        if _is_newer(error):
            return (
                FileResult(path=relative, outcome="newer", reason=error.message),
                None,
            )
        reason = f"can't read: {error.message}"
        if error.line is not None:
            reason = f"can't read (line {error.line}): {error.message}"
        return FileResult(path=relative, outcome="unreadable", reason=reason), None
    except OSError as error:
        reason = f"can't read: {_why(error)}"
        return FileResult(path=relative, outcome="unreadable", reason=reason), None
    if document.format_version == FORMAT_VERSION:
        result = FileResult(
            path=relative, outcome="current", from_version=FORMAT_VERSION
        )
        return result, document
    own = set(document._migration_warnings)
    result = FileResult(
        path=relative,
        outcome="would_migrate",
        from_version=document.format_version,
        changes=dict(document._migration_changes),
        warnings=[warning for warning in document.warnings if warning not in own],
    )
    if apply:
        result.outcome, result.reason = _write(path, document)
    return result, document


def _read(path: Path) -> Document:
    """The file's document, read once more after a pause when it can't be
    read the first time (T1). A file of a newer format isn't read again: it
    won't change."""
    try:
        return read(path)
    except UnreadableFile as error:
        if _is_newer(error):
            raise
        logger.debug("can't read %s, reading it again: %s", path, error)
    except OSError as error:
        logger.debug("can't read %s, reading it again: %s", path, error)
    time.sleep(RETRY_AFTER)
    return read(path)


def _is_newer(error: UnreadableFile) -> bool:
    return error.place == "/version" and error.message.startswith(_NEWER)


def _write(path: Path, document: Document) -> tuple[str, str | None]:
    """Write a migrated document over the file it was read from, stating the
    fingerprint it had then; the outcome, and why when it wasn't written."""
    try:
        write(path, document, expect=fingerprint_of(document))
    except FileChanged:
        return "changed_since_read", "changed since it was read"
    except FileInUse:
        return "in_use", "in use by another program"
    except (OSError, ValueError) as error:
        logger.warning("can't write %s: %s", path, error)
        return "write_failed", f"can't write: {_why(error)}"
    return "migrated", None


def _why(error: Exception) -> str:
    """The reason an error gives, without the path the report shows anyway."""
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)
