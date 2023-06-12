from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline


def get_timeline_by_name(name: str) -> Timeline:
    result = [tl for tl in get(Get.TIMELINES) if tl.name == name]
    return result[0] if result else None


def get_timeline_by_id(id: str) -> Timeline | None:
    result = [tl for tl in get(Get.TIMELINES) if tl.id == id]
    return result[0] if result else None
