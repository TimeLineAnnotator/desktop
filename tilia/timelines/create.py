from __future__ import annotations

from tilia.timelines.collection import TimelineCollection
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.collection import TimelineUICollection


def create_timeline(
    timeline_kind: TimelineKind,
    timeline_collection: TimelineCollection,
    timeline_ui_collection: TimelineUICollection,
    name: str = "",
    components: dict[int] = None,
    **kwargs,
):
    _validate_timeline_kind(timeline_kind)

    timeline = timeline_collection.create_timeline(timeline_kind, **kwargs)
    timeline_ui = timeline_ui_collection.create_timeline_ui(
        timeline_kind, name, **kwargs
    )

    timeline.ui = timeline_ui
    timeline_ui.timeline = timeline

    if components:
        timeline.component_manager.deserialize_components(components)
    else:
        if timeline_kind == TimelineKind.HIERARCHY_TIMELINE:
            timeline.component_manager.create_initial_hierarchy()  # TODO temporary workaround. Make this into an user action.


def _validate_timeline_kind(timeline_kind: TimelineKind):
    if not isinstance(timeline_kind, TimelineKind):
        raise ValueError(
            f"Can't create timeline: invalid timeline kind '{timeline_kind}'"
        )
