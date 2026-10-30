"""Finding a document's media: a local file, a YouTube video, or none.

A file stores the media's path, and each PDF timeline's path, relative to
its folder with "/", absolute only where no relative path exists (another
drive on Windows), a URL as it is, or empty (FR-033). The forms of a path
are told apart here, for the migration, the writer and the lookup alike. An
absolute path has the form of the system that wrote it, whichever system
reads it: `C:/…` or `\\\\server\\share\\…` is a Windows path, `/…` a POSIX
one. A path of the other system's form is never looked up on this one.

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
    windows = PureWindowsPath(path)  # "/" and "\\" both separate its parts
    return not windows.drive and not windows.root


def with_slashes(path: str, form: str) -> str:
    """A path of `form` with "/" between its parts. A backslash in a POSIX
    path is part of a name."""
    return path.replace("\\", "/") if form == WINDOWS else path


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
    pattern. A local file that isn't found is tried with its name, then its
    whole path, in decomposed form (NFD), as named on macOS's older file
    system; when none is found, `path` is None. TiLiA's further fallbacks
    are its own."""
    stored = doc.media_path
    found: Path | None = None
    youtube_id: str | None = None
    if not stored:
        kind = "none"
    elif youtube := YOUTUBE_URL.match(stored):
        kind, youtube_id = "youtube", youtube[6]
    else:
        kind = "local"
        found = _found(stored, os.path.dirname(os.path.abspath(path)))
    return Media(
        kind=kind,
        stored=stored,
        path=found,
        youtube_id=youtube_id,
        length=doc.media_length,
    )


def _found(stored: str, folder: str) -> Path | None:
    """The local file `stored` names, from the file's `folder`, or None."""
    form = absolute_form(stored)
    if is_url(stored) or (form is not None and form != SYSTEM):
        # Joined to the folder, a Windows path would name a file below it on
        # macOS and Linux.
        return None
    head, name = os.path.split(stored)
    spellings = (
        stored,
        os.path.join(head, unicodedata.normalize("NFD", name)),
        unicodedata.normalize("NFD", stored),
    )
    candidates = dict.fromkeys(
        os.path.normpath(os.path.join(folder, spelling)) for spelling in spellings
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return Path(candidate)
    logger.debug("media not found: %r, from %r", stored, folder)
    return None
