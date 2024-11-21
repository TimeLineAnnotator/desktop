# TODO:
# - measure tracker
# - lxml

from enum import Enum, auto
from html import escape, unescape
from pathlib import Path
from re import sub
from xml.etree import ElementTree as ET

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
        self.root = ET.Element("svg")

    def reset(self):
        self.selectable = {}
        self.deletable = set()
        self.measures = {}
        self.next_tla_id = 0
        self.selection_box = None
        self.selected_elements = set()
        self.new_selection = set()
        self.previous_selection = set()
        self.selection_mode = self.SELECTION_MODE.NEW

    def __refresh_svg(self):
        super().load(bytearray(ET.tostring(self.root)))

    @property
    def viewer(self):
        return self.parent().parent().parent()

    def load(self, data):
        self.blockSignals(True)
        old_selectable = self.selectable.copy()
        old_deletable = self.deletable.copy()
        self.root = ET.fromstring(data)
        self.svg_width = round(float(self.root.attrib.get("width", 500)))
        self.svg_height = round(float(self.root.attrib.get("height", 500)))
        self.reset()
        self.get_editable_elements(self.root)
        for deletable in old_deletable:
            self.selectable[deletable] = old_selectable[deletable]
            self.root.append(old_selectable[deletable]["node"])
        self.deletable = old_deletable

        self.__refresh_svg()
        self.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(self.svg_width, self.svg_height)
        self.show()
        self.blockSignals(False)

    def update_annotation(self, data, tl_component):
        if data == "delete":
            id = [
                d
                for d in self.deletable
                if self.selectable[d]["component"] is tl_component
            ][0]
            self.root.remove(self.selectable[id]["node"])
            self.selectable.pop(id)
            self.deletable.remove(id)
            if id in self.selected_elements:
                self.selected_elements.remove(id)

        else:
            annotation = ET.fromstring(data)
            self.root.append(annotation)
            if (id := annotation.attrib.get("id")) in self.deletable:
                self.root.remove(self.selectable[id]["node"])
            else:
                self.selectable[id] = {"component": tl_component}
                self.deletable.add(id)
                self.check_tla_id(id)
                if hasattr(self, "transform_x"):
                    self._get_bounds(self.selectable, id)
            self.selectable[id]["node"] = annotation

        self.__refresh_svg()

    def check_tla_id(self, id):
        id = int(id.split("tla_")[1])
        if self.next_tla_id <= id:
            self.next_tla_id = id + 1

    def get_editable_elements(self, node: ET.Element):
        for glyph in node.findall("g"):
            self.get_editable_elements(glyph)

        if not (v_class := node.attrib.get("class", None)):
            return

        match v_class:
            case "vf-stavenote":
                self.selectable[node.attrib["id"]] = {"node": node}
            case "vf-measure":
                self.measures[node.attrib["id"]] = {"node": node}

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.update_bounds()

    def _get_bounds(self, d: dict, element: str):
        d[element].update(
            {
                "bounds": (
                    self.renderer()
                    .transformForElement(element)
                    .scale(self.transform_x, self.transform_y)
                    .mapToPolygon(
                        self.renderer().boundsOnElement(element).toAlignedRect()
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
        update(self.selectable)
        update(self.measures)

    def mousePressEvent(self, a0):
        if (to_move := self.selected_elements.intersection(self.deletable)) and [
            k
            for k in to_move
            if self.selectable[k]["bounds"].containsPoint(
                a0.position().toPoint(), Qt.FillRule.OddEvenFill
            )
        ]:
            self.to_move = to_move
            self.remove_from_selection(self.selected_elements.difference(to_move))
            self.selection_mode = self.SELECTION_MODE.MOVE
        elif Qt.KeyboardModifier.ControlModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.SYMMETRIC_DIFFERENCE
        elif Qt.KeyboardModifier.ShiftModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.UNION
        else:
            self.selection_mode = self.SELECTION_MODE.NEW

        self.selection_box = SvgSelectionBox(a0.position().x(), a0.position().y(), 0, 0)
        self.previous_selection = self.selected_elements.copy()

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
                k for (k, v) in self.selectable.items() if v["bounds"].intersects(sb)
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
                k for (k, v) in self.selectable.items() if v["bounds"].intersects(sb)
            }
            self.update_selection()
        self.selection_box = None

    def add_to_selection(self, elements):
        def make_coloured(cur_node: ET.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#ff0000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#ff0000"  # use settings
            for child in cur_node:
                make_coloured(child)

        for element in elements:
            make_coloured(self.selectable[element]["node"])
            self.selected_elements.add(element)

    def remove_from_selection(self, elements):
        def make_black(cur_node: ET.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#000000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#000000"  # use settings
            for child in cur_node:
                make_black(child)

        for element in elements:
            make_black(self.selectable[element]["node"])
        self.selected_elements.difference_update(elements)

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

        self.add_to_selection(in_selection.difference(self.selected_elements))
        self.remove_from_selection(self.selected_elements.difference(in_selection))

        self.__refresh_svg()

    def move_annotation(self, start: QPointF, end: QPointF, is_final: bool = True):
        x = end.x() - start.x()
        y = end.y() - start.y()
        for element in self.to_move:
            self.selectable[element]["node"][0].attrib["x"] = str(
                float(self.selectable[element]["node"][0].attrib["x"]) + x
            )
            self.selectable[element]["node"][0].attrib["y"] = str(
                float(self.selectable[element]["node"][0].attrib["y"]) + y
            )
            self._get_bounds(self.selectable, element)
        if is_final:
            self.save_to_file(self.to_move)
        self.__refresh_svg()

    def enterEvent(self, event):
        self.setFocus()
        return super().enterEvent(event)

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
        if annotation := self.selected_elements.intersection(self.deletable):
            for element in annotation:
                text_element = self.selectable[element]["node"].find("text")
                new_annotation, success = get(
                    Get.FROM_USER_STRING,
                    "Score Annotation",
                    "Edit annotation",
                    text_element.text,
                )
                if success:
                    text_element.text = new_annotation
            self.save_to_file(annotation)
        else:
            self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def delete_tla_annotation(self):
        if deletable := self.selected_elements.intersection(self.deletable):
            to_delete = []
            for element in deletable:
                self.root.remove(self.selectable[element]["node"])
                to_delete.append(self.selectable[element]["component"])
                self.selectable.pop(element)
                self.deletable.remove(element)
                self.selected_elements.remove(element)
            self.viewer.measure_box.timeline.delete_components(to_delete)
        self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def _add_text(self, point: QPoint, text: str) -> str:
        tla_id = "tla_" + str(self.next_tla_id)
        glyph = ET.Element("g", {"class": "tla-annotation", "id": tla_id})
        glyph_text = ET.Element(
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
        self.selectable[tla_id] = {"node": glyph}
        self.deletable.add(tla_id)
        self.__refresh_svg()
        self._get_bounds(self.selectable, tla_id)
        self.next_tla_id += 1
        return tla_id

    def add_tla_annotation(self):
        if annotatable := self.selected_elements.difference(self.deletable):
            to_add = set()
            success, annotation = get(
                Get.FROM_USER_STRING, "Score Annotation", "Add annotation"
            )
            if success:
                for element in annotatable:
                    to_add.add(
                        self._add_text(
                            self.selectable[element]["bounds"].first(), annotation
                        )
                    )
            self.save_to_file(to_add)
        else:
            self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def annotation_zoom_in(self):
        self.remove_from_selection(self.selected_elements.difference(self.deletable))
        for element in self.selected_elements:
            self.selectable[element]["node"][0].attrib["font-size"] = (
                str(
                    int(
                        self.selectable[element]["node"][0]
                        .attrib["font-size"]
                        .strip("px")
                    )
                    * 2
                )
                + "px"
            )
        cur_selection = self.selected_elements
        self.save_to_file(cur_selection)
        self.add_to_selection(cur_selection)

        self.__refresh_svg()

    def annotation_zoom_out(self):
        self.remove_from_selection(self.selected_elements.difference(self.deletable))
        for element in self.selected_elements:
            self.selectable[element]["node"][0].attrib["font-size"] = (
                str(
                    int(
                        self.selectable[element]["node"][0]
                        .attrib["font-size"]
                        .strip("px")
                    )
                    // 2
                )
                + "px"
            )
        cur_selection = self.selected_elements
        self.save_to_file(cur_selection)
        self.add_to_selection(cur_selection)

        self.__refresh_svg()

    def zoom_in(self):
        self.resize(round(self.width() * 1.1), round(self.height() * 1.1))

    def zoom_out(self):
        self.resize(round(self.width() / 1.1), round(self.height() / 1.1))

    def save_to_file(self, elements: set[int]):
        self.remove_from_selection(self.selected_elements)
        if self.viewer.measure_box:
            for element in elements:
                if not (score_annotation := self.selectable[element].get("component")):
                    (
                        score_annotation,
                        _,
                    ) = self.viewer.measure_box.timeline.create_component(
                        kind=ComponentKind.SCORE_ANNOTATION
                    )
                    self.selectable[element].update({"component": score_annotation})

                score_annotation.save_data(
                    ET.tostring(self.selectable[element]["node"], "unicode")
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
    def __init__(self, name: str, *args, **kwargs):
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
        self.measure_box = None

    def engine_loaded(self):
        self.is_loaded = True

    def preprocess_svg(self, svg: str):
        svg = sub("\\&\\w+\\;", lambda x: escape(unescape(x.group(0))), svg)
        self.measure_box.timeline.set_data("svg_data", svg)

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
