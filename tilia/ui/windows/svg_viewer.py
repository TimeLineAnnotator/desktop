# TODO:
# - control pos from mw

from enum import Enum, auto
from html import escape, unescape
from pathlib import Path
from re import sub
from lxml import etree

from PyQt6.QtCore import (
    pyqtSlot,
    Qt,
    QKeyCombination,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    QUrl,
)
from PyQt6.QtGui import QPolygon
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDockWidget, QScrollArea

from tilia.ui.windows.view_window import ViewWindow
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get, post, Post
import tilia.errors
from tilia.ui.coords import time_x_converter


class SvgSelectionBox(QRectF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = QPointF(self.bottomLeft())

    def close_box(self, point: QPointF):
        self.setCoords(
            min(self.start.x(), point.x()),
            min(self.start.y(), point.y()),
            max(self.start.x(), point.x()),
            max(self.start.y(), point.y()),
        )


class SvgWidget(QSvgWidget):
    class SELECTION_MODE(Enum):
        NEW = auto()
        UNION = auto()
        SYMMETRIC_DIFFERENCE = auto()
        MOVE = auto()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()
        self.root = etree.Element("svg")

    def reset(self):
        self.selectable_elements = {}
        self.deletable_ids = set()
        self.measures = {}
        self.next_tla_id = 0
        self.selection_box = None
        self.selected_elements_id = set()
        self.new_selection = set()
        self.previous_selection = set()
        self.selection_mode = self.SELECTION_MODE.NEW

    def __refresh_svg(self):
        super().load(bytearray(etree.tostring(self.root)))

    @property
    def viewer(self):
        return self.parent().parent().parent()

    def load(self, data: str):
        self.blockSignals(True)
        old_selectable = self.selectable_elements.copy()
        old_deletable = self.deletable_ids.copy()
        self.root = etree.fromstring(data)
        self.svg_width = round(float(self.root.attrib.get("width", 500)))
        self.svg_height = round(float(self.root.attrib.get("height", 500)))
        self.reset()
        self.get_editable_elements(self.root)
        for id in old_deletable:
            self.selectable_elements[id] = old_selectable[id]
            self.root.append(old_selectable[id]["node"])
        self.deletable_ids = old_deletable

        self.__refresh_svg()
        self.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(self.svg_width, self.svg_height)
        self.show()
        self.blockSignals(False)

    def update_annotation(self, data: str, tl_component):
        if data == "delete":
            id = [
                d
                for d in self.deletable_ids
                if self.selectable_elements[d]["component"] is tl_component
            ][0]
            self.root.remove(self.selectable_elements[id]["node"])
            self.selectable_elements.pop(id)
            self.deletable_ids.remove(id)
            if id in self.selected_elements_id:
                self.selected_elements_id.remove(id)

        else:
            annotation = etree.fromstring(data)
            self.root.append(annotation)
            if (id := annotation.attrib.get("id")) in self.deletable_ids:
                self.root.remove(self.selectable_elements[id]["node"])
            else:
                self.selectable_elements[id] = {"component": tl_component}
                self.deletable_ids.add(id)
                self._check_tla_id(id)
                if hasattr(self, "transform_x"):
                    self._get_bounds(self.selectable_elements, id)
            self.selectable_elements[id]["node"] = annotation

        self.__refresh_svg()

    def _check_tla_id(self, id: str):
        id = int(id.split("tla_")[1])
        if self.next_tla_id <= id:
            self.next_tla_id = id + 1

    def get_editable_elements(self, node: etree.Element):
        for glyph in node.findall("g"):
            self.get_editable_elements(glyph)

        if not (v_class := node.attrib.get("class", None)):
            return

        match v_class:
            case "vf-stavenote":
                self.selectable_elements[node.attrib["id"]] = {"node": node}
            case "vf-measure":
                self.measures[node.attrib["id"]] = {"node": node}

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.update_bounds()
        self.update_measure_visibility()

    def moveEvent(self, a0):
        super().moveEvent(a0)
        if hasattr(self, "transform_x"):
            self.update_measure_visibility()

    def _get_bounds(self, d: dict, element_id: str):
        d[element_id].update(
            {
                "bounds": (
                    self.renderer()
                    .transformForElement(element_id)
                    .scale(self.transform_x, self.transform_y)
                    .mapToPolygon(
                        self.renderer().boundsOnElement(element_id).toAlignedRect()
                    )
                )
            }
        )

    def update_bounds(self):
        def update(to_update: dict):
            for element in to_update.keys():
                self._get_bounds(to_update, element)

        self.transform_x = self.width() / self.renderer().viewBox().size().width()
        self.transform_y = self.height() / self.renderer().viewBox().size().height()
        update(self.selectable_elements)
        update(self.measures)

    def update_measure_visibility(self):
        p = self.parentWidget().parentWidget().childrenRect()
        p_min = self.parentWidget().parentWidget().mapToGlobal(p.topLeft()).x()
        p_max = self.parentWidget().parentWidget().mapToGlobal(p.bottomRight()).x()
        visible_measures = []

        for id, measure in self.measures.items():

            def intersects():
                if p_min <= m_min and p_max >= m_max:
                    return True, (0, 0)
                m_length = m_max - m_min
                if p_min >= m_min and p_max <= m_max:
                    return True, (
                        (p_min - m_min) / m_length,
                        (p_max - m_min) / m_length,
                    )
                if p_min > m_min and p_min < m_max <= p_max:
                    return True, ((p_min - m_min) / m_length, 0)
                if p_min <= m_min < p_max and p_max < m_max:
                    return True, (0, (p_max - m_min) / m_length)
                return False, (-1, -1)

            m = measure["bounds"].boundingRect()
            m_min = self.mapToGlobal(m.topLeft()).x()
            m_max = self.mapToGlobal(m.bottomRight()).x()
            is_intersecting, fractions = intersects()
            if is_intersecting:
                if len(visible_measures) == 0:
                    visible_measures.append(
                        {"number": int(id), "fraction": fractions[0]}
                    )
                if fractions[1] != 0:
                    visible_measures.append(
                        {"number": int(id), "fraction": fractions[1]}
                    )
                    break
            else:
                if len(visible_measures) == 1:
                    visible_measures.append({"number": int(id), "fraction": 0})
                    break

        self.viewer.update_visible_measures(visible_measures)

    def mousePressEvent(self, a0):
        if (to_move := self.selected_elements_id.intersection(self.deletable_ids)) and [
            id
            for id in to_move
            if self.selectable_elements[id]["bounds"].containsPoint(
                a0.position().toPoint(), Qt.FillRule.OddEvenFill
            )
        ]:
            self.ids_to_move = to_move
            self.remove_from_selection(self.selected_elements_id.difference(to_move))
            self.selection_mode = self.SELECTION_MODE.MOVE
        elif Qt.KeyboardModifier.ControlModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.SYMMETRIC_DIFFERENCE
        elif Qt.KeyboardModifier.ShiftModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.UNION
        else:
            self.selection_mode = self.SELECTION_MODE.NEW

        self.selection_box = SvgSelectionBox(a0.position().x(), a0.position().y(), 0, 0)
        self.previous_selection = self.selected_elements_id.copy()

        return super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0):
        if self.selection_box is None:
            return super().mouseMoveEvent(a0)

        if self.selection_mode is self.SELECTION_MODE.MOVE:
            self.move_annotation(self.selection_box.bottomLeft(), a0.position(), False)
            self.selection_box.moveBottomLeft(a0.position())
        else:
            self.selection_box.close_box(a0.position())
            sb = QPolygon(self.selection_box.toAlignedRect(), True)
            self.new_selection = {
                k
                for (k, v) in self.selectable_elements.items()
                if v["bounds"].intersects(sb)
            }
            self.update_selection()

    def mouseReleaseEvent(self, a0):
        if self.selection_box is None:
            return super().mouseReleaseEvent(a0)

        if self.selection_mode is self.SELECTION_MODE.MOVE:
            self.move_annotation(self.selection_box.bottomLeft(), a0.position())
        else:
            self.selection_box.close_box(a0.position())
            sb = QPolygon(self.selection_box.toAlignedRect(), True)
            self.new_selection = {
                k
                for (k, v) in self.selectable_elements.items()
                if v["bounds"].intersects(sb)
            }
            self.update_selection()
        self.selection_box = None

    def add_to_selection(self, element_ids: set[str]):
        def make_coloured(cur_node: etree.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#ff0000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#ff0000"  # use settings
            for child in cur_node:
                make_coloured(child)

        for id in element_ids:
            make_coloured(self.selectable_elements[id]["node"])
            self.selected_elements_id.add(id)

    def remove_from_selection(self, element_ids: set[str]):
        def make_black(cur_node: etree.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#000000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#000000"  # use settings
            for child in cur_node:
                make_black(child)

        for id in element_ids:
            make_black(self.selectable_elements[id]["node"])
        self.selected_elements_id.difference_update(element_ids)

    def update_selection(self):
        match self.selection_mode:
            case self.SELECTION_MODE.NEW:
                in_selection = self.new_selection

            case self.SELECTION_MODE.SYMMETRIC_DIFFERENCE:
                in_selection = self.new_selection.symmetric_difference(
                    self.previous_selection
                )

            case self.SELECTION_MODE.UNION:
                in_selection = self.new_selection.union(self.previous_selection)

        self.add_to_selection(in_selection.difference(self.selected_elements_id))
        self.remove_from_selection(self.selected_elements_id.difference(in_selection))

        self.__refresh_svg()

    def move_annotation(self, start: QPointF, end: QPointF, is_final: bool = True):
        x = end.x() - start.x()
        y = end.y() - start.y()
        for id in self.ids_to_move:
            self.selectable_elements[id]["node"][0].attrib["x"] = str(
                float(self.selectable_elements[id]["node"][0].attrib["x"]) + x
            )
            self.selectable_elements[id]["node"][0].attrib["y"] = str(
                float(self.selectable_elements[id]["node"][0].attrib["y"]) + y
            )
            self._get_bounds(self.selectable_elements, id)
        if is_final:
            self.save_to_file(self.ids_to_move)
        self.__refresh_svg()

    def enterEvent(self, a0):
        self.setFocus()
        return super().enterEvent(a0)

    def leaveEvent(self, a0):
        self.clearFocus()
        return super().leaveEvent(a0)

    def wheelEvent(self, a0):
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

    def keyPressEvent(self, a0):
        key_comb_to_action = {
            QKeyCombination(
                Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Plus
            ): self.zoom_in,
            QKeyCombination(
                Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Minus
            ): self.zoom_out,
            QKeyCombination(
                Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Up
            ): self.annotation_zoom_in,
            QKeyCombination(
                Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Down
            ): self.annotation_zoom_out,
            QKeyCombination(
                Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Return
            ): self.edit_tla_annotation,
            QKeyCombination(
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Delete
            ): self.delete_tla_annotation,
            QKeyCombination(
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return
            ): self.add_tla_annotation,
        }
        if action := key_comb_to_action.get(a0.keyCombination()):
            action()
        else:
            return super().keyPressEvent(a0)

    def edit_tla_annotation(self):
        if ids_to_edit := self.selected_elements_id.intersection(self.deletable_ids):
            for id in ids_to_edit:
                text_element = self.selectable_elements[id]["node"].find("text")
                success, new_annotation = get(
                    Get.FROM_USER_STRING,
                    "Score Annotation",
                    "Edit annotation",
                    text_element.text,
                )
                if success:
                    text_element.text = new_annotation
                    self._get_bounds(self.selectable_elements, id)
            self.save_to_file(ids_to_edit)
        else:
            self.remove_from_selection(self.selected_elements_id)
        self.__refresh_svg()

    def delete_tla_annotation(self):
        if ids_to_delete := self.selected_elements_id.intersection(self.deletable_ids):
            to_delete = []
            for id in ids_to_delete:
                to_delete.append(self.selectable_elements[id]["component"])
            self.viewer.timeline_ui.timeline.delete_components(to_delete)
        self.remove_from_selection(self.selected_elements_id)
        self.__refresh_svg()

    def _add_text(self, point: QPoint, text: str) -> str:
        tla_id = "tla_" + str(self.next_tla_id)
        glyph = etree.Element("g", {"class": "tla-annotation", "id": tla_id})
        glyph_text = etree.Element(
            "text",
            {
                "stroke-width": "0.3",
                "fill": "#000000",
                "stroke": "none",
                "stroke-dasharray": "none",
                "font-family": "Times New Roman",
                "font-size": "20px",
                "font-weight": "normal",
                "font-style": "oblique",
                "x": str(point.x() / self.transform_x),
                "y": str(point.y() / self.transform_y),
            },
        )
        glyph_text.text = text
        glyph.append(glyph_text)
        self.root.append(glyph)
        self.selectable_elements[tla_id] = {"node": glyph}
        self.deletable_ids.add(tla_id)
        self.__refresh_svg()
        self._get_bounds(self.selectable_elements, tla_id)
        self.next_tla_id += 1
        return tla_id

    def add_tla_annotation(self):
        if ids_to_annotate := self.selected_elements_id.difference(self.deletable_ids):
            to_add = set()
            success, annotation = get(
                Get.FROM_USER_STRING, "Score Annotation", "Add annotation"
            )
            if success:
                for id in ids_to_annotate:
                    to_add.add(
                        self._add_text(
                            self.selectable_elements[id]["bounds"].first(), annotation
                        )
                    )
            self.save_to_file(to_add)
        else:
            self.remove_from_selection(self.selected_elements_id)
        self.__refresh_svg()

    def annotation_zoom_in(self):
        self.remove_from_selection(
            self.selected_elements_id.difference(self.deletable_ids)
        )
        for id in self.selected_elements_id:
            self.selectable_elements[id]["node"][0].attrib["font-size"] = (
                str(
                    int(
                        self.selectable_elements[id]["node"][0]
                        .attrib["font-size"]
                        .strip("px")
                    )
                    * 2
                )
                + "px"
            )
            self._get_bounds(self.selectable_elements, id)
        cur_selection = self.selected_elements_id.copy()
        self.save_to_file(cur_selection)
        self.add_to_selection(cur_selection)

        self.__refresh_svg()

    def annotation_zoom_out(self):
        self.remove_from_selection(
            self.selected_elements_id.difference(self.deletable_ids)
        )
        for id in self.selected_elements_id:
            self.selectable_elements[id]["node"][0].attrib["font-size"] = (
                str(
                    int(
                        self.selectable_elements[id]["node"][0]
                        .attrib["font-size"]
                        .strip("px")
                    )
                    // 2
                )
                + "px"
            )
            self._get_bounds(self.selectable_elements, id)
        cur_selection = self.selected_elements_id.copy()
        self.save_to_file(cur_selection)
        self.add_to_selection(cur_selection)

        self.__refresh_svg()

    def zoom_in(self):
        self.resize(round(self.width() * 1.1), round(self.height() * 1.1))

    def zoom_out(self):
        self.resize(round(self.width() / 1.1), round(self.height() / 1.1))

    def save_to_file(self, ids_to_save: set[int]):
        self.remove_from_selection(self.selected_elements_id)
        for id in ids_to_save:
            if not (score_annotation := self.selectable_elements[id].get("component")):
                (
                    score_annotation,
                    _,
                ) = self.viewer.timeline_ui.timeline.create_component(
                    kind=ComponentKind.SCORE_ANNOTATION
                )
                self.selectable_elements[id].update({"component": score_annotation})

            score_annotation.save_data(
                str(etree.tostring(self.selectable_elements[id]["node"]), "utf-8")
            )

            post(Post.APP_RECORD_STATE, "score annotation")


class SvgWebEngineTracker(QObject):
    def __init__(self, page, on_svg_loaded, display_error):
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


class SvgViewer(ViewWindow, QDockWidget):
    def __init__(self, name: str, tl_ui, *args, **kwargs):
        super().__init__("TiLiA Score Viewer", *args, menu_title=name, **kwargs)
        self.scroll_area = QScrollArea()
        self.scroll_area.setSizeAdjustPolicy(
            QScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.scroll_area.setAutoFillBackground(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidgetResizable(False)

        self.svg_widget = SvgWidget()
        self.scroll_area.setWidget(self.svg_widget)
        self.setWidget(self.scroll_area)

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

        self.is_loaded = False
        self.timeline_ui = tl_ui
        self.visible_measures = [(0, 0), (0, 0)]

    def engine_loaded(self):
        self.is_loaded = True

    def preprocess_svg(self, svg: str):
        svg = sub("\\&\\w+\\;", lambda x: escape(unescape(x.group(0))), svg)
        self.timeline_ui.timeline.set_data("svg_data", svg)

    def load_svg_data(self, data):
        self.svg_widget.load(data)
        self.show()

    def update_annotation(self, data, tl_component):
        self.svg_widget.update_annotation(data, tl_component)

    def to_svg(self, data: str) -> None:
        def convert():
            self.web_engine.page().runJavaScript(f"loadSVG(`{data}`)")

        if self.is_loaded:
            convert()
        else:
            self.web_engine.loadFinished.connect(convert)

    def display_error(self, message: str):
        tilia.errors.display(tilia.errors.SCORE_SVG_CREATE_ERROR, message)

    def update_visible_measures(self, visible_measures: list[dict]):
        if visible_measures != self.visible_measures:
            self.visible_measures = visible_measures
            beat_tl = get(
                Get.TIMELINE_COLLECTION
            ).get_beat_timeline_for_measure_calculation()
            self.timeline_ui.tracker_start = [
                time_x_converter.get_x_by_time(t)
                for t in beat_tl.get_time_by_measure(**visible_measures[0])
            ]
            self.timeline_ui.tracker_end = [
                time_x_converter.get_x_by_time(t)
                for t in beat_tl.get_time_by_measure(**visible_measures[1])
            ]
            self.timeline_ui.update_measure_tracker_position()

            print(
                visible_measures,
                self.timeline_ui.tracker_start,
                self.timeline_ui.tracker_end,
            )

    def position_updated(self, metric_position):
        # TODO: calculate position, update tlui.
        pass
