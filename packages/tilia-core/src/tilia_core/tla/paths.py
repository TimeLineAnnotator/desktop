"""The one path handler: every path a `.tla` file stores, read, found, written
and rebased the same way (FR-033; TimeLineAnnotator/project-management#584).

A file stores paths of two kinds: the media's, at `/media/path`, and each PDF
timeline's, at `/timelines/<id>/path`. A kind added later is one entry in
`TIMELINE_PATHS`, and everything below takes it. What a path's text means, a
URL, a relative path, or an absolute one of either system's form, is
`media_files`'.

- **Reading** (`keep_as_read`): a document keeps the folder its relative paths
  are relative to, found as it is read, and the paths it was read with
  absolute, each after its place. An old file's are those its migration kept
  absolute (TimeLineAnnotator/project-management#402, #530); old bytes read
  with no place are no exception (#582, point 3).
- **The folder** (`paths_folder`, `paths_folder_of`): that of the file, or of
  the file a link to it names (#431), found when it is read or written and
  kept, so that a link changed since doesn't move it (#433).
- **Finding** (`media`, `stored_file`): a relative path from that folder; for
  the document's own origin, the folder kept from its read or last write, as
  a write takes it.
- **Writing** (`rebase_paths`, `follow`): a path is judged by its text. One
  the document was read, or last written, with absolute stays absolute while
  the text at its place is the text read, however it got there, Save As
  included; any other text is made relative to the folder written into
  wherever a relative path exists, and a relative one is recomputed from it
  (#555, option a; #582, points 1 and 4). A path written absolute because no
  relative one exists, on another drive on Windows, is then one the document
  was last written with absolute, so its later writes keep it so.
- **Timelines held outside the document** (`following`), as TiLiA's undo
  keeps one deleted: they follow its writes as its own do.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tilia_core.tla.layout import pointer_to
from tilia_core.tla.media_files import (
    POSIX,
    SYSTEM,
    WINDOWS,
    YOUTUBE_URL,
    absolute_form,
    is_relative,
    is_url,
    local_file,
    relative_path,
    with_slashes,
)
from tilia_core.tla.model import (
    Document,
    Kind,
    Media,
    Timeline,
    timeline_kind_from_current_file,
)

# The place of a document's media path, as a JSON Pointer into its file.
MEDIA_PATH_PLACE = "/media/path"
# The kinds of timeline that store a path, and the attributes that hold it.
TIMELINE_PATHS: dict[Kind, tuple[str, ...]] = {"pdf": ("path",)}

Paths = tuple[tuple[str, str], ...]


# The kinds of path, and their places


def timeline_path_place(key: str, attr: str = "path") -> str:
    """The place of the path `attr` of the timeline at `key` in a document's
    timelines, as a JSON Pointer into its file."""
    return pointer_to(pointer_to("/timelines", key), attr)


def _timeline_paths(timelines: Any) -> Iterator[tuple[str, Timeline, str]]:
    """Each timeline among `timelines`, by its key, that stores a path, with the
    attribute that holds it, once for each such attribute it has."""
    if not isinstance(timelines, dict):
        return
    for key, timeline in timelines.items():
        if not (isinstance(timeline, Timeline) and isinstance(timeline.attrs, dict)):
            continue
        for attr in TIMELINE_PATHS.get(timeline.kind, ()):
            if attr in timeline.attrs:
                yield key, timeline, attr


def stored_paths(doc: Document) -> list[tuple[str, Any]]:
    """Each path `doc` stores, after its place: the media's, then the
    timelines', in the order of `doc.timelines`. A value that isn't text is
    listed as it is, for the writer's check to refuse."""
    paths: list[tuple[str, Any]] = [(MEDIA_PATH_PLACE, doc.media_path)]
    for key, timeline, attr in _timeline_paths(doc.timelines):
        paths.append((timeline_path_place(key, attr), timeline.attrs[attr]))
    return paths


