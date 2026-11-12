"""Finding a document's media: a local file, a YouTube video, or none.

A file stores the media's path, and each PDF timeline's path, relative to
its folder with "/", absolute only where no relative path exists (another
drive on Windows) or where reading kept it absolute (an old file's path that
can't be related to where the file was saved;
TimeLineAnnotator/project-management#530), a URL as it is, or empty (FR-033).
The forms of a path are told apart here, for the migration, the writer and
the lookup alike. An absolute path has the form of the system that wrote it,
whichever system reads it: `C:/…` or `\\\\server\\share\\…` is a Windows
path, `/…` a POSIX one. A path of the other system's form is never looked
up on this one. A
backslash in a relative path, or in a POSIX one, is never converted: TiLiA
and the core write "/" between folders, so it is a hand edit, or part of a
name on macOS and Linux, and the lookup lets the system read it
(TimeLineAnnotator/project-management#402). In a Windows path, it separates
folders. A path is a URL only when it starts with a scheme, such as
`https://`: one without, even one like a YouTube link, is a file's path
(FR-033, TimeLineAnnotator/project-management#380), and one that starts
with `//` is a Windows server path, as TiLiA writes one with "/"
(TimeLineAnnotator/project-management#397).

The lookups are `tla.media`, and `tla.stored_file` for any stored path; this
module has a name of its own, so that the function doesn't hide it.
"""

from __future__ import annotations

import logging
import ntpath
import os
import posixpath
import re
import unicodedata
from pathlib import Path, PureWindowsPath

from tilia_core.tla.model import Document, Media, Timeline

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
# The starts of a verbatim path, `\\?\` or the `//?/` that a file stores for it.
_VERBATIM = ("\\\\?\\", "//?/")
# The starts that `PureWindowsPath`, and Windows, read as a share's two slashes,
# though they are of two kinds.
_SLASH_AND_BACKSLASH = ("/\\", "\\/")


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
    writes, which a path relative to the working folder isn't. Only where
    that wouldn't name what the system reads, on macOS and Linux, are links
    followed (`_absolute`). A text without a scheme that matches TiLiA's
    YouTube pattern, such as `youtu.be/…` or `youtube.com/clip.mp4`, is such
    a path when a file is there, and otherwise a YouTube link, returned with
    `https://`. One that starts with `//`, such as `//www.youtube.com/…`, is a
    link, returned with `https:`, and never looked for on a server, which on
    Windows could block for seconds and reach the host the link names: as the
    migration takes an old one. Any other path that starts with `//` is a
    server path, unless it names a file on macOS or Linux, which read `//` as
    the root: then it is that file's path, with one slash. A path object is a
    path, never a link: its text differs by system. A path of the other
    system's form (`C:\\…` or `\\\\server\\share\\…` on macOS and Linux, `/…`
    on Windows) is already absolute in its own form, and is returned as it
    is: the working folder says nothing about it."""
    if not isinstance(given, str):
        return _absolute(os.fspath(given))
    if not given or is_url(given):
        return given
    if _is_link_without_scheme(given) and (
        given.startswith("//") or local_file(given, os.getcwd()) is None
    ):
        return _as_link(given)
    return _absolute(given)


def _absolute(path: str) -> str:
    """`path`, not a link, absolute from the working folder, links not
    followed; as it is when this system mustn't read it
    (`_not_for_this_system`).

    macOS and Linux read two paths otherwise than `os.path.abspath` does
    (FR-033). `//home/me/rec.wav` names a file there, and would keep its two
    slashes, which the core reads as a Windows server path: they become the
    one root. And `link/../rec.wav` goes up from the link's target, where
    `os.path.abspath` goes up from the link, by name, to no file or another
    one: when it gives another than `path` names, links are followed. Windows
    reads `link/..` by name too, so nothing is looked up there, where a
    `//server/share` path would go to the network."""
    if SYSTEM == POSIX and path.startswith("//") and os.path.isfile(path):
        path = "/" + path.lstrip("/")
    if _not_for_this_system(path):
        return path
    if SYSTEM == WINDOWS and path.startswith(_VERBATIM):
        # Already absolute, and its name is as it is: `os.path.abspath` would
        # take a trailing dot or space off it (FR-052).
        return path.replace("/", "\\")
    absolute = os.path.abspath(path)
    if SYSTEM == POSIX and not _same_file(absolute, path):
        return str(Path(path).resolve())
    return absolute


def _same_file(path: str, other: str) -> bool:
    """Whether `path` and `other` name one file, or neither names any."""
    found = os.path.isfile(path)
    if found != os.path.isfile(other):
        return False
    return not found or os.path.samefile(path, other)


def absolute_form(path: str) -> str | None:
    """`WINDOWS` or `POSIX` for an absolute path of that system's form; None
    for anything else: empty, a URL, a relative path, or one relative to a
    drive (`C:piece.wav`) or to the current drive's root (`\\piece.wav`)."""
    if not path or is_url(path):
        return None
    return _form(path)


