"""Score timelines in old files: their SVG, kept as a legacy score.

TiLiA 0.x stored a score timeline's score as the SVG its viewer drew
(`svg_data`), with the viewer's beat positions (`viewer_beat_x`, an object
from each beat's position, as a number written as text, to its x). The
migration moves both out of the timeline into a score of the file's
`scores`, of the format `svg-osmd-legacy`, which the timeline names in
`score` (FR-022): the SVG as its lines (FR-132), and the beat positions as
`beat_x`, `[time, x]` pairs in time order. A legacy score has no `source` or
`license`: TiLiA never recorded them. The timeline keeps its components,
which only a legacy score has. The SVG is text: it is never parsed (FR-135).

A score timeline whose `svg_data` is empty, or null, has no score imported
yet: it gets no score and no `score` key.
"""

from __future__ import annotations

import json
import math
import os
import re
from operator import itemgetter
from typing import Any

from tilia_core.tla.errors import UnreadableFile, printable
from tilia_core.tla.ids import migrated_id
from tilia_core.tla.layout import pointer_to
from tilia_core.tla.model import TIMELINE_KINDS, score_lines

LEGACY_FORMAT = "svg-osmd-legacy"
_SCORE_TIMELINE = TIMELINE_KINDS["score"]
# A number as JSON writes it, and so as TiLiA wrote a beat's position, a
# Python float, as a key of viewer_beat_x.
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def to_legacy_scores(
    content: dict[str, Any], *, version: str, path: str | os.PathLike[str] | None
) -> None:
    """Move each score timeline's SVG and beat positions into a legacy score
    of `content["scores"]`, changing `content` in place.

    `content` is an old file's, in the current format but with the old ids:
    each score takes its timeline's old id, which `name_by_new_ids` replaces
    once the document id is derived. Raises `UnreadableFile`, naming the
    place in the old file, for a shape TiLiA never writes, which the
    migration can't convert (TimeLineAnnotator/project-management#359).
    """
    scores = []
    for key, timeline in content["timelines"].items():
        if timeline["kind"] != _SCORE_TIMELINE:
            continue
        score = _Timeline(key, timeline, version, path).legacy_score()
        if score is not None:
            scores.append(score)
    # In id order, as the file holds them, so that the document id doesn't
    # depend on the timelines' order.
    content["scores"] = sorted(scores, key=itemgetter("id"))


def name_by_new_ids(content: dict[str, Any], document_id: str) -> None:
    """Give each legacy score its new id, derived from its timeline's old id
    and position as the timeline's own is, and name it so in its timeline.
    `content` still has the old ids, and is changed in place. The reader
    puts the scores in the order of their new ids."""
    positions = {key: position for position, key in enumerate(content["timelines"])}
    for score in content["scores"]:
        old_id = score["id"]
        score["id"] = migrated_id(
            document_id, "score", old_id, position=positions[old_id]
        )
        content["timelines"][old_id]["score"] = score["id"]


class _Timeline:
    """One old score timeline, already in the current format but for its
    `svg_data` and `viewer_beat_x`."""

    def __init__(
        self,
        key: str,
        timeline: dict[str, Any],
        version: str,
        path: str | os.PathLike[str] | None,
    ) -> None:
        self.key = key
        self.timeline = timeline
        self.version = version
        self.path = path
        self.place = pointer_to("/timelines", key)

    def _refuse(self, message: str, place: str) -> UnreadableFile:
        return UnreadableFile(message, path=self.path, place=place)

    def legacy_score(self) -> dict[str, Any] | None:
        """The timeline's legacy score, under its timeline's old id, which the
        timeline then names; None when it has no SVG."""
        timeline = self.timeline
        svg = timeline.pop("svg_data", None)
        if svg is not None and not isinstance(svg, str):
            at = pointer_to(self.place, "svg_data")
            raise self._refuse(f"expected text at {at}", at)
        if not svg:
            # No score imported yet. Beat positions without their SVG, which
            # only a file edited by hand holds, stay as they are.
            if timeline.get("viewer_beat_x") in (None, {}):
                timeline.pop("viewer_beat_x", None)
            return None
        beat_x = self._beat_x(timeline.pop("viewer_beat_x", None))
        timeline["score"] = self.key
        return {
            "id": self.key,
            "format": LEGACY_FORMAT,
            "content": score_lines(svg),
            "beat_x": beat_x,
        }

    def _beat_x(self, positions: Any) -> list[list[Any]]:
        """`viewer_beat_x` as `[time, x]` pairs in time order; none when it is
        missing or null, TiLiA's default until its viewer draws the score."""
        place = pointer_to(self.place, "viewer_beat_x")
        if positions is None:
            return []
        if not isinstance(positions, dict):
            raise self._refuse(f"expected an object at {place}", place)
        pairs = []
        for key, x in positions.items():
            at = pointer_to(place, key)
            time = _time(key)
            if time is None:
                name = printable(json.dumps(key, ensure_ascii=False))
                raise self._refuse(f"{name} in viewer_beat_x isn't a number", at)
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise self._refuse(f"expected a number at {at}", at)
            pairs.append([time, x])
        # By value: in text order, "10.0" would come before "2.0". Two keys
        # with one value, which TiLiA never wrote, keep the file's order.
        pairs.sort(key=itemgetter(0))
        return pairs


def _time(key: str) -> float | None:
    """A beat's position, as TiLiA reads it with float(), from a key written
    as JSON writes a number; None for anything else, or a number too large."""
    if not _JSON_NUMBER.fullmatch(key):
        return None
    time = float(key)
    return time if math.isfinite(time) else None
