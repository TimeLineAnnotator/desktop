from tilia.timelines.base.timeline import TimelineComponentManager


def scale_discrete(
    cm: TimelineComponentManager, factor: float, offset_old: float, offset_new: float
) -> None:
    for component in cm:
        component.set_data(
            "time", (component.get_data("time") - offset_old) * factor + offset_new
        )


def crop_discrete(cm: TimelineComponentManager, start: float, end: float) -> None:
    for component in list(cm).copy():
        if not start <= component.get_data("time") <= end:
            cm.delete_component(component)
