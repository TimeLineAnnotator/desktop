from dataclasses import dataclass

from tilia.requests import Post
from tilia.timelines.timeline_kinds import TimelineKind as TlKind, NOT_SLIDER, ALL
from tilia.ui.timelines.collection.requests.enums import TimelineSelector


@dataclass
class TlRequestSelector:
    tl_kind: list[TlKind]
    timeline: TimelineSelector


request_to_scope: dict[Post, TlRequestSelector] = {
    Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT
    ),
    Post.TIMELINE_DELETE_FROM_CLI: TlRequestSelector(
        ALL, TimelineSelector.FROM_CLI
    ),
    Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT
    ),
    Post.TIMELINE_NAME_SET: TlRequestSelector(NOT_SLIDER, TimelineSelector.FIRST),
    Post.TIMELINE_HEIGHT_SET: TlRequestSelector(NOT_SLIDER, TimelineSelector.FIRST),
    Post.TIMELINE_ORDINAL_INCREASE_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_TO_PERMUTE
    ),
    Post.TIMELINE_ORDINAL_DECREASE_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_TO_PERMUTE
    ),
    Post.TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES: TlRequestSelector(
        ALL, TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT
    ),
    Post.HARMONY_TIMELINE_SHOW_KEYS: TlRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST
    ),
    Post.HARMONY_TIMELINE_HIDE_KEYS: TlRequestSelector(
        [TlKind.HARMONY_TIMELINE], TimelineSelector.FIRST
    ),
    Post.TIMELINE_DELETE_FROM_CONTEXT_MENU: TlRequestSelector(
        ALL, TimelineSelector.FROM_CONTEXT_MENU
    ),
    Post.TIMELINE_ORDINAL_DECREASE_FROM_CONTEXT_MENU: TlRequestSelector(
        ALL, TimelineSelector.FROM_CONTEXT_MENU_TO_PERMUTE
    ),
    Post.TIMELINE_ORDINAL_INCREASE_FROM_CONTEXT_MENU: TlRequestSelector(
        ALL, TimelineSelector.FROM_CONTEXT_MENU_TO_PERMUTE
    ),
}
