"""The file open in TiLiA: what `FileManager.file` is."""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tilia.file import tla_bridge
from tilia.file.media_metadata import MediaMetadata
from tilia.log import logger
from tilia_core import tla
from tilia_core.tla import paths

_MEDIA_LENGTH = "media length"

# The paths a document holds: its media's, and those of its timelines that store
# one, each by its id in a timeline with nothing else.
_Paths = tuple[str, dict[str, tla.Timeline]]


@dataclass(eq=False)
class OpenDocument:
    """The file open in TiLiA, the document it is saved from, and what its state is
    compared with to tell whether the file is modified.

    `document` is the document the core read from the file, or, for a new file, the
    one `tla.new_document` makes, with the fields TiLiA starts a file with. TiLiA
    builds its timelines from it and keeps it, with what TiLiA doesn't show, such as
    the timelines of kinds it doesn't know. It is the document every save writes, and
    is never built again from TiLiA's state: one built in memory has no fingerprint,
    so a write that states it would check nothing.

    `synced` is the state the document reflects, and `sync` applies to it what differs
    from that state. `removed` keeps what `sync` took out of it, so that an undo gets
    it back whole. For each state undo records, `remember` keeps what the document
    then held that the state can't tell (`tla_bridge.history_of`, and the paths as the
    file stores them), and an undo or a redo back to that state gives it back.

    `media_path` is where the media was found, not the path the file stores
    (`note_media_found`).
    `timelines` and `timelines_hash` are the state's when the file was last read or
    saved. `unknown_discarded` says timelines of kinds TiLiA doesn't know were taken
    out of the document, so that the file reads as modified until it is saved.

    Two are the same file only if they are the same object.
    """

    document: tla.Document | None = None
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = field(default_factory=MediaMetadata)
    timelines: dict[str, Any] = field(default_factory=dict)
    timelines_hash: str = ""
    unknown_discarded: bool = False
    synced: dict[str, Any] | None = None
    removed: tla_bridge.Removed = field(default_factory=dict)
    # Taken by whatever changes the document or copies it: the autosaver copies
    # from its thread.
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    # By the id of a state undo recorded: that state, the document's history, and the
    # paths as the document then held them, which the state can't tell: the state
    # holds where a file was found, or "" when the media wasn't.
    _histories: dict[int, tuple[dict[str, Any], tla_bridge.History, _Paths]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.document is None:
            # A new file (FR-008): the fields TiLiA starts a file with, and no
            # timelines, which TiLiA's state then adds.
            self.document = tla.new_document()
            self.document.metadata = {
                name: copy.deepcopy(value)
                for name, value in self.media_metadata.items()
                if name != _MEDIA_LENGTH
            }
            self.synced = {
                "media_metadata": dict(self.media_metadata),
                "media_path": self.media_path,
                "timelines": {},
            }

    def sync(
        self,
        state: dict[str, Any],
        *,
        by_person: bool = True,
        back_to: dict[str, Any] | None = None,
    ) -> None:
        """Makes the document follow `state`, as `App.get_app_state` gives it.
        `by_person` is False for an undo or a redo, which the states alone can't tell
        from a person's edit. `back_to` is the state undo recorded that an undo or a
        redo has gone back to: the document gets back what it held then. Logs what
        the document couldn't keep as it was."""
        with self._lock:
            if self.synced is None:
                # A document read, before TiLiA took the state it built from it.
                logger.warning("The document reflects no state yet: taking this one.")
                self.synced = state
                return
            notes = tla_bridge.apply_changes(
                self.document,
                self.synced,
                state,
                removed=self.removed,
                by_person=by_person,
            )
            remembered = self._histories.get(id(back_to))
            if remembered is not None and remembered[0] is back_to:
                tla_bridge.give_back_history(
                    self.document, remembered[1], state, removed=self.removed
                )
                _give_back_paths(self.document, remembered[2], state, remembered[0])
            self.synced = state
        for note in notes:
            logger.warning(note)

    def remember(self, state: dict[str, Any]) -> None:
        """Keeps, for `state`, which undo has just recorded and the document follows,
        what the document holds that the state can't tell, for an undo or a redo
        back to it."""
        with self._lock:
            self._histories[id(state)] = (
                state,
                tla_bridge.history_of(self.document, state),
                _paths_in(self.document),
            )

    def forget_all_but(self, states: Iterable[dict[str, Any]]) -> None:
        """Forgets the history kept for any state but these, which undo keeps."""
        kept = {id(state) for state in states}
        with self._lock:
            for key in self._histories.keys() - kept:
                del self._histories[key]

    def write(self, path: str | Path) -> None:
        """Writes the document to `path` through the core. Under the lock, so that a
        copy for writing never sees the document part-way through following the
        file. The timelines `removed` holds follow the file too, as the document's
        do, through the core's path handler, so that a PDF timeline an undo gives
        back after a Save As, or a save through a link to a file elsewhere, still
        names its PDF, and one read with an absolute path keeps it; and so do the
        paths kept for undo, so that one an undo gives back names its file.
        Raises what `tla.write` raises, having changed nothing."""
        with self._lock:
            held = [
                item for item in self.removed.values() if isinstance(item, tla.Timeline)
            ]
            # The paths as they are now, relative to the folder the document was
            # read from or last written to.
            before = copy.copy(self.document)
            with paths.following(self.document, held, path):
                tla.write(path, self.document)
            # The folder `tla.write` rebases to: that of the file a link names.
            self._rebase_kept_paths(before, paths.paths_folder(path))

    def _rebase_kept_paths(self, before: tla.Document, folder: str) -> None:
        """Makes the paths kept for undo follow the write of `before` into `folder`
        that has just been made, as the document's own do: each is what the core
        would have stored had `before` held it."""
        # One rebase for the many states that hold the same paths.
        rebased: dict[tuple[tuple[str, Any], ...], _Paths] = {}
        other = copy.copy(before)
        for key, (state, history, kept) in list(self._histories.items()):
            other.media_path, other.timelines = kept
            held = tuple(paths.stored_paths(other))
            if held not in rebased:
                written = paths.rebase_paths(other, folder)
                rebased[held] = (written.media_path, written.timelines)
            self._histories[key] = (state, history, rebased[held])

    def note_media_length(self, length: float) -> None:
        """Takes `length`, the player's report for the media the file already has,
        within the tolerance of the stored one, as what the document reflects: so it
        is no change, and the stored length stays (FR-034)."""
        with self._lock:
            if self.synced is None:
                return
            media_metadata = {**self.synced["media_metadata"], _MEDIA_LENGTH: length}
            # A new dict: undo may keep the old one in a state it records.
            self.synced = {**self.synced, "media_metadata": media_metadata}

    def note_media_found(self, path: str) -> None:
        """Takes `path`, where TiLiA found the media the file stores, or "" when the
        user declined to look for it, as where the file's media is: so it is no
        change, and the file keeps the path it stores (FR-032). Loading other media
        is a change, which `sync` writes."""
        with self._lock:
            self.media_path = path
            if self.synced is not None:
                # A new dict: undo may keep the old one in a state it records.
                self.synced = {**self.synced, "media_path": path}

    def note_unstored_timeline(self, timeline_id: str, state: dict[str, Any]) -> None:
        """Takes a timeline TiLiA shows and the document doesn't store, such as the
        slider of a new file, with `state`, its state, as what the document reflects:
        so it is no change, and the document stores it only once it differs
        (FR-007)."""
        with self._lock:
            if self.synced is None:
                return
            timelines = {**self.synced["timelines"], timeline_id: state}
            # A new dict: undo may keep the old one in a state it records.
            self.synced = {**self.synced, "timelines": timelines}

    def copy_for_writing(self) -> tla.Document:
        """A copy of the document, to write elsewhere: a write makes the document it
        is given follow the file written, and the one open must stay with its file."""
        with self._lock:
            return copy.deepcopy(self.document)


def _paths_in(doc: tla.Document) -> _Paths:
    """The paths `doc` holds, copied."""
    return doc.media_path, {
        timeline_id: tla.Timeline(
            id=timeline.id,
            kind=timeline.kind,
            ordinal=timeline.ordinal,
            attrs={
                attr: value
                for attr, value in timeline.attrs.items()
                if attr in paths.TIMELINE_PATHS[timeline.kind]
            },
        )
        for timeline_id, timeline in doc.timelines.items()
        if timeline.kind in paths.TIMELINE_PATHS
    }


def _give_back_paths(
    doc: tla.Document, kept: _Paths, state: dict[str, Any], back_to: dict[str, Any]
) -> None:
    """Gives `doc` back the paths it held in `back_to`, which an undo or a redo has
    brought TiLiA back to, as `state`. `apply_changes` took them from the state, where
    each is the file TiLiA found, or "" for media it didn't. A timeline's stays the
    state's where that isn't the one it was: asked about a PDF that is no longer
    there, the user has picked another."""
    doc.media_path, timelines = kept
    for timeline_id in doc.timelines.keys() & timelines.keys():
        then = back_to["timelines"].get(timeline_id, {})
        now = state["timelines"].get(timeline_id, {})
        for attr, path in timelines[timeline_id].attrs.items():
            if now.get(attr) == then.get(attr):
                doc.timelines[timeline_id].attrs[attr] = path
