from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tilia.ui.timelines.base.element import TimelineUIElement


def get_copy_data_from_elements(
    elements: list[tuple[TimelineUIElement, CopyAttributes]],
) -> list[dict]:
    copy_data = []
    for element, copy_attrs in elements:
        copy_data.append(get_copy_data_from_element(element, copy_attrs))

    return copy_data


def get_copy_data_from_element(
    element: TimelineUIElement, copy_attrs: CopyAttributes
) -> dict:
    values = {}
    for attr in copy_attrs.values:
        values[attr] = element.get_data(attr)

    context = {}
    for attr in copy_attrs.context:
        context[attr] = getattr(element.tl_component, attr)

    copy_data = {
        "values": values,
        "context": context,
    }

    return copy_data


def paste_into_element(element: TimelineUIElement, paste_data: dict[str, Any]):
    for attr, value in paste_data["values"].items():
        if element is None:
            pass
        element.set_data(attr, value)


def fitted_time(
    source_start: float,
    source_end: float,
    target_start: float,
    target_end: float,
) -> Callable[[float], float]:
    """The affine map from the copied components' timespan to the target's, as a
    paste fits them into it: a hierarchy's subtree, or ranges pasted onto one.

    The whole paste shares one map, so a time that appears in several copied
    components — as one's end and the next one's start — maps to the same float
    in all of them and coincident boundaries stay coincident. Deriving a scale
    factor separately per component, or anchoring starts and ends to different
    reference points, lets those boundaries drift apart by a few ulps, which later
    reads as an overlap, or a join that doesn't hold.
    """
    scale_factor = (target_end - target_start) / (source_end - source_start)

    def map_time(time: float) -> float:
        # Anchor the endpoints exactly: scaling them arithmetically can land a
        # ulp off, misaligning the paste with the target.
        if time == source_start:
            return target_start
        if time == source_end:
            return target_end
        return (time - source_start) * scale_factor + target_start

    return map_time


@dataclass
class CopyAttributes:
    values: list[str]
    context: list[str]
