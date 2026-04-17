from __future__ import annotations

import functools

import httpx
import pypdf
from pathlib import Path
from urllib import parse


import tilia.dirs
from tilia.errors import display, LOAD_FILE_ERROR
from tilia.requests import get, Get
from tilia.settings import settings
from tilia.timelines.base.component.pointlike import scale_pointlike, crop_pointlike
from tilia.timelines.base.validators import validate_string
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.pdf.components import PdfMarker
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import (
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)


class PdfTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: PdfTimeline):
        super().__init__(timeline, [ComponentKind.PDF_MARKER])
        self.scale = functools.partial(scale_pointlike, self)
        self.crop = functools.partial(crop_pointlike, self)

    def _validate_component_creation(self, _, time, *args, **kwargs):
        return PdfMarker.validate_creation(time, {c.get_data("time") for c in self})


class PdfTimeline(Timeline):
    KIND = TimelineKind.PDF_TIMELINE
    SERIALIZABLE = ["height", "is_visible", "name", "ordinal", "path"]
    COMPONENT_MANAGER_CLASS = PdfTLComponentManager
    FLAGS = [TimelineFlag.COMPONENTS_COPYABLE, TimelineFlag.COMPONENTS_IMPORTABLE]

    def __init__(self, path: str, name: str = "", height: int | None = None, **kwargs):
        super().__init__(
            name=name,
            height=height,
            **kwargs,
        )

        self.validators = self.validators | {"path": validate_string}
        self.path = path

    @property
    def default_height(self):
        return settings.get("PDF_timeline", "default_height")

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value: str):
        self._path = value
        self.is_local = True
        self.is_pdf_valid = False
        self.page_total = 0
        if parse.urlparse(value).scheme in ("http", "https"):
            path = tilia.dirs.tmp_path / value.partition("://")[2]
            if not path.exists() and not self._download_pdf(path, value):
                return
            self.is_local = False
            self.page_total = len(pypdf.PdfReader(path).pages)
            self.is_pdf_valid = True
            self.tmp_path = path.as_posix()

        elif checked_path := get(Get.VERIFIED_PATH, value):
            try:
                self._path = Path(checked_path).as_posix()
                self.is_local = True
                self.is_pdf_valid = True
                self.page_total = len(pypdf.PdfReader(checked_path).pages)

            except FileNotFoundError:
                return

    def _download_pdf(self, path, url):
        if not (response := httpx.get(url)).is_success:
            display(LOAD_FILE_ERROR, url, response)
            return False
        path = tilia.dirs.tmp_path / url.partition("://")[2]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(response.content)
        return True

    def setup_blank_timeline(self):
        self.create_component(ComponentKind.PDF_MARKER, time=0, page_number=1)

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def get_previous_page_number(self, time: float) -> int:
        previous_component = self.get_previous_component_by_time(time)
        return previous_component.get_data("page_number") if previous_component else 0
