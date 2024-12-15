from tilia.timelines.base.component import PointLikeTimelineComponent, SegmentLikeTimelineComponent
from tilia.timelines.base.timeline import TimelineComponentManager


def scale_mixed(cm: TimelineComponentManager, factor: float) -> None:
    for component in list(cm).copy():
        if isinstance(component, PointLikeTimelineComponent):
            component.set_data('time', component.get_data('time') * factor)
        elif isinstance(component, SegmentLikeTimelineComponent):
            component.set_data('start', component.get_data('start') * factor)
            component.set_data('end', component.get_data('end') * factor)


def crop_mixed(cm: TimelineComponentManager, length: float) -> None:
    for component in list(cm).copy():
        if isinstance(component, PointLikeTimelineComponent):
            if component.get_data('time') > length:
                cm.delete_component(component)
        elif isinstance(component, SegmentLikeTimelineComponent):
            start = component.get_data('start')
            end = component.get_data('end')
            if start >= length:
                cm.delete_component(component)
            elif end > length:
                component.set_data('end', length)