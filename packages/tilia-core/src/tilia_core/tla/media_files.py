"""Finding a document's media: a local file, a YouTube video, or none.

A file stores the media's path, and each PDF timeline's path, relative to
its folder with "/", absolute only where no relative path exists (another
drive on Windows), a URL as it is, or empty (FR-033). The forms of a path
are told apart here, for the migration, the writer and the lookup alike. An
absolute path has the form of the system that wrote it, whichever system
reads it: `C:/…` or `\\\\server\\share\\…` is a Windows path, `/…` a POSIX
one. A path of the other system's form is never looked up on this one. In a
relative path, a backslash separates its parts, as on Windows, where a name
can't hold one.

The lookup is `tla.media`; this module has a name of its own, so that the
function doesn't hide it.
"""

from __future__ import annotations

import logging
import ntpath
import os
import posixpath
import re
import unicodedata
from pathlib import Path, PureWindowsPath

from tilia_core.tla.model import Document, Media

logger = logging.getLogger(__name__)

# TiLiA's own pattern for a YouTube link, copied from
# tilia.constants.YOUTUBE_URL_REGEX, with the dot in "youtu.be" escaped,
# which TiLiA's leaves to match any character: group 6 is the video's id.
YOUTUBE_URL = re.compile(
    r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu\.be))"
    r"(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
)
# Any other URL: a scheme of two characters or more, so that a Windows
# drive isn't one, then "://".
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+://")

WINDOWS = "windows"
POSIX = "posix"
# The form of this system's absolute paths.
SYSTEM = WINDOWS if os.name == "nt" else POSIX
_MODULES = {WINDOWS: ntpath, POSIX: posixpath}


def is_url(path: str) -> bool:
    """Whether `path` is a URL: a YouTube link, as TiLiA reads one, or another."""
    return YOUTUBE_URL.match(path) is not None or _URL.match(path) is not None


def absolute_form(path: str) -> str | None:
    """`WINDOWS` or `POSIX` for an absolute path of that system's form; None
    for anything else: empty, a URL, a relative path, or one relative to a
    drive (`C:piece.wav`) or to the current drive's root (`\\piece.wav`)."""
    if not path or is_url(path):
        return None
    return _form(path)


def _form(path: str) -> str | None:
    """`absolute_form` of a path that isn't a URL."""
    if PureWindowsPath(path).is_absolute():  # a drive and its root, or a share
        return WINDOWS
    if path.startswith("/"):
        return POSIX
    return None


def is_relative(path: str) -> bool:
    """Whether `path` is relative to the file's folder: not empty, not a URL,
    and with no drive or root of either system's form."""
    if not path or is_url(path):
        return False
    return _is_relative(path)


def _is_relative(path: str) -> bool:
    """`is_relative` of a path that isn't empty or a URL."""
    windows = PureWindowsPath(path)  # "/" and "\\" both separate its parts
    return not windows.drive and not windows.root


def with_slashes(path: str, form: str) -> str:
    """A path of `form` with "/" between its parts. A backslash in a POSIX
    path is part of a name."""
    return path.replace("\\", "/") if form == WINDOWS else path


def relative_with_slashes(path: str) -> str:
    """A relative path with "/" between its parts, which a backslash also
    separates."""
    return path.replace("\\", "/")


def folder_of(path: str, form: str) -> str:
    """The folder of `path`, a path of `form`, with that system's conventions."""
    return _MODULES[form].dirname(path)


def relative_path(path: str, folder: str, form: str) -> str | None:
    """`path`, absolute and of `form`, relative to `folder`, absolute and of
    the same form, with "/"; None where no relative path exists: on another
    drive or server share. Windows paths are compared in any letter case."""
    try:
        relative = _MODULES[form].relpath(path, folder)
    except ValueError:  # another drive or share
        return None
    return with_slashes(relative, form)


def media(path: str | os.PathLike[str], doc: Document) -> Media:
    """The media of `doc`, the document of the file at `path` (FR-110).

    A relative path is resolved against the file's folder, an absolute one is
    taken as it is, and a URL is a YouTube link when it matches TiLiA's
    pattern; another URL is never looked up. A local file is found as
    `local_file` finds it; when none is found, `path` is None. TiLiA's
    further fallbacks are its own."""
    stored = doc.media_path
    found: Path | None = None
    youtube_id: str | None = None
    if not stored:
        kind = "none"
    elif youtube := YOUTUBE_URL.match(stored):
        kind, youtube_id = "youtube", youtube[6]
    else:
        kind = "local"
        if not _URL.match(stored):
            found = local_file(stored, os.path.dirname(os.path.abspath(path)))
    return Media(
        kind=kind,
        stored=stored,
        path=found,
        youtube_id=youtube_id,
        length=doc.media_length,
    )


def local_file(stored: str, folder: str | None) -> Path | None:
    """The file that `stored`, a local path and not a URL, names from
    `folder`, the folder of the file that stores it; None when it names no
    file. Without a folder, only an absolute path is looked up.

    It is tried as stored, then with its name, then all of it, in decomposed
    form (NFD), as named on macOS's older file system and copied elsewhere.
    The migration asks this whether an old file's media exists, so that it
    and `tla.media` agree. A path of the other system's form is never looked
    up: joined to the folder, a Windows path would name a file below it on
    macOS and Linux."""
    form = _form(stored)
    if form is not None and form != SYSTEM:
        return None
    if form is None:
        if folder is None:
            return None
        if _is_relative(stored):
            stored = relative_with_slashes(stored)
    head, name = os.path.split(stored)
    spellings = (
        stored,
        os.path.join(head, unicodedata.normalize("NFD", name)),
        unicodedata.normalize("NFD", stored),
    )
    base = folder or ""  # an absolute path ignores it
    candidates = dict.fromkeys(
        os.path.normpath(os.path.join(base, spelling)) for spelling in spellings
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return Path(candidate)
    logger.debug("media not found: %r, from %r", stored, folder)
    return None