def places_in(content: Mapping[str, Any]) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Each path an old file's content stores once the migration has brought it
    to the current layout, as its place, the object that holds it, and its key
    there: what the migration makes relative."""
    yield MEDIA_PATH_PLACE, content["media"], "path"
    for key, timeline in content["timelines"].items():
        kind = timeline_kind_from_current_file(timeline["kind"])
        for attr in TIMELINE_PATHS.get(kind, ()):
            if attr in timeline:
                yield timeline_path_place(key, attr), timeline, attr


def _with_paths(doc: Document, changed: Mapping[str, Any]) -> Document:
    """`doc` with the paths at the places `changed` names set to its values: a
    copy, sharing with `doc` what didn't change, or `doc` itself when nothing
    did."""
    if not changed:
        return doc
    replaced: dict[str, Timeline] = {}
    for key, timeline, attr in _timeline_paths(doc.timelines):
        place = timeline_path_place(key, attr)
        if place in changed:
            held = replaced.get(key, timeline)
            attrs = {**held.attrs, attr: changed[place]}
            replaced[key] = dataclasses.replace(held, attrs=attrs)
    timelines = {**doc.timelines, **replaced} if replaced else doc.timelines
    media_path = changed.get(MEDIA_PATH_PLACE, doc.media_path)
    return dataclasses.replace(doc, media_path=media_path, timelines=timelines)


# Reading: what a path is judged by


def absolute_paths(doc: Document) -> Paths:
    """The paths `doc` stores that are absolute, of either system's form, each
    after its place, sorted, so that a document is the same in any process."""
    return tuple(
        sorted(
            (place, path)
            for place, path in stored_paths(doc)
            if isinstance(path, str) and absolute_form(path) is not None
        )
    )


def _recorded(held: Paths, written: Iterable[tuple[str, Any]]) -> Paths:
    """`held`, the paths a document holds absolute after their places, once the
    paths `written`, each after its place, are written: each of those is held
    if it is written absolute, and no longer otherwise. A place not written,
    such as that of a timeline taken out of the document, keeps what it held,
    for the timeline put back."""
    paths = dict(held)
    for place, path in written:
        if isinstance(path, str) and absolute_form(path) is not None:
            paths[place] = path
        else:
            paths.pop(place, None)
    return tuple(sorted(paths.items()))


def keep_as_read(doc: Document, path: str | os.PathLike[str] | None) -> None:
    """Give `doc`, just read from the file at `path`, or from bytes with no
    place when `path` is None, what its writes judge its paths by: the folder
    its relative paths are relative to, found now, and the paths it was read
    with absolute (FR-033)."""
    if doc.origin is not None and path is not None:
        doc._paths_folder = (doc.origin, paths_folder(path))
    doc._absolute_as_read = absolute_paths(doc)


# The folder the paths are relative to

# How many links in a row are followed, as many as Linux follows: a loop of
# links is given up on, not followed for ever.
_LINKS_FOLLOWED = 40


def paths_folder(path: str | os.PathLike[str]) -> str:
    """The folder that the paths the file at `path` stores are relative to: the
    file's own, absolute (FR-033).

    When `path` is a link to a file, that is the folder of the file the link
    names, so that one file has one set of paths, whichever way it is reached
    (TimeLineAnnotator/project-management#431). A link to a folder isn't
    followed: a folder is taken as `path`, or the link, names it, as a media
    path given through one is (`as_media_path`), so that a path through a
    linked folder stays through it (TimeLineAnnotator/project-management#366).
    Only where that would name another folder than the system reads, when a
    `..` in a link's target goes up from a linked folder, are links followed.
    A loop of links names no file: its folder is that of `path`."""
    given = os.path.abspath(path)
    file = _named_file(given)
    folder = os.path.dirname(file)
    if file != given:
        # macOS and Linux go up from a linked folder's target, where reading
        # the link's target by name goes up from the link.
        real = os.path.dirname(os.path.realpath(given))
        if not _same_folder(folder, real):
            return real
    return folder


def paths_folder_of(doc: Document) -> str | None:
    """The folder that `doc`'s relative paths are relative to (FR-033): that of
    the file it was read from or last written to, as `paths_folder` found it
    then, so that a link to the file changed since doesn't move it
    (TimeLineAnnotator/project-management#431). When a caller set `origin`,
    `paths_folder` of it, found now: an origin that is a link to a file gives
    the folder of the file the link names, as `write` and `tla.media` take
    it. None for a document from nowhere."""
    if doc.origin is None:
        return None
    held = doc._paths_folder
    if held is not None and held[0] == doc.origin:
        return held[1]
    return paths_folder(doc.origin)


def _named_file(path: str) -> str:
    """The file `path`, absolute, names once the links to files it ends in are
    followed, each target read from the folder of its link, by name; `path`
    itself when it isn't a link, or when its links go round in a loop."""
    file = path
    for _ in range(_LINKS_FOLLOWED):
        if not os.path.islink(file):
            return file
        try:
            target = os.readlink(file)
        except OSError:  # gone since
            return file
        file = os.path.abspath(os.path.join(os.path.dirname(file), _plain(target)))
    return path


def _plain(target: str) -> str:
    """A link's target, without the `\\\\?\\` that Windows puts before an
    absolute one, which no relative path reaches: `\\\\?\\C:\\…` is `C:\\…`, and
    `\\\\?\\UNC\\server\\…` is `\\\\server\\…`. Where the two don't name one
    folder, `paths_folder` follows the links instead."""
    if SYSTEM == WINDOWS and target.startswith("\\\\?\\"):
        rest = target[4:]
        return "\\" + rest[3:] if rest.startswith("UNC\\") else rest
    return target


def _same_folder(folder: str, other: str) -> bool:
    """Whether `folder` and `other` name one folder, or neither names any."""
    found = os.path.isdir(folder)
    if found != os.path.isdir(other):
        return False
    return not found or os.path.samefile(folder, other)


# Finding the file a path names


def media(path: str | os.PathLike[str], doc: Document) -> Media:
    """The media of `doc`, the document of the file at `path` (FR-110).

    A relative path is resolved against the file's folder, an absolute one is
    taken as it is, and a URL is a YouTube link when it matches TiLiA's
    pattern; another URL is never looked up. A path without a scheme is a
    file's, even one like a link (FR-033). A local file is found as
    `stored_file` finds it, for `doc`: from the folder kept from its read or
    last write when `path` is its origin. When none is found, `path` is None.
    TiLiA's further fallbacks are its own."""
    stored = doc.media_path
    found: Path | None = None
    youtube_id: str | None = None
    if not stored:
        kind = "none"
    elif not is_url(stored):
        kind = "local"
        found = stored_file(path, stored, doc=doc)
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


def stored_file(
    path: str | os.PathLike[str], stored: str, *, doc: Document | None = None
) -> Path | None:
    """The file that `stored`, the media's path or a PDF timeline's as the file
    at `path` stores it, names; None when it names none, and for an empty path
    or a URL, which name no file here and are never looked up (FR-021, FR-033).

    A relative path is resolved against the folder of the file at `path`, the
    file a link names when `path` is a link to a file (`paths_folder`). When
    `doc` is given and `path` is its origin, it is the folder `doc`'s paths are
    relative to, kept from its read or last write, as `write` takes it, so that
    a link changed since doesn't move it (`paths_folder_of`). An absolute path
    is taken as it is. It is tried as stored, then with its name, then all of
    it, in decomposed form (NFD). A path that starts with `//` is a server path,
    and a path of the other system's form is never looked up. A backslash is
    left for the system to read: it separates folders on Windows, and is part
    of a name on macOS and Linux."""
    if not stored or is_url(stored):
        return None
    return local_file(stored, _lookup_folder(path, doc))


def stored_file_of(doc: Document, stored: str) -> Path | None:
    """The file that `stored`, a path `doc` holds, names, as `stored_file` finds
    it from the file `doc` was read from or last written to; for a document
    from nowhere, only an absolute path names one, as a stored path is never
    read from where the process happens to run."""
    if not stored or is_url(stored):
        return None
    return local_file(stored, paths_folder_of(doc))


def _lookup_folder(path: str | os.PathLike[str], doc: Document | None) -> str:
    if doc is not None and doc.origin is not None:
        if Path(os.path.abspath(path)) == Path(os.path.abspath(doc.origin)):
            folder = paths_folder_of(doc)
            assert folder is not None  # it has an origin
            return folder
    return paths_folder(path)


# Writing


def rebase_paths(doc: Document, folder: str | os.PathLike[str]) -> Document:
    """`doc` with each path it stores as a file in `folder` stores it (FR-003,
    FR-033), with "/".

    A path is judged by its text. One `doc` was read, or last written, with
    absolute stays absolute while the text at its place is the text read,
    however it got there (TimeLineAnnotator/project-management#555, option a;
    #582). Any other absolute path becomes relative to `folder` wherever a
    relative path exists, so not on another drive on Windows. When `folder`
    isn't the one `doc` was read from or last written to (`paths_folder_of`:
    the folder of the file a link named, when it was reached through a link
    to a file), a relative path is resolved against that one and made
    relative to `folder`, or absolute where no relative path exists. A stored
    relative path is joined with POSIX semantics, "/" between its parts: a
    backslash in it is part of a name, never converted, so that the same
    document gives the same bytes on every system (FR-023). A Windows path
    that stays absolute, or becomes so, is written with "/". An empty path, a
    URL, and a relative path in a document read from nowhere, whose base is
    unknown, are kept. `doc` isn't changed: when a path changes, a copy is
    returned, sharing with `doc` what didn't change."""
    folder = _absolute_folder(folder)
    read_from = paths_folder_of(doc)
    origin = None if read_from is None else _absolute_folder(read_from)
    if origin is not None and os.path.normcase(origin) == os.path.normcase(folder):
        origin = None  # its relative paths are already relative to `folder`
    read = dict(doc._absolute_as_read)
    changed: dict[str, Any] = {}
    for place, path in stored_paths(doc):
        rebased = _rebased(path, origin, folder, read.get(place))
        if rebased != path:
            changed[place] = rebased
    return _with_paths(doc, changed)


def follow(
    doc: Document, rebased: Document, path: str | os.PathLike[str], folder: str
) -> None:
    """Make `doc` follow the file just written at `path` from `rebased`, its
    copy with the paths as written relative to `folder` (FR-033): its origin
    becomes the file, as the reader sets it, with that folder; its paths the
    ones written; and the paths it holds absolute those written so, which its
    next write keeps. The timelines keep their objects; only a rebased path
    changes."""
    doc.origin = Path(os.path.abspath(path))
    doc._paths_folder = (doc.origin, folder)
    doc._absolute_as_read = _recorded(doc._absolute_as_read, stored_paths(rebased))
    if rebased is doc:
        return
    doc.media_path = rebased.media_path
    _take_paths(doc.timelines, rebased.timelines)


def _take_paths(own: Mapping[str, Timeline], rebased: Mapping[str, Timeline]) -> None:
    """Give each of `own`'s timelines whose copy in `rebased` is another the
    paths of that copy."""
    for key, timeline, attr in _timeline_paths(rebased):
        if timeline is not own[key]:
            own[key].attrs[attr] = timeline.attrs[attr]


@contextmanager
def following(
    doc: Document, timelines: Iterable[Timeline], path: str | os.PathLike[str]
) -> Iterator[None]:
    """Make `timelines`, held outside `doc`, follow the write of `doc` to `path`
    that the block makes, as `doc`'s own timelines do. TiLiA's undo holds a
    deleted timeline so, to put it back whole.

    Once the block has run without raising, each one's paths are those that
    write would have written had the timeline been in `doc`, judged by what
    `doc` held before it, and `doc` holds absolute those so written, for when
    the timeline is put back. A block that raises changes none of them."""
    held = {timeline.id: timeline for timeline in timelines}
    rebased = rebase_paths(dataclasses.replace(doc, timelines=held), paths_folder(path))
    yield
    written = [
        (place, value)
        for place, value in stored_paths(rebased)
        if place != MEDIA_PATH_PLACE
    ]
    doc._absolute_as_read = _recorded(doc._absolute_as_read, written)
    _take_paths(held, rebased.timelines)


def _absolute_folder(folder: str | os.PathLike[str]) -> str:
    """`folder` absolute, links not followed. On macOS and Linux, the two
    slashes `os.path.abspath` keeps at the start of `//home/me`, which `Path`
    takes for a root of their own, are the one root."""
    absolute = os.path.abspath(folder)
    return absolute[1:] if SYSTEM == POSIX and absolute.startswith("//") else absolute


def _rebased(stored: Any, origin: str | None, folder: str, read: str | None) -> Any:
    """`stored` as a file in `folder` stores it; `origin` is the folder its
    relative paths are relative to when that isn't `folder`, or None; `read`
    the absolute path the document was read or last written with at its place,
    or None."""
    if not isinstance(stored, str):
        return stored  # for the check to refuse
    form = absolute_form(stored)
    if form is not None:
        # The text the document was read with stays absolute, and one of the
        # other system's form has no relative path from here.
        relative = (
            relative_path(stored, folder, form)
            if form == SYSTEM and stored != read
            else None
        )
        return with_slashes(stored, form) if relative is None else relative
    if origin is None or not is_relative(stored):
        # Empty, a URL, relative to a drive or its root, or already relative
        # to `folder`: kept as written.
        return stored
    return _moved(stored, origin, folder)


def _moved(stored: str, origin: str, folder: str) -> str:
    """`stored`, a path relative to the folder `origin`, as relative to
    `folder`: as `os.path.relpath` would give it, except that the stored path
    is split on "/" only and its names are compared exactly, on every system,
    so that a backslash in one stays part of it and a document gives the same
    bytes everywhere (FR-023). The two folders, which the system gave, are
    compared as it reads them. Where no relative path exists (another drive
    on Windows), absolute and normalised, with "/": in a path of Windows form,
    a backslash separates folders."""
    parts = _collapsed(stored)
    up = 0
    while up < len(parts) and parts[up] == "..":
        up += 1
    names = parts[up:]
    base = Path(origin).parts
    base = base[: max(1, len(base) - up)]  # never above the root
    here = Path(folder).parts
    if os.path.normcase(base[0]) != os.path.normcase(here[0]):
        return with_slashes(os.path.normpath(os.path.join(origin, stored)), SYSTEM)
    target = [*base, *names]
    same = 0
    for mine, theirs in zip(here, target, strict=False):  # up to the shorter
        if same < len(base):  # two folders the system gave, not a stored name
            mine, theirs = os.path.normcase(mine), os.path.normcase(theirs)
        if mine != theirs:
            break
        same += 1
    return "/".join([".."] * (len(here) - same) + target[same:]) or "."


def _collapsed(stored: str) -> list[str]:
    """The names of `stored`, split on "/", without "." and without a ".." that
    can go back over the name before it. A ".." after a name holding a
    backslash stays: what it goes back over differs by system, a part of that
    name on Windows and all of it on macOS and Linux."""
    names: list[str] = []
    for name in stored.split("/"):
        if name in ("", "."):
            continue
        if name == ".." and names and names[-1] != ".." and "\\" not in names[-1]:
            names.pop()
        else:
            names.append(name)
    return names
