# TODO: reimplement tracker

from __future__ import annotations

from html import escape, unescape
from pathlib import Path
from re import sub
from lxml import etree

# from bisect import bisect
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    pyqtSlot,
    Qt,
    QKeyCombination,
    QObject,
    QPointF,
    QUrl,
)
from PyQt6.QtGui import QFont
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsView,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtSvg import QSvgRenderer

from tilia.ui.actions import TiliaAction, get_qaction

# from tilia.ui.smooth_scroll import smooth, setup_smooth
from tilia.ui.windows.view_window import ViewDockWidget
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get, post, Post
import tilia.errors

# from tilia.settings import settings

if TYPE_CHECKING:
    from tilia.timelines.score.timeline import ScoreTimeline


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


class SvgViewer(ViewDockWidget):
    def __init__(self, name: str, tl: ScoreTimeline, *args, **kwargs) -> None:
        super().__init__("TiLiA Score Viewer", *args, menu_title=name, **kwargs)

        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.timeline = tl
        self.timeline_ui = None

        self.__setup_score_creator()
        self.__setup_score_viewer()

    def __setup_score_creator(self) -> None:
        self.is_engine_loaded = False
        self.web_engine = QWebEngineView()
        self.web_engine.load(
            QUrl.fromLocalFile(
                (Path(__file__).parent / "svg_maker.html").resolve().__str__()
            )
        )
        self.web_engine.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.web_engine.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self.web_engine.loadFinished.connect(self.engine_loaded)

        self.channel = QWebChannel()
        self.shared_object = SvgWebEngineTracker(
            self.web_engine.page(),
            self.preprocess_svg,
            self.display_error,
        )
        self.channel.registerObject("backend", self.shared_object)
        self.web_engine.page().setWebChannel(self.channel)

    def engine_loaded(self) -> None:
        self.is_engine_loaded = True

    def preprocess_svg(self, svg: str) -> None:
        svg = sub("\\&\\w+\\;", lambda x: escape(unescape(x.group(0))), svg)
        self.timeline.set_data("svg_data", svg)

    def to_svg(self, data: str) -> None:
        def convert():
            self.web_engine.page().runJavaScript(f"loadSVG(`{data}`)")

        if self.is_engine_loaded:
            convert()
        else:
            self.web_engine.loadFinished.connect(convert)

    def display_error(self, message: str) -> None:
        tilia.errors.display(tilia.errors.SCORE_SVG_CREATE_ERROR, message)

    def __setup_score_viewer(self) -> None:
        self.view = QGraphicsView(self)
        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setFrameShadow(QFrame.Shadow.Sunken)
        self.view.setFrameShape(QFrame.Shape.Panel)

        v_toolbar = self._get_toolbar()
        h_box = QHBoxLayout()
        h_box.addLayout(v_toolbar)
        h_box.addWidget(self.view)
        widget = QWidget()
        widget.setLayout(h_box)
        self.setWidget(widget)

        self.score_root = ""
        self.score_renderer = QSvgRenderer()
        self.tla_annotations = {}
        self.next_tla_id = 0
        self.drag_pos = QPointF()
        self.is_hidden = False
        self.visible_measures = [
            {"number": 1, "fraction": 0},
            {"number": 1, "fraction": 0},
        ]
        self.relative_start_x = {}

    def _get_toolbar(self) -> QVBoxLayout:
        def get_button(qaction, callback):
            button = QToolButton()
            qaction.triggered.connect(callback)
            button.setDefaultAction(qaction)
            return button

        actions = [
            (TiliaAction.SCORE_ANNOTATION_ADD, self.annotation_add),
            (TiliaAction.SCORE_ANNOTATION_EDIT, self.annotation_edit),
            (TiliaAction.SCORE_ANNOTATION_DELETE, self.annotation_delete),
            (TiliaAction.SCORE_ANNOTATION_FONT_INC, self.annotation_font_inc),
            (TiliaAction.SCORE_ANNOTATION_FONT_DEC, self.annotation_font_dec),
        ]

        v_toolbar = QVBoxLayout()
        for taction, callback in actions:
            button = get_button(get_qaction(taction), callback)
            v_toolbar.addWidget(button)

        return v_toolbar

    def load_svg_data(self, data: str) -> None:
        self.score_root = etree.fromstring(data)
        self.score_renderer.load(bytearray(etree.tostring(self.score_root)))

        for item in self.scene.items():
            if not isinstance(item, SvgTlaAnnotation):
                self.scene.removeItem(item)
                item.deleteLater()

        bg = QGraphicsSvgItem()
        bg.setSharedRenderer(self.score_renderer)
        self.scene.addItem(bg)
        self.create_stavenotes(self.score_root)

        if self.timeline_ui and not self.is_hidden:
            if not self.isVisible():
                self.parent().addDockWidget(
                    Qt.DockWidgetArea.BottomDockWidgetArea, self
                )
            self.show()

    def create_stavenotes(self, root: etree.Element) -> None:
        def process(element: etree.Element):
            if element.attrib.get("class", "none") != "vf-stavenote":
                for child in element:
                    process(child)
            else:
                id = element.attrib.get("id")
                stavenote = SvgStaveNote(self.score_renderer, id)
                self.scene.addItem(stavenote)

        process(root)

    def _get_drag_actions(self) -> None:
        def _start_drag(start_pos: QPointF) -> None:
            self.filter_selection(SvgTlaAnnotation)
            self.drag_pos = start_pos

        def _while_drag(current_pos: QPointF) -> None:
            d_pos = current_pos - self.drag_pos
            for item in self.scene.selectedItems():
                item.moveBy(d_pos.x(), d_pos.y())
            self.drag_pos = current_pos

        def _after_drag(final_pos: QPointF) -> None:
            d_pos = final_pos - self.drag_pos
            for item in self.scene.selectedItems():
                item.moveBy(d_pos.x(), d_pos.y())
                self.save_tla_annotation(item)
            post(Post.APP_RECORD_STATE, "score annotation")

        return {"press": _start_drag, "move": _while_drag, "release": _after_drag}

    def remove_annotation(self, tl_component) -> None:
        viewer_id = tl_component.get_data("viewer_id")
        self.scene.removeItem(self.tla_annotations[viewer_id]["annotation"])
        self.tla_annotations.pop(viewer_id)

    def update_annotation(self, tl_component) -> None:
        data: dict = tl_component.get_viewer_data()
        if data["viewer_id"] in self.tla_annotations.keys():
            component_id = data["viewer_id"]
            self.scene.removeItem(self.tla_annotations[component_id]["annotation"])
            self.tla_annotations.pop(component_id)
        annotation = self.create_annotation(
            data["text"], data["viewer_id"], data["x"], data["y"], data["font_size"]
        )
        annotation.setSelected(True)
        self.tla_annotations[data["viewer_id"]] = {
            "component": tl_component,
            "annotation": annotation,
        }

    def filter_selection(self, type: SvgStaveNote | SvgTlaAnnotation):
        for selected in self.scene.selectedItems():
            if not isinstance(selected, type):
                selected.setSelected(False)

    def save_tla_annotation(self, item: SvgTlaAnnotation) -> None:
        self.tla_annotations[item.id]["component"].save_data(
            x=item.x(),
            y=item.y(),
            viewer_id=item.id,
            text=item.text(),
            font_size=item.font().pointSize(),
        )

    def _check_tla_id(self, id) -> None:
        if self.next_tla_id <= id:
            self.next_tla_id = id + 1

    def create_annotation(
        self, text: str, id: int, x: float, y: float, font_size: int = 16
    ) -> None:
        new_annotation = SvgTlaAnnotation(
            text, id, x, y, font_size, self._get_drag_actions()
        )
        self._check_tla_id(id)
        self.scene.addItem(new_annotation)
        return new_annotation

    def annotation_add(self) -> None:
        self.filter_selection(SvgStaveNote)
        if not (to_add := self.scene.selectedItems()):
            return
        success, annotation = get(
            Get.FROM_USER_STRING, "Score Annotation", "Add annotation"
        )
        if not success or not annotation:
            return
        for item in to_add:
            new_annotation = self.create_annotation(
                annotation, self.next_tla_id, item.x(), item.y()
            )
            item.setSelected(False)
            new_annotation.setSelected(True)
            (score_annotation, _) = self.timeline.create_component(
                kind=ComponentKind.SCORE_ANNOTATION
            )
            self.tla_annotations[new_annotation.id] = {
                "component": score_annotation,
                "annotation": new_annotation,
            }
            self.save_tla_annotation(new_annotation)
        post(Post.APP_RECORD_STATE, "score annotation")

    def annotation_delete(self) -> None:
        self.filter_selection(SvgTlaAnnotation)
        if not (to_delete := self.scene.selectedItems()):
            return
        self.timeline.delete_components(
            [self.tla_annotations[item.id]["component"] for item in to_delete]
        )
        post(Post.APP_RECORD_STATE, "score annotation")

    def annotation_edit(self) -> None:
        self.filter_selection(SvgTlaAnnotation)
        if not (to_edit := self.scene.selectedItems()):
            return
        for item in to_edit:
            success, annotation = get(
                Get.FROM_USER_STRING, "Score Annotation", "Edit Annotation", item.text()
            )
            if not success:
                continue
            if not annotation:
                if get(
                    Get.FROM_USER_YES_OR_NO,
                    "Edit annotation",
                    "No text inputted. Delete annotation?",
                ):
                    self.timeline.delete_components(
                        [self.tla_annotations[item.id]["component"]]
                    )
                    post(Post.APP_RECORD_STATE, "score annotation")
                continue

            item.setText(annotation)
            item.setSelected(False)
            self.save_tla_annotation(item)
            post(Post.APP_RECORD_STATE, "score annotation")

    def annotation_font_dec(self) -> None:
        self.filter_selection(SvgTlaAnnotation)
        if not (to_edit := self.scene.selectedItems()):
            return
        for item in to_edit:
            font = item.font()
            font.setPointSize(font.pointSize() // 2)
            item.setFont(font)
            self.save_tla_annotation(item)
        post(Post.APP_RECORD_STATE, "score annotation")

    def annotation_font_inc(self) -> None:
        self.filter_selection(SvgTlaAnnotation)
        if not (to_edit := self.scene.selectedItems()):
            return
        for item in to_edit:
            font = item.font()
            font.setPointSize(font.pointSize() * 2)
            item.setFont(font)
            self.save_tla_annotation(item)
        post(Post.APP_RECORD_STATE, "score annotation")

    def zoom_in(self) -> None:
        self.view.setTransform(self.view.transform().scale(1.1, 1.1))
        self._check_zoom_limits()

    def zoom_out(self) -> None:
        self.view.setTransform(self.view.transform().scale(1 / 1.1, 1 / 1.1))
        self._check_zoom_limits()

    def _check_zoom_limits(self) -> None:
        if (br := self.scene.itemsBoundingRect()) != self.scene.sceneRect():
            self.scene.setSceneRect(br)

    def hideEvent(self, a0) -> None:
        self.timeline_ui.measure_tracker.hide()
        self.is_hidden = True
        return super().hideEvent(a0)

    def showEvent(self, event):
        self.timeline_ui.measure_tracker.show()
        self.is_hidden = False
        return super().showEvent(event)

    def enterEvent(self, event) -> None:
        self.setFocus()
        return super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.clearFocus()
        return super().leaveEvent(event)

    def keyPressEvent(self, a0) -> None:
        # listen here because these shortcuts are shared with the main window
        key_comb_to_action = {
            QKeyCombination(
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Delete
            ): self.annotation_delete,
            QKeyCombination(
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return
            ): self.annotation_add,
        }
        if action := key_comb_to_action.get(a0.keyCombination()):
            a0.accept()
            action()
        else:
            return super().keyPressEvent(a0)

    def wheelEvent(self, a0) -> None:
        if Qt.KeyboardModifier.ControlModifier not in a0.modifiers():
            return super().wheelEvent(a0)

        if Qt.KeyboardModifier.ShiftModifier in a0.modifiers():
            dx = a0.angleDelta().y()
            dy = a0.angleDelta().x()
        else:
            dx = a0.angleDelta().x()
            dy = a0.angleDelta().y()

        if a0.inverted():
            temp = dx
            dx = dy
            dy = temp

        if dy > 0:
            self.zoom_in()
        else:
            self.zoom_out()


class SvgStaveNote(QGraphicsSvgItem):
    def __init__(self, renderer, id) -> None:
        super().__init__()
        self.setSharedRenderer(renderer)
        self.setElementId(id)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(renderer.boundsOnElement(id).topLeft())

    def paint(self, painter, option, widget) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setCompositionMode(painter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(self.boundingRect(), Qt.GlobalColor.red)


class SvgTlaAnnotation(QGraphicsSimpleTextItem):
    def __init__(self, text, id, x, y, font_size, drag_actions) -> None:
        super().__init__(text)
        self.id = id
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(x, y)
        font = self.font()
        font.setPointSize(font_size)
        font.setStyle(QFont.Style.StyleOblique)
        font.setStyleHint(QFont.StyleHint.Serif, QFont.StyleStrategy.PreferDevice)
        self.setFont(font)
        self.drag_actions = drag_actions

    def paint(self, painter, option, widget) -> None:
        self.setBrush(Qt.GlobalColor.red if self.isSelected() else Qt.GlobalColor.black)
        return super().paint(painter, option, widget)

    def mousePressEvent(self, event) -> None:
        self.drag_actions["press"](event.scenePos())
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self.drag_actions["move"](event.scenePos())
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_actions["release"](event.scenePos())
        return super().mouseReleaseEvent(event)
