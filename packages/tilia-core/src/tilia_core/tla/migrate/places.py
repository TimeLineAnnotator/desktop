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
from typing import Any

from tilia_core.tla.errors import printable
from tilia_core.tla.parse import pointer


def _step(key: str) -> str:
    """A key as a step of a JSON Pointer."""
    return pointer([key])[1:]


def _key(step: str) -> str:
    """The key a step of a JSON Pointer names."""
    return step.replace("~1", "/").replace("~0", "~")


def _quoted(value: Any) -> str:
    return printable(json.dumps(value, ensure_ascii=False))


class OldPlaces:
    """Maps a place in a migrated document to the place in the old file that
    it comes from."""

    def __init__(self) -> None:
        # The old id of each timeline, by its new id, and of each of its
        # components, by the timeline's new id and the component's; all as
        # steps of a pointer.
        self._timelines: dict[str, str] = {}
        self._components: dict[str, dict[str, str]] = {}
        # Where each key the migration moved or renamed was in the old file,
        # by its place as the migration leaves it, with the old ids.
        self._moved: dict[str, str] = {}
        # Each reference that names nothing, by its place in the migrated
        # document, with its value in the old file.
        self._nothing: dict[str, Any] = {}

    def timeline(self, new_id: str, old_id: str) -> None:
        """The timeline `new_id` was `old_id` in the old file."""
        self._timelines[_step(new_id)] = _step(old_id)

    def component(self, timeline_id: str, new_id: str, old_id: str) -> None:
        """The component `new_id`, of the timeline whose new id is
        `timeline_id`, was `old_id` in the old file."""
        components = self._components.setdefault(_step(timeline_id), {})
        components[_step(new_id)] = _step(old_id)

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
        steps = place.split("/")  # "" first: a pointer starts with "/"
        if len(steps) > 2 and steps[1] == "timelines":
            timeline = steps[2]
            steps[2] = self._timelines.get(timeline, timeline)
            if len(steps) > 4 and steps[3] == "components":
                components = self._components.get(timeline, {})
                steps[4] = components.get(steps[4], steps[4])
        place = "/".join(steps)
        held = place
        while held:
            if held in self._moved:
                return self._moved[held] + place[len(held) :]
            held = held.rpartition("/")[0]
        return place

    def in_old_file(self, place: str, message: str) -> tuple[str, str]:
        """`place`, a place in the migrated document, and a message the
        check gives about what is there, as the old file has them: the
        place there, and a reference that names nothing named as the old
        file writes it (`"joined_right" names nothing: "99"`), not as the
        UUID the migration put in its place."""
        old = self.old(place)
        if place in self._nothing:
            key = _key(old.rpartition("/")[2])
            message = f"{_quoted(key)} names nothing: {_quoted(self._nothing[place])}"
        return old, message
