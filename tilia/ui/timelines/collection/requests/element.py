from dataclasses import dataclass

from tilia.requests import Post
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    NOT_SLIDER,
    COLORED_COMPONENTS,
    ALL,
)

from enum import Enum, auto


class TimelineSelector(Enum):
    ANY = auto()
    FROM_CLI = auto()
    FROM_MANAGE_TIMELINES_CURRENT = auto()
    FROM_MANAGE_TIMELINES_TO_PERMUTE = auto()
    FROM_CONTEXT_MENU = auto()
    FROM_CONTEXT_MENU_TO_PERMUTE = auto()
    EXPLICIT = auto()
    SELECTED = auto()
    ALL = auto()
    FIRST = auto()
    PASTE = auto()


class ElementSelector(Enum):
    SELECTED = auto()
    ALL = auto()
    NONE = auto()


@dataclass
class TlElmRequestSelector:
    tl_kind: list[TlKind]
    timeline: TimelineSelector
    element: ElementSelector


@dataclass
class TlRequestSelector:
    tl_kind: list[TlKind]
    timeline: TimelineSelector


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
    Post.BEAT_ADD: TlElmRequestSelector(
        [TlKind.BEAT_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
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
    Post.HARMONY_DISPLAY_AS_ROMAN_NUMERAL: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.HARMONY_DISPLAY_AS_CHORD_SYMBOL: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.SELECTED, ElementSelector.SELECTED
    ),
    Post.MODE_ADD: TlElmRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.PDF_MARKER_ADD: TlElmRequestSelector(
        [TlKind.PDF_TIMELINE], TimelineSelector.FIRST, ElementSelector.NONE
    ),
    Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT
    ),
    Post.TIMELINE_DELETE_FROM_CLI: TlRequestSelector(ALL, TimelineSelector.FROM_CLI),
    Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT
    ),
    Post.TIMELINE_NAME_SET: TlRequestSelector(NOT_SLIDER, TimelineSelector.FIRST),
    Post.TIMELINE_HEIGHT_SET: TlRequestSelector(NOT_SLIDER, TimelineSelector.FIRST),
    Post.HARMONY_TIMELINE_SHOW_KEYS: TlRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST
    ),
    Post.HARMONY_TIMELINE_HIDE_KEYS: TlRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST
    ),
    Post.TIMELINE_DELETE_FROM_CONTEXT_MENU: TlRequestSelector(
        ALL, TimelineSelector.FROM_CONTEXT_MENU
    ),
}
