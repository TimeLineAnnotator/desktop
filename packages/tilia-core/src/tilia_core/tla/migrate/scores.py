"""Score timelines in old files: their SVG, kept as a legacy score.

TiLiA 0.x stored a score timeline's score as the SVG its viewer drew
(`svg_data`), with the viewer's beat positions (`viewer_beat_x`). The
migration moves both out of the timeline into a score of the file's
`scores`, of the format `svg-osmd-legacy`, which the timeline names in
`score` (FR-022): the SVG as its lines (FR-132), and the beat positions as
`beat_x`, `[position, x]` pairs in the order of their positions. A beat's
position is a place in the score, not a time: the measure number plus the
fraction of the measure, as TiLiA's viewer computes it, which TiLiA turns
into a time through the beat timeline; `x` is the beat's x coordinate in
the SVG. A legacy score has no `source` or `license`: TiLiA never recorded
them. The timeline keeps its components, which only a legacy score has. The
SVG is text: it is never parsed (FR-135).

A score timeline whose `svg_data` is empty, or null, has no score imported
yet: it gets no score and no `score` key.

Shapes TiLiA never writes, which only a file edited by hand holds, are
refused, naming the place in the old file, as
TimeLineAnnotator/project-management#359 (old score timelines TiLiA never
wrote) recommends, pending its decision.
"""

from __future__ import annotations

import json
import math
import re
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from tilia_core.tla.errors import printable
from tilia_core.tla.layout import pointer_to
from tilia_core.tla.migrate import to_1
from tilia_core.tla.model import score_lines

if TYPE_CHECKING:
    from tilia_core.tla.migrate.to_1 import _Migration

LEGACY_FORMAT = "svg-osmd-legacy"
# A number as JSON writes it, and so as TiLiA wrote a beat's position, a
# Python float, as a key of viewer_beat_x.
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def legacy_score(
    migration: _Migration, key: str, timeline: dict[str, Any]
) -> dict[str, Any] | None:
    """The legacy score of an old score timeline, already in the current
    format but for its `svg_data` and `viewer_beat_x`, which leave it: under
    the timeline's old id, `key`, which the timeline then names, and which
    the new ids replace once the document id is derived. None when the
    timeline has no SVG. Raises `UnreadableFile`, naming the place in the
    old file, for a shape TiLiA never writes."""
    place = pointer_to("/timelines", key)
    if timeline.get("svg_data") is not None:
        migration._text(timeline, "svg_data", place)
    svg = timeline.pop("svg_data", None)
    if not svg:
        # No score imported yet. Beat positions without their SVG, which
        # only a file edited by hand holds, stay as they are.
        if timeline.get("viewer_beat_x") in (None, {}):
            timeline.pop("viewer_beat_x", None)
        return None
    positions = timeline.pop("viewer_beat_x", None)
    beat_x = _beat_x(migration, positions, pointer_to(place, "viewer_beat_x"))
    timeline["score"] = key
    return {
        "id": key,
        "format": LEGACY_FORMAT,
        "content": score_lines(svg),
        "beat_x": beat_x,
    }


def in_old_id_order(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The legacy scores, still under their timelines' old ids, in the order
    of those ids, so that the timelines' order in the old file doesn't change
    the document id."""
    return sorted(scores, key=itemgetter("id"))


def _beat_x(migration: _Migration, positions: Any, place: str) -> list[list[Any]]:
    """`viewer_beat_x` as `[position, x]` pairs in the order of their
    positions; none when it is missing or null, TiLiA's default until its
    viewer draws the score."""
    if positions is None:
        return []
    migration._object(positions, place)
    pairs = []
    for key, x in positions.items():
        at = pointer_to(place, key)
        position = _position(key)
        if position is None:
            name = printable(json.dumps(key, ensure_ascii=False))
            raise migration._refuse(f"{name} in viewer_beat_x isn't a number", at)
        if not to_1._is_number(x):
            raise migration._refuse(f"expected a number at {at}", at)
        pairs.append([position, x])
    # By value: in text order, "10.0" would come before "2.0".
    pairs.sort(key=itemgetter(0))
    return pairs


def _position(key: str) -> float | None:
    """A beat's position, as TiLiA reads it with float(), from a key written
    as JSON writes a number; None for anything else, or a number too large."""
    if not _JSON_NUMBER.fullmatch(key):
        return None
    position = float(key)
    return position if math.isfinite(position) else None
