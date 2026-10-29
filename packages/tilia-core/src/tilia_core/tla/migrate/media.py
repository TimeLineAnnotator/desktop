"""Media paths in old files: from absolute to relative to the file.

An old file stores the media's path, and each PDF timeline's path, absolute,
and in `file_path` where it was last saved. The migration makes each path
relative to the file's folder, starting from where TiLiA would find the
media now (contracts/migration.md, *Media paths*):

1. empty, or a URL: kept as it is;
2. absolute, and it exists on this computer: made relative from the file's
   current folder;
3. absolute, and it doesn't exist here: made relative from the folder of the
   old `file_path`, computed with that path's own conventions, Windows or
   POSIX, which is where TiLiA looks when the file and its media moved
   together; without a `file_path`, from the file's current folder;
4. already relative (written by hand): kept as it is.

Where no relative path exists, on another drive or of the other system's
form, the path stays absolute. Separators become "/". The document id is
derived before this step, so it doesn't depend on where the file is.
"""

from __future__ import annotations

import os
from typing import Any

from tilia_core.tla.media import (
    SYSTEM,
    absolute_form,
    folder_of,
    relative_path,
    with_slashes,
)
from tilia_core.tla.model import timeline_kind_from_current_file


def make_relative(
    content: dict[str, Any],
    *,
    file_path: Any,
    path: str | os.PathLike[str] | None,
) -> None:
    """Make the media's path and each PDF timeline's path in `content`, an old
    file's content once migrated, relative, in place. `file_path` is the old
    file's, and `path` where the file is now; None for bytes read without
    their place, which then have no current folder."""
    folder = None if path is None else os.path.dirname(os.path.abspath(path))
    media = content["media"]
    media["path"] = migrated_path(media["path"], file_path=file_path, folder=folder)
    for timeline in content["timelines"].values():
        kind = timeline_kind_from_current_file(timeline["kind"])
        if kind == "pdf" and "path" in timeline:
            timeline["path"] = migrated_path(
                timeline["path"], file_path=file_path, folder=folder
            )


def migrated_path(stored: Any, *, file_path: Any, folder: str | None) -> Any:
    """`stored`, an old file's media or PDF path, as the migration stores it,
    for a file in `folder` (None when unknown) saved last at `file_path`.
    Anything but text is left for the check to refuse."""
    if not isinstance(stored, str):
        return stored
    form = absolute_form(stored)
    if form is None:
        return stored  # empty, a URL, or relative
    if form == SYSTEM and os.path.exists(stored):
        # Where TiLiA finds it now, whatever file_path says.
        return _relative_or_absolute(stored, form, folder)
    saved = file_path if isinstance(file_path, str) else ""
    saved_form = absolute_form(saved)
    if saved_form is None:
        # Never saved under this name (an autosave), or a file_path that
        # doesn't say where: from the current folder, whether or not the
        # media is there.
        return _relative_or_absolute(stored, form, folder if form == SYSTEM else None)
    if saved_form != form:
        return with_slashes(stored, form)  # no relative path between them
    return _relative_or_absolute(stored, form, folder_of(saved, form))


def _relative_or_absolute(stored: str, form: str, folder: str | None) -> str:
    """`stored` relative to `folder`, or absolute where no relative path
    exists, or without a folder; with "/" either way."""
    relative = None if folder is None else relative_path(stored, folder, form)
    return relative if relative is not None else with_slashes(stored, form)
