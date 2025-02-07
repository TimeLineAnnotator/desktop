from __future__ import annotations
from typing import TYPE_CHECKING

import tilia.errors

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent
    from tilia.timelines.base.timeline import Timeline
    from tilia.ui.timelines.base.element import TimelineUIElement

from typing import Protocol

from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind


class Serializable(Protocol):
    id: int
    ui: TimelineUIElement
    KIND: ComponentKind
    hash: str

    SERIALIZABLE: list[str]


def serialize_components(
    components: set[Serializable] | list[Serializable],
) -> dict[int, dict[str]]:

    return {c.id: serialize_component(c) for c in components}


def serialize_component(component: Serializable) -> dict[str]:
    serialized_component = {}

    for attr in component.SERIALIZABLE:
        if isinstance(value := getattr(component, attr), list):
            value = value.copy()
        serialized_component[attr] = value

    serialized_component["kind"] = component.KIND.name
    serialized_component["hash"] = component.hash

    return serialized_component


def deserialize_components(
    timeline: Timeline, serialized_components: dict[int | str, dict[str]]
):
    """Creates the given serialized components in 'timeline'."""

    id_to_component_dict = {}
    errors = []

    for id, serialized_component in serialized_components.items():
        component, error = _deserialize_component(timeline, serialized_component)
        if not component:
            errors.append(f"id={id} | {error}")
            continue

        # Keys will be strings if loading a JSON file.
        # Must convert to int, as id-based attributes
        # are either of type int or list[int].
        id_to_component_dict[int(id)] = component

    if errors:
        errors_str = "\n".join(errors)
        tilia.errors.display(tilia.errors.COMPONENTS_LOAD_ERROR, errors_str)


def _deserialize_component(
    timeline: Timeline, serialized_component: dict[str]
) -> tuple[TimelineComponent, str]:
    """Creates the serialized TimelineComponent in the given timeline."""

    component_kind = ComponentKind[serialized_component["kind"]]
    component_class = get_component_class_by_kind(component_kind)

    # directly serializable attrs go into constructor
    constructor_kwargs = _get_component_constructor_kwargs(
        serialized_component, component_class
    )

    # create component
    component, fail_reason = timeline.create_component(
        component_kind, **constructor_kwargs
    )

    return component, fail_reason


def _get_component_constructor_kwargs(
    serialized_component: dict, component_class
) -> dict:
    return {
        k: v
        for k, v in serialized_component.items()
        if k in component_class.SERIALIZABLE
    }
