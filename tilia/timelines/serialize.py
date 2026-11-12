from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent
    from tilia.timelines.base.timeline import Timeline
    from tilia.ui.timelines.base.element import TimelineUIElement

from typing import Protocol

from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind


def id_order(id: str) -> tuple[int, str]:
    """Sort key that puts ids in the order they were made, both UUIDv7s and
    numbers as text.
    """
    return len(id), id


class Serializable(Protocol):
    id: str
    ui: TimelineUIElement
    KIND: ComponentKind
    hash: str

    SERIALIZABLE: list[str]


def serialize_components(
    components: set[Serializable] | list[Serializable],
) -> dict[str, dict[str]]:

    result = {}
    for c in sorted(components, key=lambda c: id_order(c.id)):
        result[c.id] = serialize_component(c)

    return result


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
    timeline: Timeline, serialized_components: dict[str, dict[str]]
):
    """Creates the given serialized components in 'timeline', as they are: none is
    checked, so that a component that breaks a rule is kept, as the reader keeps it,
    and its time is the one stored, even past the media's end."""
    for id, serialized_component in serialized_components.items():
        _deserialize_component(timeline, id, serialized_component)


def _deserialize_component(
    timeline: Timeline, id: str, serialized_component: dict[str]
) -> TimelineComponent:
    """Creates the serialized TimelineComponent in the given timeline."""

    component_kind = ComponentKind[serialized_component["kind"]]
    component_class = get_component_class_by_kind(component_kind)

    # directly serializable attrs go into constructor
    constructor_kwargs = _get_component_constructor_kwargs(
        serialized_component, component_class
    )

    component, _ = timeline.create_component(
        component_kind, **constructor_kwargs, id=id, checked=False
    )

    return component


def _get_component_constructor_kwargs(
    serialized_component: dict, component_class
) -> dict:
    return {
        k: v
        for k, v in serialized_component.items()
        if k in component_class.SERIALIZABLE
    }
