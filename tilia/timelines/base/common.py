from tilia.timelines.base.timeline import TimelineComponentManager


def scale_discrete(cm: TimelineComponentManager, factor: float) -> None:
    for component in cm:
        component.set_data('time', component.get_data('time') * factor)


def crop_discrete(cm: TimelineComponentManager, length: float) -> None:
    for component in list(cm).copy():
        if component.get_data('time') > length:
            cm.delete_component(component)
