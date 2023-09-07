from tilia.requests import get, Get


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
