from dataclasses import dataclass

from tilia.requests import Post
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    NOT_SLIDER,
    COLORED_COMPONENTS,
)
from tilia.ui.timelines.collection.requests.enums import (
    TimelineSelector,
    ElementSelector,
)


@dataclass
class TlElmRequestSelector:
    tl_kind: list[TlKind]
    timeline: TimelineSelector
    element: ElementSelector


request_to_scope: dict[Post, TlElmRequestSelector] = {
    Post.TIMELINE_ELEMENT_COLOR_SET: TlElmRequestSelector(
        COLORED_COMPONENTS,
        TimelineSelector.SELECTED,
        ElementSelector.SELECTED,
    ),
    Post.TIMELINE_ELEMENT_COLOR_RESET: TlElmRequestSelector(
        COLORED_COMPONENTS,
        TimelineSelector.SELECTED,
        ElementSelector.SELECTED,
    ),
    Post.TIMELINE_ELEMENT_DELETE: TlElmRequestSelector(
        NOT_SLIDER,
        TimelineSelector.SELECTED,
        ElementSelector.SELECTED,
    ),
    Post.TIMELINE_ELEMENT_COPY: TlElmRequestSelector(
        NOT_SLIDER,
        TimelineSelector.SELECTED,
        ElementSelector.SELECTED,
    ),
    Post.TIMELINE_ELEMENT_PASTE: TlElmRequestSelector(
        NOT_SLIDER,
        TimelineSelector.PASTE,
        ElementSelector.SELECTED,
    ),
    Post.TIMELINE_ELEMENT_EXPORT_AUDIO: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.MARKER_ADD: TlElmRequestSelector(
        [TlKind.MARKER_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.MARKER_DELETE: TlElmRequestSelector(
        [TlKind.MARKER_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.TIMELINE_NAME_SET: TlElmRequestSelector(
        NOT_SLIDER, TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.BEAT_ADD: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.BEAT_DELETE: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.BEAT_SET_MEASURE_NUMBER: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.BEAT_RESET_MEASURE_NUMBER: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.BEAT_DISTRIBUTE: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.BEAT_SET_AMOUNT_IN_MEASURE: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_INCREASE_LEVEL: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_DECREASE_LEVEL: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_GROUP: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_COLOR_SET: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_COLOR_RESET: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_MERGE: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_CREATE_CHILD: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_SPLIT: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.FIRST, ElementSelector.ALL
    ),
    Post.TIMELINE_ELEMENT_PASTE_COMPLETE: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_ADD_PRE_START: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HIERARCHY_ADD_POST_END: TlElmRequestSelector(
        [TlKind.HIERARCHY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HARMONY_ADD: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.HARMONY_DELETE: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HARMONY_DISPLAY_AS_ROMAN_NUMERAL: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HARMONY_DISPLAY_AS_CHORD_SYMBOL: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.MODE_ADD: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.MODE_DELETE: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
}
