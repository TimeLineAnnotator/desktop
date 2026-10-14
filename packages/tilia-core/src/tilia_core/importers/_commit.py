"""The one step in which an import changes the document.

An importer reads the whole file and builds the new components apart from the
document, then calls `commit` once; so an import that fails before it changes
nothing.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Iterable
from typing import Any

from tilia_core import rules, tla


def commit(
    document: tla.Document,
    target_id: str,
    components: Iterable[tla.Component],
    *,
    rows: list[dict[str, Any]] | None = None,
    attrs: dict[str, Any] | None = None,
) -> None:
    """Replace the target's components with `components`, in their order.

    `rows`, for a range timeline, replace its rows; with none left, it gets one
    blank row, as TiLiA restores it. `attrs` are set on the target, replacing
    the values it had.
    """
    timeline = document.timelines[target_id]
    timeline.components = {component.id: component for component in components}
    if rows is not None:
        timeline.attrs["rows"] = list(rows) if rows else [blank_row()]
    if attrs:
        timeline.attrs.update(attrs)


def new_row_id(taken: Collection[str]) -> str:
    """A range row's id: six letters and digits, none of `taken`, as TiLiA makes them."""
    while True:
        row_id = "".join(random.choices(rules.ROW_ID_CHARACTERS, k=rules.ROW_ID_LENGTH))
        if row_id not in taken:
            return row_id


def blank_row() -> dict[str, Any]:
    """The row a range timeline gets when it has none (`RangeTimeline.setup_blank_timeline`)."""
    return {"id": new_row_id(()), "name": "Row 0", "color": None, "height": None}
