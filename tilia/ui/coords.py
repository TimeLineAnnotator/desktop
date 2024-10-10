from tilia.requests import get, Get


def get_x_by_time(time: float) -> float:
    try:
        playback_time = get(Get.MEDIA_TIMES_PLAYBACK)
        return (
            (time - playback_time.start)
            / playback_time.duration
            * get(Get.PLAYBACK_AREA_WIDTH)
        ) + get(Get.LEFT_MARGIN_X)
    except ZeroDivisionError:
        return get(Get.LEFT_MARGIN_X)


def get_time_by_x(x: float) -> float:
    try:
        playback_time = get(Get.MEDIA_TIMES_PLAYBACK)
        return (
            (x - get(Get.LEFT_MARGIN_X))
            * playback_time.duration
            / get(Get.PLAYBACK_AREA_WIDTH)
        ) + playback_time.start
    except ZeroDivisionError:
        return 0.0
