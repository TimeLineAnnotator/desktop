"""The file open in TiLiA: what `FileManager.file` is."""

from __future__ import annotations

import copy
import os
import threading
import unicodedata
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
    then held that the state can't tell (`tla_bridge.history_of`, and the media's path
    as the file stores it), and an undo or a redo back to that state gives it back.

    `media_path` is where the media was found, not the path the file stores
    (`note_media_found`), when the file was last read or saved.
    `stored_media_path` is the path the file then had: media a person picks
    since (`take_media`) is an unsaved change when a save would store another.
    `timelines` and `timelines_hash` are the state's when the file was last read or
    saved. `unknown_discarded` says timelines of kinds TiLiA doesn't know were taken
    out of the document, so that the file reads as modified until it is saved.

    Two are the same file only if they are the same object.
    """

    document: tla.Document | None = None
    file_path: str = ""
    media_path: str = ""
    stored_media_path: str = field(default="", init=False)
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
    # media's path as the document then held it, which the state can't tell: the
    # state holds where the media was found, or "" when it wasn't.
    _histories: dict[int, tuple[dict[str, Any], tla_bridge.History, str]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.document is not None:
            self.stored_media_path = self.document.media_path
        else:
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
                # The media's path the file stored then, which `apply_changes` took
                # from the state: where the media was found, or "" when it wasn't.
                if self.document.media_path != remembered[2]:
                    self.document.media_path = remembered[2]
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
                tla_bridge.history_of(self.document),
                self.document.media_path,
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
        media paths kept for undo, so that one an undo gives back names the media.
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
            self._rebase_kept_media_paths(before, paths.paths_folder(path))

    def _rebase_kept_media_paths(self, before: tla.Document, folder: str) -> None:
        """Makes the media paths kept for undo those the file just written from
        `before` stores, relative to `folder`, as the document's own is: the one
        the document held is what the core wrote, and any other is rebased as the
        core would have written it."""
        written = {before.media_path: self.document.media_path}
        for key, (state, history, media_path) in list(self._histories.items()):
            if media_path not in written:
                other = copy.copy(before)
                other.timelines = {}
                other.media_path = media_path
                written[media_path] = paths.rebase_paths(other, folder).media_path
            self._histories[key] = (state, history, written[media_path])

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

    def take_media(self, media_path: str) -> None:
        """Makes `media_path`, media a person picked and TiLiA has loaded, the file's,
        also when it is the media TiLiA had found elsewhere
        (TimeLineAnnotator/project-management#688, a). The document stores its place
        or, for media that is where the file says, however either spells it, the path
        the file has."""
        with self._lock:
            given = tla.as_media_path(media_path)
            self.document.media_path = (
                self.stored_media_path if self._is_where_the_file_says(given) else given
            )
            if self.synced is not None:
                # A new dict: undo may keep the old one in a state it records.
                self.synced = {**self.synced, "media_path": media_path}

    def stores_other_media(self, media_path: str) -> bool:
        """Whether a save would store another media path than the file has, with
        `media_path` in TiLiA's state: what makes media an unsaved change."""
        with self._lock:
            to_store = self.document.media_path
            if self.synced is not None and media_path != self.synced["media_path"]:
                to_store = tla.as_media_path(media_path)  # as a sync takes it
            if to_store == self.stored_media_path:
                return False
            if not self.file_path:
                return True
            # As the core would write it into the file's folder.
            other = copy.copy(self.document)
            other.timelines = {}
            other.media_path = to_store
            written = paths.rebase_paths(other, paths.paths_folder(self.file_path))
            return written.media_path != self.stored_media_path

    def media_place(self) -> str:
        """Where the document says its media is, whether it is there or not: the same
        for any spelling, so that a save doesn't change it. A link is as it is, and ""
        is none."""
        with self._lock:
            path = self.document.media_path
            return self._place_of(path) or path

    def _is_where_the_file_says(self, given: str) -> bool:
        """Whether `given`, a path of media that is there, as `as_media_path` gives it,
        is where the file says its media is. A link to it is another place."""
        said, picked = self._place_of(self.stored_media_path), self._place_of(given)
        if said == picked:
            return bool(said)
        texts = {
            unicodedata.normalize("NFC", path).casefold() for path in (said, picked)
        }
        if not said or len(texts) > 1:
            return False
        # One file, where the file system ignores letter case or Unicode's form.
        found = paths.stored_file_of(self.document, self.stored_media_path)
        try:
            return found is not None and os.path.samefile(found, given)
        except OSError:  # gone since
            return False

    def _place_of(self, media_path: str) -> str:
        """Where `media_path`, as the document stores it, says the media is: absolute,
        by its text alone. "" for a link, for none, and for another system's path."""
        if not media_path or tla.media_files.is_url(media_path):
            return ""
        if tla.media_files.absolute_form(media_path) not in (
            None,
            tla.media_files.SYSTEM,
        ):
            return ""
        folder = paths.paths_folder_of(self.document) or ""
        return os.path.normcase(os.path.abspath(os.path.join(folder, media_path)))

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

    def copy_for_writing(self) -> tla.Document:
        """A copy of the document, to write elsewhere: a write makes the document it
        is given follow the file written, and the one open must stay with its file."""
        with self._lock:
            return copy.deepcopy(self.document)
