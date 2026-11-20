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
    then held that the state can't tell (`tla_bridge.history_of`), and an undo or a
    redo back to that state gives it back.

    `media_path` is where the media was found, not the path the file stores.
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
    # By the id of a state undo recorded: that state, and the document's history.
    _histories: dict[int, tuple[dict[str, Any], tla_bridge.History]] = field(
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
            self.synced = state
        for note in notes:
            logger.warning(note)

    def remember(self, state: dict[str, Any]) -> None:
        """Keeps, for `state`, which undo has just recorded and the document follows,
        what the document holds that the state can't tell, for an undo or a redo
        back to it."""
        with self._lock:
            self._histories[id(state)] = (state, tla_bridge.history_of(self.document))

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
        names its PDF, and one read with an absolute path keeps it. Raises what
        `tla.write` raises, having changed nothing."""
        with self._lock:
            held = [
                item for item in self.removed.values() if isinstance(item, tla.Timeline)
            ]
            with paths.following(self.document, held, path):
                tla.write(path, self.document)

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

    def component_fields(
        self, timeline_id: str, component_id: str
    ) -> dict[str, str | list[str]]:
        """A copy of the fields of a component the document holds, which TiLiA shows
        but doesn't edit (FR-092). Empty for a component it doesn't hold, such as one
        TiLiA doesn't store or has made since its last action."""
        with self._lock:
            timeline = self.document.timelines.get(timeline_id)
            component = timeline.components.get(component_id) if timeline else None
            return copy.deepcopy(component.metadata) if component else {}

    def copy_for_writing(self) -> tla.Document:
        """A copy of the document, to write elsewhere: a write makes the document it
        is given follow the file written, and the one open must stay with its file."""
        with self._lock:
            return copy.deepcopy(self.document)