def absolute_paths(doc: Document) -> frozenset[str]:
    """The media's path and the PDF timelines' paths of `doc` that are absolute,
    of either system's form. Read from a file, or just written to one, these are
    the paths a write keeps absolute (TimeLineAnnotator/project-management#530)."""
    paths = [doc.media_path]
    if isinstance(doc.timelines, dict):
        paths += [
            timeline.attrs.get("path")
            for timeline in doc.timelines.values()
            if isinstance(timeline, Timeline)
            and timeline.kind == "pdf"
            and isinstance(timeline.attrs, dict)
        ]
    return frozenset(
        path
        for path in paths
        if isinstance(path, str) and absolute_form(path) is not None
    )


def _form(path: str) -> str | None:
    """`absolute_form` of a path that isn't a URL. Only two slashes of one
    kind, `//` or `\\\\`, start a share, whatever `PureWindowsPath` reads: `/\\a`
    is a POSIX path, and `\\/a` is relative to a root, as `\\a` is. They are
    tested here because `PureWindowsPath` calls a share with one name, such as
    `//x.wav`, absolute only from Python 3.13, and a file's bytes mustn't differ
    by version."""
    if path[:2] in ("//", "\\\\"):
        return WINDOWS
    if not path.startswith(_SLASH_AND_BACKSLASH) and (
        PureWindowsPath(path).is_absolute()  # a drive and its root
    ):
        return WINDOWS
    if path.startswith("/"):
        return POSIX
    return None


def _not_for_this_system(path: str) -> bool:
    """Whether this system mustn't read `path`, which isn't a URL: it is of the
    other system's form, so it would name something else here, or on Windows
    it starts with `\\/`, which Windows itself would take for a share."""
    form = _form(path)
    if form is not None and form != SYSTEM:
        return True
    return SYSTEM == WINDOWS and path.startswith("\\/")


def is_relative(path: str) -> bool:
    """Whether `path` is relative to the file's folder: not empty, not a URL,
    and with no drive or root of either system's form, which is why a
    leading backslash counts as a root here."""
    if not path or is_url(path):
        return False
    windows = PureWindowsPath(path)
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
    pattern; another URL is never looked up. A path without a scheme is a
    file's, even one like a link (FR-033). A local file is found as
    `stored_file` finds it; when none is found, `path` is None. TiLiA's
    further fallbacks are its own."""
    stored = doc.media_path
    found: Path | None = None
    youtube_id: str | None = None
    if not stored:
        kind = "none"
    elif not is_url(stored):
        kind = "local"
        found = stored_file(path, stored)
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


def stored_file(path: str | os.PathLike[str], stored: str) -> Path | None:
    """The file that `stored`, the media's path or a PDF timeline's as the file
    at `path` stores it, names; None when it names none, and for an empty path
    or a URL, which name no file here and are never looked up (FR-021, FR-033).

    A relative path is resolved against the folder of the file at `path`, and
    an absolute one is taken as it is. It is tried as stored, then with its
    name, then all of it, in decomposed form (NFD). A path that starts with `//`
    is a server path, and a path of the other system's form is never looked up.
    A backslash is left for the system to read: it separates folders on Windows,
    and is part of a name on macOS and Linux."""
    if not stored or is_url(stored):
        return None
    return local_file(stored, os.path.dirname(os.path.abspath(path)))


def local_file(stored: str, folder: str | None) -> Path | None:
    """The file that `stored`, a local path and not a URL, names from
    `folder`, the folder of the file that stores it; None when it names no
    file. Without a folder, only an absolute path is looked up.

    It is tried as stored, then with its name, then all of it, in decomposed
    form (NFD), as named on macOS's older file system and copied elsewhere.
    The migration asks this whether an old file's media exists, so that it
    and `tla.media` agree. A path of the other system's form is never looked
    up: joined to the folder, a Windows path would name a file below it on
    macOS and Linux. Any other is joined to the folder as it is, and the
    system reads it: a backslash separates folders on Windows, and is part
    of a name on macOS and Linux."""
    if _not_for_this_system(stored):
        return None
    if _form(stored) is None and folder is None:
        return None
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
