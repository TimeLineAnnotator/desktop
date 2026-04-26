from __future__ import annotations

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


@dataclass
class CopyAttributes:
    values: list[str]
    context: list[str]
