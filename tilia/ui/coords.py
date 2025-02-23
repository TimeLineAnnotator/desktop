from tilia.requests import get, Get, listen, Post


class TimeXConverter:
    def __init__(self):
        listen(self, Post.FILE_MEDIA_DURATION_CHANGED, self.on_media_duration_changed)
        listen(self, Post.PLAYBACK_AREA_SET_WIDTH, self.on_playback_area_set_width)

    def setup(self):
        self.media_duration = get(Get.MEDIA_DURATION)
        self.playback_area_width = get(Get.PLAYBACK_AREA_WIDTH)
        self.left_margin_x = get(Get.LEFT_MARGIN_X)

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
        except AttributeError:
            self.setup()
            try:
                return (
                    (x - self.left_margin_x)
                    * self.media_duration
                    / self.playback_area_width
                )
            except ZeroDivisionError:
                return 0.0
        except ZeroDivisionError:
            return 0.0

    def get_x_by_time(self, time: float) -> int:
        try:
            return (
                (time / self.media_duration) * self.playback_area_width
            ) + self.left_margin_x
        except AttributeError:
            self.setup()
            try:
                return (
                    (time / self.media_duration) * self.playback_area_width
                ) + self.left_margin_x
            except ZeroDivisionError:
                return self.left_margin_x
        except ZeroDivisionError:
            self.setup()
            return self.left_margin_x


time_x_converter = TimeXConverter()
