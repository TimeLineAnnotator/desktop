from __future__ import annotations

import tilia.errors
from tilia.requests import Post, get, Get, post
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.dialogs.add_timeline_without_media import AddTimelineWithoutMedia
from tilia.ui.request_handler import RequestHandler
from tilia.ui.strings import (
    BEAT_TIMELINE_FILL_TITLE,
    BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
)


def _get_media_is_loaded():
    if get(Get.MEDIA_DURATION) == 0:
        return False
    return True


def _get_timeline_name():
    accepted, name = get(
        Get.FROM_USER_STRING,
        title="New timeline",
        prompt="Choose name for new timeline",
    )

    return accepted, name


class TimelineUIsRequestHandler(RequestHandler):
    def __init__(self, timeline_uis):
        super().__init__(
            request_to_callback={
                Post.TIMELINE_ADD: self.on_timeline_add,
                Post.TIMELINES_CLEAR: self.on_timelines_clear,
                Post.BEAT_TIMELINE_FILL: self.on_beat_timeline_fill,
            }
        )
        self.timeline_uis = timeline_uis
        self.timelines = get(Get.TIMELINE_COLLECTION)

    @staticmethod
    def _handle_media_not_loaded() -> bool:
        accept, action_to_take = get(Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA)
        if not accept:
            return False

        if action_to_take == AddTimelineWithoutMedia.Result.SET_DURATION:
            success, duration = get(
                Get.FROM_USER_FLOAT,
                "Set duration",
                "Insert duration",
                initial=1.0,
                min=0.1,
            )
            if not success:
                return False
            post(Post.PLAYER_DURATION_AVAILABLE, duration)
        elif action_to_take == AddTimelineWithoutMedia.Result.LOAD_MEDIA:
            success, path = get(Get.FROM_USER_MEDIA_PATH)
            if not success:
                return False
            post(Post.APP_MEDIA_LOAD, path)
        else:
            raise ValueError(
                f"Unknown action to take '{action_to_take}' for timeline without media."
            )

        return True

    def on_timeline_add(self, kind: TimelineKind):
        if not _get_media_is_loaded():
            if kind == TimelineKind.AUDIOWAVE_TIMELINE:
                tilia.errors.display(tilia.errors.CREATE_TIMELINE_WITHOUT_MEDIA)
                return
            if not self._handle_media_not_loaded():
                return
        success, name = _get_timeline_name()
        kwargs = dict()
        if not success:
            return False
        cls = self.timeline_uis.get_timeline_ui_class(kind)
        if hasattr(cls, "get_additional_args_for_creation"):
            success, additional_args = cls.get_additional_args_for_creation()
            if not success:
                return False
            kwargs |= additional_args

        self.timelines.create_timeline(kind=kind, components=None, name=name, **kwargs)

        return True

    def on_timelines_clear(self, confirmed):
        if confirmed:
            self.timelines.clear_timelines()
            return True
        return False

    @staticmethod
    def on_beat_timeline_fill():
        accepted, result = get(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD)
        if not accepted:
            return False

        timeline, method, value = result

        if not timeline.is_empty:
            confirmed = get(
                Get.FROM_USER_YES_OR_NO,
                BEAT_TIMELINE_FILL_TITLE,
                BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
            )
            if not confirmed:
                return False
            timeline.clear()

        timeline.fill_with_beats(method, value)

        return True
