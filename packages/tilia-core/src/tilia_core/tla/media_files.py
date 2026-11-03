"""Finding a document's media: a local file, a YouTube video, or none.

A file stores the media's path, and each PDF timeline's path, relative to
its folder with "/", absolute only where no relative path exists (another
drive on Windows), a URL as it is, or empty (FR-033). The forms of a path
are told apart here, for the migration, the writer and the lookup alike. An
absolute path has the form of the system that wrote it, whichever system
reads it: `C:/…` or `\\\\server\\share\\…` is a Windows path, `/…` a POSIX
one. A path of the other system's form is never looked up on this one. In a
relative path, a backslash separates its parts, as on Windows, where a name
can't hold one. A path is a URL only when it starts with a scheme, such as
`https://`: one without, even one like a YouTube link, is a file's path
(FR-033, TimeLineAnnotator/project-management#380), and one that starts
with `//` is a Windows server path, as TiLiA writes one with "/"
(TimeLineAnnotator/project-management#397).

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
# It is the core's one copy. It matches a link without its scheme too, which
# TiLiA takes for a link and the core doesn't (FR-033).
YOUTUBE_URL = re.compile(
    r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu\.be))"
    r"(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
)
# A URL's scheme: two characters or more, so that a Windows drive isn't one,
# then "://".
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+://")

WINDOWS = "windows"
POSIX = "posix"
# The form of this system's absolute paths.
SYSTEM = WINDOWS if os.name == "nt" else POSIX
_MODULES = {WINDOWS: ntpath, POSIX: posixpath}


def is_url(path: str) -> bool:
    """Whether `path` is a URL: it starts with a scheme, such as `https://`
    (FR-033). Anything else is a file's path: one that starts with `//` is
    a Windows server path, as TiLiA writes one with "/"."""
    return _URL.match(path) is not None


def _is_link_without_scheme(path: str) -> bool:
    """Whether `path` matches TiLiA's YouTube pattern without being a URL: a
    link as TiLiA stored it when typed, or a file's path that looks like one."""
    return not is_url(path) and YOUTUBE_URL.match(path) is not None


def _as_link(path: str) -> str:
    """A YouTube link without a scheme, with one: `https:` before `//`."""
    return f"https:{path}" if path.startswith("//") else f"https://{path}"


def with_scheme(path: str) -> str:
    """An old file's media path, with `https://` before a YouTube link that
    has no scheme, which TiLiA stored as it was typed, or `https:` before one
    that starts with `//` (FR-033). TiLiA stored local media as absolute
    paths, which never match its pattern."""
    return _as_link(path) if _is_link_without_scheme(path) else path


def as_media_path(given: str | os.PathLike[str]) -> str:
    """The media path to store for one a person or a script gives, as TiLiA's
    `load-media` and a script's `load-media` are given one (FR-033).

    A URL, with a scheme, is returned as it is, and so is an empty text. A
    path is returned absolute, from the working folder, links not followed
    (`os.path.abspath`): the writer stores it relative to the file it
    writes, which a path relative to the working folder isn't. A text
    without a scheme that matches TiLiA's YouTube pattern, such as
    `youtu.be/…`, `youtube.com/clip.mp4` or `//www.youtube.com/…`, is such a
    path when a file is there, or on a server for one that starts with `//`,
    and otherwise a YouTube link, returned with `https://`, or `https:`
    before `//`. A path object is a path, never a link: its text differs by
    system."""
    if not isinstance(given, str):
        return os.path.abspath(os.fspath(given))
    if not given or is_url(given):
        return given
    if _is_link_without_scheme(given) and local_file(given, os.getcwd()) is None:
        return _as_link(given)
    return os.path.abspath(given)


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
    pattern; another URL is never looked up. A path without a scheme is a
    file's, even one like a link (FR-033). A local file is found as
    `local_file` finds it; when none is found, `path` is None. TiLiA's
    further fallbacks are its own."""
    stored = doc.media_path
    found: Path | None = None
    youtube_id: str | None = None
    if not stored:
        kind = "none"
    elif not is_url(stored):
        kind = "local"
        found = local_file(stored, os.path.dirname(os.path.abspath(path)))
    elif youtube := YOUTUBE_URL.match(stored):
        kind, youtube_id = "youtube", youtube[6]
    else:
        kind = "local"  # another URL, as TiLiA takes it: a file it can't find
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
