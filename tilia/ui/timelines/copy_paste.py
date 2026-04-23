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
    by_component_value = {}
    for attr in copy_attrs.by_component_value:
        by_component_value[attr] = element.get_data(attr)

    support_by_component_value = {}
    for attr in copy_attrs.support_by_component_value:
        support_by_component_value[attr] = getattr(element.tl_component, attr)

    copy_data = {
        "by_component_value": by_component_value,
        "support_by_component_value": support_by_component_value,
    }

    return copy_data


def paste_into_element(element: TimelineUIElement, paste_data: dict[str, Any]):
    for attr, value in paste_data["by_component_value"].items():
        if element is None:
            pass
        element.set_data(attr, value)


@dataclass
class CopyAttributes:
    by_component_value: list[str]
    support_by_component_value: list[str]
