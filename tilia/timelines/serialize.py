from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.requests import post, Post
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

    SERIALIZABLE_BY_VALUE: list[str]
    SERIALIZABLE_BY_ID: list[str]
    SERIALIZABLE_BY_ID_LIST: list[str]


def serialize_components(
    components: set[Serializable] | list[Serializable],
) -> dict[int, dict[str]]:
    serialized_components = {}
    for component in components:
        serialized_components[component.id] = serialize_component(component)

    return serialized_components


def serialize_component(component: Serializable) -> dict[str]:
    serialized_component = {}

    # serialize attributes by value
    for attr in component.SERIALIZABLE_BY_VALUE:
        if isinstance(value := getattr(component, attr), list):
            value = value.copy()
        serialized_component[attr] = value

    # serialize attributes by id
    for attr in component.SERIALIZABLE_BY_ID:
        if attr_value := getattr(component, attr):
            serialized_component[attr] = attr_value.id
        else:
            serialized_component[attr] = None

    # serialize attributes by id list
    for attr in component.SERIALIZABLE_BY_ID_LIST:
        if attr_value := getattr(component, attr):
            serialized_component[attr] = [component.id for component in attr_value]
        else:
            serialized_component[attr] = []

    # add component kind to serialized component
    serialized_component["kind"] = component.KIND.name

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

    _substitute_ids_for_reference_to_components(id_to_component_dict)


def _deserialize_component(
    timeline: Timeline, serialized_component: dict[str]
) -> tuple[TimelineComponent, str]:
    """Creates the serialized TimelineComponent in the given timeline.
    Attributes that originally referenced other TimelineComponents are
    , in this stage, set as references to save ids."""

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

    if component:
        # attributes that are serializable by id or by id list get set separatedly
        _set_serializable_by_id_or_id_list(component, serialized_component)

    return component, fail_reason


def _get_component_constructor_kwargs(
    serialized_component: dict, component_class
) -> dict:
    return {
        k: v
        for k, v in serialized_component.items()
        if k in component_class.SERIALIZABLE_BY_VALUE
    }


def _set_serializable_by_id_or_id_list(component, serialized_component: dict) -> None:
    component_class = type(component)
    for attr in (
        component_class.SERIALIZABLE_BY_ID + component_class.SERIALIZABLE_BY_ID_LIST
    ):
        setattr(component, attr, serialized_component[attr])


def _substitute_ids_for_reference_to_components(
    id_to_component: dict[id, TimelineComponent]
) -> None:

    for id_, component in id_to_component.items():
        component_class = type(component)

        for attr in component_class.SERIALIZABLE_BY_ID:
            if attr_as_id := getattr(component, attr):
                setattr(component, attr, id_to_component[attr_as_id])

        for attr in component_class.SERIALIZABLE_BY_ID_LIST:
            if attr_as_id_list := getattr(component, attr):
                setattr(
                    component,
                    attr,
                    [id_to_component[id_] for id_ in attr_as_id_list],
                )
