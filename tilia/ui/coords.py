from tilia.requests import get, Get


def get_x_by_time(time: float) -> int:
    return ((time / get(Get.MEDIA_DURATION)) * get(Get.TIMELINE_WIDTH)) + get(
        Get.LEFT_MARGIN_X
    )


def get_time_by_x(x: float) -> float:
    return (
        (x - get(Get.LEFT_MARGIN_X)) * get(Get.MEDIA_DURATION) / get(Get.TIMELINE_WIDTH)
    )
