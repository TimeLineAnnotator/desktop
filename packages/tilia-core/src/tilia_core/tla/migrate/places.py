"""Where each place of a migrated document was in the old file.

The migration keeps each new id's old id, and where each key it moved or
renamed was, so that what the check after the migration refuses or warns
about is named in the old file's terms: the place there, with the old ids,
whose line the reader then finds in the old file's bytes
(TimeLineAnnotator/project-management#347). It also keeps each reference
the new ids couldn't follow, which names nothing, with its old value.

Places are JSON Pointers (RFC 6901).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from tilia_core.tla.errors import printable
from tilia_core.tla.parse import pointer


def _step(key: str) -> str:
    """A key as a step of a JSON Pointer."""
    return pointer([key])[1:]


def _name(place: str) -> str:
    """The key the last step of a JSON Pointer names."""
    return place.rpartition("/")[2].replace("~1", "/").replace("~0", "~")


def _quoted(value: Any) -> str:
    return printable(json.dumps(value, ensure_ascii=False))


# Where what the migration moves to the top level was in every old file.
_TOP_LEVEL = {
    "/media/path": "/media_path",
    "/media/length": "/media_metadata/media length",
    "/metadata": "/media_metadata",
}


class OldPlaces:
    """Maps a place in a migrated document to the place in the old file that
    it comes from. It knows from the start where the top level's keys were;
    the migration tells it the rest."""

    def __init__(self) -> None:
        # Each timeline's old id, and its components' new ids by their old
        # ones, as the migration made them, by the timeline's new id, a UUID,
        # which a pointer writes as it is. Nothing is done for each component
        # on every read: the ids are turned around, by timeline, only for a
        # place asked for.
        self._timelines: dict[str, tuple[str, Mapping[str, str]]] = {}
        self._old_ids: dict[str, dict[str, str]] = {}
        # Where each key the migration moved or renamed was in the old file,
        # by its place as the migration leaves it, with the old ids.
        self._moved: dict[str, str] = dict(_TOP_LEVEL)
        # Each reference that names nothing, by its place in the migrated
        # document, with its value in the old file.
        self._nothing: dict[str, Any] = {}

    def timeline(
        self, new_id: str, old_id: str, components: Mapping[str, str] | None = None
    ) -> None:
        """The timeline `new_id`, a UUID, was `old_id` in the old file, and
        `components` gives the new id of each of its components by its old
        one; it is kept as it is given."""
        self._timelines[new_id] = (old_id, {} if components is None else components)

    def moved(self, place: str, old_place: str) -> None:
        """What is at `place` once migrated, named with the old ids, was at
        `old_place` in the old file, and so was what it holds: `place`'s
        `/x` was at `old_place`'s `/x`."""
        self._moved[place] = old_place

    def names_nothing(self, place: str, reference: Any) -> None:
        """The reference at `place` in the migrated document, `reference` in
        the old file, names nothing the new ids could follow it to; the
        check refuses it there, as a reference that names nothing."""
        self._nothing[place] = reference

    def old(self, place: str) -> str:
        """The place in the old file of `place`, a place in the migrated
        document: its new ids made the old ones again, then a key the
        migration moved put back where it was. A place the old file doesn't
        have, such as a key the migration added, is given as it is."""
        return self._back(place)[0]

    def _back(self, place: str) -> tuple[str, tuple[str, str, bool] | None]:
        """The old place of `place`; and when it is in a key the migration
        moved, that key's name once migrated and in the old file, and
        whether `place` is the key's own."""
        steps = place.split("/")  # "" first: a pointer starts with "/"
        if len(steps) > 2 and steps[1] == "timelines" and steps[2] in self._timelines:
            timeline = steps[2]
            old_id, components = self._timelines[timeline]
            steps[2] = _step(old_id)
            if len(steps) > 4 and steps[3] == "components":
                old_ids = self._old_ids.get(timeline)
                if old_ids is None:
                    old_ids = {new: old for old, new in components.items()}
                    self._old_ids[timeline] = old_ids
                if steps[4] in old_ids:
                    steps[4] = _step(old_ids[steps[4]])
        place = "/".join(steps)
        held = place
        while held:
            if held in self._moved:
                old = self._moved[held]
                names = (_name(held), _name(old), held == place)
                return old + place[len(held) :], names
            held = held.rpartition("/")[0]
        return place, None

    def in_old_file(self, place: str, message: str) -> tuple[str, str]:
        """`place`, a place in the migrated document, and a message the
        check gives about what is there, as the old file has them: the
        place there; a key the migration renamed by the name the old file
        gives it (`"display_position" should be …`, not `"ordinal" …`); and a
        reference that names nothing as the old file writes it
        (`"joined_right" names nothing: "99"`), not as the UUID the
        migration put in its place."""
        old, moved = self._back(place)
        if place in self._nothing:
            key = _name(old)
            return old, f"{_quoted(key)} names nothing: {_quoted(self._nothing[place])}"
        if moved is not None and moved[0] != moved[1]:
            # The check's messages start with what they are about: the key,
            # or an item of the nearest key's value.
            name, old_name, own = moved
            about = "" if own else "an item of "
            subject = f"{about}{_quoted(name)} "
            if message.startswith(subject):
                message = f"{about}{_quoted(old_name)} {message[len(subject) :]}"
        return old, message
