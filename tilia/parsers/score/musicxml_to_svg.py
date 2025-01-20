from __future__ import annotations

from html import escape, unescape
from pathlib import Path
from re import sub

from PyQt6.QtCore import (
    pyqtSlot,
    QObject,
    QUrl,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from tilia.requests import (
    get,
    Get,
)
import tilia.errors


class SvgWebEngineTracker(QObject):
    def __init__(self, page, on_svg_loaded, display_error) -> None:
        super().__init__()
        self.page = page
        self.on_svg_loaded = on_svg_loaded
        self.display_error = display_error

    @pyqtSlot(str)
    def set_svg(self, svg: str) -> None:
        self.on_svg_loaded(svg)

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        self.display_error(message)


class musicxml_to_svg(QWebEngineView):
    def __init__(self, timeline_id):
        self.timeline_id = timeline_id
        self.is_engine_loaded = False
        super().__init__()
        self.load(
            QUrl.fromLocalFile(
                (Path(__file__).parent / "svg_maker.html").resolve().__str__()
            )
        )
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.loadFinished.connect(self.engine_loaded)

        self.channel = QWebChannel()
        self.shared_object = SvgWebEngineTracker(
            self.page(),
            self.preprocess_svg,
            self.display_error,
        )
        self.channel.registerObject("backend", self.shared_object)
        self.page().setWebChannel(self.channel)

    def engine_loaded(self) -> None:
        self.is_engine_loaded = True

    def preprocess_svg(self, svg: str) -> None:
        svg = sub("\\&\\w+\\;", lambda x: escape(unescape(x.group(0))), svg)
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.timeline_id, "svg_data", svg
        )
        self.deleteLater()

    def to_svg(self, data: str) -> None:
        def convert():
            self.page().runJavaScript(f"loadSVG(`{data}`)")

        if self.is_engine_loaded:
            convert()
        else:
            self.loadFinished.connect(convert)

    def display_error(self, message: str) -> None:
        tilia.errors.display(tilia.errors.SCORE_SVG_CREATE_ERROR, message)
