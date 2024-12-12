# TODO: playback line
# TODO: QThreads
# TODO: tracker does not load after viewer is loaded
from __future__ import annotations

from html import escape, unescape
from pathlib import Path
from re import sub
from lxml import etree

from bisect import bisect
from typing import TYPE_CHECKING, Callable

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

from tilia.ui.smooth_scroll import smooth, setup_smooth
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
        self.setObjectName(f"TiLiA Score Viewer {tl.id}")
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
        self.view = SvgGraphicsView(
            get_times=self._get_time_from_scene_x,
            update_measure_tracker=self.update_measure_tracker,
            parent=self,
        )
        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)

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
        self.is_svg_loaded = False
        self.visible_times = [0, 0]
        self.beat_x_position = {}

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
        self.score_root = etree.fromstring(data, None)
        beat_x_pos, success = self.timeline.set_data(
            "viewer_beat_x", self._get_beat_x_pos(self.score_root)
        )
        if not success:
            tilia.errors.display(
                tilia.errors.SCORE_SVG_CREATE_ERROR,
                "File not properly set up. Beat positions not found.",
            )
        else:
            self.beat_x_position = {
                float(beat): float(x) for beat, x in beat_x_pos.items()
            }
        self.timeline.save_svg_data(str(etree.tostring(self.score_root), "utf-8"))

        if not self.timeline_ui:
            return

        self.score_renderer.load(bytearray(etree.tostring(self.score_root)))
        self.is_svg_loaded = True

        for item in self.scene.items():
            if not isinstance(item, SvgTlaAnnotation):
                self.scene.removeItem(item)

        bg = QGraphicsSvgItem()
        bg.setSharedRenderer(self.score_renderer)
        self.scene.addItem(bg)
        self.create_stavenotes(self.score_root)

        if not self.isVisible():
            self.parent().addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self)

        self.show()
        self.view.check_scale()

    def _get_beat_x_pos(self, root: etree._Element) -> dict[float, float]:
        texts = root.findall(".//g[@class='vf-text']", None)
        x_stamps = {}
        measure_divs = {}
        for e in texts:
            if float(e[0].attrib["font-size"].strip("px")) > 1:
                continue
            if len(x_stamp := e[0].text.split("␟")) != 3:
                e[0].attrib["font-size"] = "15px"
                continue

            e.getparent().remove(e)

            measure, beat_div, max_div = map(int, x_stamp)
            if x_stamps.get(measure):
                if cur_x := x_stamps[measure].get(beat_div):
                    if cur_x > (x := float(e[0].attrib["x"])):
                        x_stamps[measure][beat_div] = x
                else:
                    x_stamps[measure][beat_div] = float(e[0].attrib["x"])

            else:
                x_stamps[measure] = {beat_div: float(e[0].attrib["x"])}
                measure_divs[measure] = max_div

        return {
            measure + beat_div / measure_divs[measure]: x
            for measure, value in x_stamps.items()
            for beat_div, x in value.items()
        }

    def create_stavenotes(self, root: etree._Element) -> None:
        def process(element: etree._Element):
            if element.attrib.get("class", "none") != "vf-stavenote":
                for child in element:
                    process(child)
            else:
                id = element.attrib.get("id")
                stavenote = SvgStaveNote(
                    self.score_renderer, id, self._get_closest_time
                )
                self.scene.addItem(stavenote)

        process(root)

    def _get_drag_actions(self) -> dict[str, Callable[[QPointF], None]]:
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

    def filter_selection(self, type: type[SvgStaveNote | SvgTlaAnnotation]) -> None:
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
    ) -> SvgTlaAnnotation:
        new_annotation = SvgTlaAnnotation(
            text, id, x, y, font_size, self._get_drag_actions(), self._get_closest_time
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
            if font.pointSize() < 2:
                continue
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

    def _get_time_from_scene_x(self, xs: dict[int, float]) -> dict[int, list[float]]:
        output = {}
        beat_pos = {}
        beats, x_pos = list(self.beat_x_position.keys()), list(
            self.beat_x_position.values()
        )
        for key, x in xs.items():
            if x in x_pos:
                idx = x_pos.index(x)
                beat_pos[key] = ((b := beats[idx]) // 1, b % 1)
                continue

            idx = bisect(x_pos, x)
            if idx == 0 and len(beats) == 0:
                b0 = 0
                b1 = 1
                x0 = self.scene.sceneRect().left()
                x1 = self.scene.sceneRect().right()
            elif idx == 0:
                b0 = 0
                b1 = beats[0]
                x0 = self.scene.sceneRect().left()
                x1 = x_pos[0]
            elif idx == len(beats):
                b0 = beats[idx - 1]
                b1 = round(-(-b0 // 1))
                x0 = x_pos[idx - 1]
                x1 = self.scene.sceneRect().right()
            else:
                b0 = beats[idx - 1]
                b1 = beats[idx]
                x0 = x_pos[idx - 1]
                x1 = x_pos[idx]
            beat_pos[key] = (
                (num := b0 // 1),
                (frac := (b1 - b0) * (x - x0) / (x1 - x0) + b0 % 1),
            )
            self.beat_x_position[num + frac] = x

            self.beat_x_position = {
                k: self.beat_x_position[k] for k in sorted(self.beat_x_position.keys())
            }

        beat_tl = get(
            Get.TIMELINE_COLLECTION
        ).get_beat_timeline_for_measure_calculation()
        for key, beat in beat_pos.items():
            t = beat_tl.get_time_by_measure(*beat)
            if not t:
                t = (
                    [0]
                    if beat[0] < min(beat_tl.measure_numbers)
                    else [get(Get.MEDIA_DURATION)]
                )
            output[key] = t

        return output

    def _get_scene_x_from_time(self, time: float) -> float:
        beat_tl = get(
            Get.TIMELINE_COLLECTION
        ).get_beat_timeline_for_measure_calculation()
        beat = beat_tl.get_metric_fraction_by_time(time)
        if x := self.beat_x_position.get(beat):
            return x
        beats, x_pos = list(self.beat_x_position.keys()), list(
            self.beat_x_position.values()
        )
        idx = bisect(beats, beat)
        if idx == 0:
            return x_pos[0]
        if idx == len(beats):
            return x_pos[idx - 1]
        return (beat - beats[idx - 1]) / (beats[idx] - beats[idx - 1]) * (
            x_pos[idx] - x_pos[idx - 1]
        ) + x_pos[idx - 1]

    def _get_closest_time(
        self, x: float
    ) -> tuple[tuple[float, float], None | tuple[float, float]]:
        times = self._get_time_from_scene_x({0: x}).get(0)
        current_time = get(Get.SELECTED_TIME)
        idx = bisect(times, current_time)
        if idx == 0:
            return ((times[0], current_time - times[0]), None)
        if idx == len(times):
            return ((times[-1], current_time - times[0]), None)
        return (
            ((t0 := times[idx - 1]), current_time - t0),
            ((t1 := times[idx]), current_time - t1),
        )

    def update_measure_tracker(self, start: float, end: float) -> None:
        if (new_visible_times := [start, end]) == self.visible_times:
            return
        self.visible_times = new_visible_times
        if start != end:
            self.timeline_ui.update_measure_tracker_position(start, end)
            self.timeline_ui.measure_tracker.show()
        else:
            self.timeline_ui.measure_tracker.hide()

    def scroll_to_time(self, time: float, is_centered: bool):
        x = self._get_scene_x_from_time(time)
        if is_centered:
            self.view.scroll_to_x(x)
            return
        cur_viewport = self.view.current_viewport_x
        margin = (width := (cur_viewport[1] - cur_viewport[0])) / 10
        if (cur_viewport[0] + margin) < x < (cur_viewport[1] - margin):
            return
        self.view.scroll_to_x(x + width / 2 - margin)

    def hideEvent(self, a0) -> None:
        try:
            self.timeline_ui.measure_tracker.hide()
        except RuntimeError:
            pass
        self.is_hidden = True
        return super().hideEvent(a0)

    def showEvent(self, event):
        self.timeline_ui.measure_tracker.show()
        self.is_hidden = False
        return super().showEvent(event)

    def enterEvent(self, event) -> None:
        self.setFocus()
        return super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self.clearFocus()
        return super().leaveEvent(a0)

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


class SvgGraphicsView(QGraphicsView):
    def __init__(
        self,
        get_times: Callable[[dict[int, float]], dict[int, list[float]]],
        update_measure_tracker: Callable[[float, float], None],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setFrameShape(QFrame.Shape.Panel)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.get_times = get_times
        self.current_viewport_x = {0: 0.0, 1: 0.0}
        self.current_viewport_y_center = 0.0
        self.current_viewport_x_center = 0.0
        self._viewport_updated()
        self.update_measure_tracker = update_measure_tracker
        setup_smooth(self)

    def _viewport_updated(self) -> bool:
        viewport = self.mapToScene(self.viewport().geometry()).boundingRect()
        self.current_viewport_y_center = viewport.center().y()
        self.current_viewport_x_center = viewport.center().x()
        if (
            vp := {0: viewport.left(), 1: viewport.right()}
        ).values() == self.current_viewport_x.values():
            return False

        self.current_viewport_x = vp
        return True

    def _check_scene_bounding_rect(self) -> None:
        if (
            scene_bounding_rect := self.scene().itemsBoundingRect()
        ) != self.scene().sceneRect():
            self.scene().setSceneRect(scene_bounding_rect)

    def check_scale(self) -> None:
        if (
            visible := self.mapToScene(self.viewport().geometry())
            .boundingRect()
            .height()
            - (
                h_scroll_bar.height()
                if (h_scroll_bar := self.horizontalScrollBar()).maximum() != 0
                else 0
            )
        ) < (actual := self.sceneRect().height()):
            self.setTransform(
                self.transform().scale((zoom_level := visible / actual), zoom_level)
            )
            self._check_scene_bounding_rect()

    def scroll_to_x(self, x: float):
        def __get_x():
            return [self.current_viewport_x_center]

        @smooth(self, __get_x)
        def __set_x(x):
            self.centerOn(x, self.current_viewport_y_center)

        __set_x(x)

    def wheelEvent(self, event):
        if Qt.KeyboardModifier.ControlModifier not in event.modifiers():
            return super().wheelEvent(event)

        if Qt.KeyboardModifier.ShiftModifier in event.modifiers():
            dx = event.angleDelta().y()
            dy = event.angleDelta().x()
        else:
            dx = event.angleDelta().x()
            dy = event.angleDelta().y()

        if event.inverted():
            temp = dx
            dx = dy
            dy = temp

        old_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        if dy > 0:
            self.setTransform(self.transform().scale(1.1, 1.1))
        else:
            self.setTransform(self.transform().scale(1 / 1.1, 1 / 1.1))
        self.setTransformationAnchor(old_anchor)
        self._check_scene_bounding_rect()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._viewport_updated():
            start_ts, end_ts = self.get_times(self.current_viewport_x).values()
            current_time = get(Get.SELECTED_TIME)
            start_time = start_ts[
                s_idx - 1 if (s_idx := bisect(start_ts, current_time)) != 0 else s_idx
            ]
            end_time = (
                end_ts[e_idx]
                if (e_idx := bisect(end_ts, start_time)) != len(end_ts)
                else get(Get.MEDIA_DURATION)
                if start_time != 0 and end_ts[0] != 0
                else 0
            )
            self.update_measure_tracker(start_time, end_time)


class SvgStaveNote(QGraphicsSvgItem):
    def __init__(
        self,
        renderer: QSvgRenderer,
        id: str,
        get_time: Callable[
            [float], tuple[tuple[float, float], None | tuple[float, float]]
        ],
    ) -> None:
        super().__init__()
        self.setSharedRenderer(renderer)
        self.setElementId(id)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(renderer.boundsOnElement(id).topLeft())
        self.get_time = get_time

    def paint(self, painter, option, widget) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setCompositionMode(painter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(self.boundingRect(), Qt.GlobalColor.red)

    def mouseDoubleClickEvent(self, event) -> None:
        t0, t1 = self.get_time(event.scenePos().x())
        if not t1 or abs(t0[1]) < abs(t1[1]):
            post(Post.PLAYER_SEEK, t0[0])
        else:
            post(Post.PLAYER_SEEK, t1[0])
        return super().mouseDoubleClickEvent(event)


class SvgTlaAnnotation(QGraphicsSimpleTextItem):
    def __init__(
        self,
        text: str,
        id: int,
        x: float,
        y: float,
        font_size: int,
        drag_actions: dict[str, Callable[[QPointF], None]],
        get_time: Callable[
            [float], tuple[tuple[float, float], None | tuple[float, float]]
        ],
    ) -> None:
        super().__init__(text)
        self.id = id
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(x, y)
        font = self.font()
        font.setPointSize(font_size)
        font.setStyle(QFont.Style.StyleOblique)
        font.setWeight(QFont.Weight.Medium)
        font.setStyleHint(QFont.StyleHint.Serif, QFont.StyleStrategy.PreferDevice)
        self.setFont(font)
        self.drag_actions = drag_actions
        self.get_time = get_time

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

    def mouseDoubleClickEvent(self, event) -> None:
        t0, t1 = self.get_time(event.scenePos().x())
        if not t1 or abs(t0[1]) < abs(t1[1]):
            post(Post.PLAYER_SEEK, t0[0])
        else:
            post(Post.PLAYER_SEEK, t1[0])
        return super().mouseDoubleClickEvent(event)
