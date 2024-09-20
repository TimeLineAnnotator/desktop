from tilia.requests import get, Get, listen, Post


class TimeXConverter:
    def __init__(self):
        self.media_duration = get(Get.MEDIA_DURATION)
        self.playback_area_width = get(Get.PLAYBACK_AREA_WIDTH)
        self.left_margin_x = get(Get.LEFT_MARGIN_X)

        listen(self, Post.FILE_MEDIA_DURATION_CHANGED, self.on_media_duration_changed)
        listen(self, Post.PLAYBACK_AREA_SET_WIDTH, self.on_playback_area_set_width)

    def on_media_duration_changed(self, duration):
        self.media_duration = duration

    def on_playback_area_set_width(self, width):
        if width < 0:
            return

        self.playback_area_width = width

    def get_time_by_x(self, x):
        try:
            return (
                (x - self.left_margin_x)
                * self.media_duration
                / self.playback_area_width
            )
        except ZeroDivisionError:
            return 0.0

    def get_x_by_time(self, time: float) -> int:
        try:
            return (
                (time / self.media_duration) * self.playback_area_width
            ) + self.left_margin_x
        except ZeroDivisionError:
            return self.left_margin_x


def get_x_by_time(time: float) -> int:
    try:
        return ((time / get(Get.MEDIA_DURATION)) * get(Get.PLAYBACK_AREA_WIDTH)) + get(
            Get.LEFT_MARGIN_X
        )
    except ZeroDivisionError:
        return get(Get.LEFT_MARGIN_X)


def get_time_by_x(x: float) -> float:
    try:
        return (
            (x - get(Get.LEFT_MARGIN_X))
            * get(Get.MEDIA_DURATION)
            / get(Get.PLAYBACK_AREA_WIDTH)
        )
    except ZeroDivisionError:
        return 0.0
