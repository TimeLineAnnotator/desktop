"""Where each place of a migrated document was in the old file.

The migration keeps each new id's old id, and where each key it moved or
renamed was, so that what the check after the migration refuses or warns
about is named in the old file's terms: the place there, with the old ids,
whose line the reader then finds in the old file's bytes
(TimeLineAnnotator/project-management#347).

Places are JSON Pointers (RFC 6901).
"""

from __future__ import annotations

from tilia_core.tla.parse import pointer


def _step(key: str) -> str:
    """A key as a step of a JSON Pointer."""
    return pointer([key])[1:]


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
