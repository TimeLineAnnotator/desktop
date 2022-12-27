from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.ui.timelines.common import TimelineUIElement

from tilia.exceptions import AppException
from tilia.timelines.common import TimelineComponent

import logging


logger = logging.getLogger(__name__)


class CopyError(AppException):
    pass


class PasteError(AppException):
    pass


@runtime_checkable
class Copyable(Protocol):
    DEFAULT_COPY_ATTRIBUTES: CopyAttributes
    tl_component: TimelineComponent


def get_copy_data_from_elements(
    elements: list[tuple[Copyable, CopyAttributes]]
) -> list[dict]:
    copy_data = []
    for element, kind, copy_attrs in elements:
        copy_data.append(get_copy_data_from_element(element, copy_attrs))

    return copy_data


def get_copy_data_from_element(element: Copyable, copy_attrs: CopyAttributes) -> dict:

    by_element_value = {}
    for attr in copy_attrs.by_element_value:
        by_element_value[attr] = getattr(element, attr)

    by_component_value = {}
    for attr in copy_attrs.by_component_value:
        by_component_value[attr] = getattr(element.tl_component, attr)

    support_by_element_value = {}
    for attr in copy_attrs.support_by_element_value:
        support_by_element_value[attr] = getattr(element, attr)

    support_by_component_value = {}
    for attr in copy_attrs.support_by_component_value:
        support_by_component_value[attr] = getattr(element.tl_component, attr)

    copy_data = {
        "by_element_value": by_element_value,
        "by_component_value": by_component_value,
        "support_by_element_value": support_by_element_value,
        "support_by_component_value": support_by_component_value,
    }

    return copy_data


def paste_into_element(element: TimelineUIElement, paste_data: dict[str:Any]):

    logger.debug(f"{element} is receiving paste...")

    for attr, value in paste_data["by_element_value"].items():
        logger.debug(f"Pasting '{attr}' with value= '{value}'.")
        setattr(element, attr, value)

    for attr, value in paste_data["by_component_value"].items():
        logger.debug(f"Pasting '{attr}' with value='{value}'.")
        setattr(element.tl_component, attr, value)


@dataclass
class CopyAttributes:
    by_element_value: list[str]
    by_component_value: list[str]
    support_by_element_value: list[str]
    support_by_component_value: list[str]
