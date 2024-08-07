from __future__ import annotations
import logging
import pypdf

from tilia.settings import settings
from tilia.requests import Get, get
from tilia.timelines.base.validators import validate_string
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager

logger = logging.getLogger(__name__)


class PdfTimeline(Timeline):
    KIND = TimelineKind.PDF_TIMELINE
    SERIALIZABLE_BY_VALUE = [
        'height',
        'is_visible',
        'name',
        'ordinal',
        'path'
    ]

    def __init__(
        self,
        component_manager: PdfTLComponentManager,
        path: str,
        name: str = "",
        height: int | None = None,
        **kwargs
    ):
        super().__init__(
            name=name,
            height=height,
            component_manager=component_manager,
            **kwargs,
        )

        self.validators = self.validators | {'path': validate_string}
        self.path = path

    @property
    def default_height(self):
        return settings.get("PDF_timeline", "default_height")

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value
        try:
            self.page_total = len(pypdf.PdfReader(value).pages)
            self.is_pdf_valid = True
        except FileNotFoundError:
            self.page_total = 0
            self.is_pdf_valid = False

    def setup_blank_timeline(self):
        self.create_timeline_component(
            ComponentKind.PDF_MARKER,
            time=0,
            page_number=1
        )

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def get_previous_page_number(self, time: float) -> int:
        previous_component = self.get_previous_component_by_time(time)
        return previous_component.get_data('page_number') if previous_component else 0

    def scale(self, factor: float) -> None:
        self.component_manager: PdfTLComponentManager
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager: PdfTLComponentManager
        self.component_manager.crop(length)


class PdfTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.PDF_MARKER]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        media_duration = get(Get.MEDIA_DURATION)
        if time > media_duration:
            return False, f"Time '{time}' is bigger than media time '{media_duration}'"
        elif time < 0:
            return False, f"Time can't be negative. Got '{time}'"
        elif time in [x.time for x in self.get_components()]:
            return (
                False,
                f"There is already a page marker at this position."
            )
        else:
            return True, ""

    def scale(self, factor: float) -> None:
        for marker in self:
            marker.set_data("time", marker.get_data("time") * factor)

    def crop(self, length: float) -> None:
        for marker in list(self).copy():
            if marker.get_data("time") > length:
                self.delete_component(marker)
