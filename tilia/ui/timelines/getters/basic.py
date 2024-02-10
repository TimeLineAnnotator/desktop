from typing import Any, Callable

from tilia.requests import Get, get


def all_timelines():
    return get(Get.TIMELINE_UIS)


def by_kinds(kinds, *_, timelines=None, **__):
    timelines = timelines or all_timelines()
    return [tlui for tlui in timelines if tlui.timeline.KIND in kinds]


def last_selected(*_, timelines=None, **__):
    timelines = timelines or all_timelines()
    return get(Get.TIMELINE_UI_LAST_SELECTED, timelines)


GetterCall = tuple[Callable, tuple[Any, ...], dict[str, Any]]


def compose(getters: list[GetterCall]):
    result = []
    for func, args, kwargs in reversed(getters):
        result = func(*args, timelines=result, **kwargs)
    return result
