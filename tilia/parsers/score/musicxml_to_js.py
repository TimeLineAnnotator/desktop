from PyQt6.QtWidgets import QApplication, QDockWidget, QScrollArea
from PyQt6.QtCore import Qt, QRectF, QPointF, QKeyCombination, QPoint
from PyQt6.QtGui import QPolygon
import sys
from pathlib import Path
from PyQt6.QtSvgWidgets import QSvgWidget
import xml.etree.ElementTree as ET
from enum import Enum, auto


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()
        self.tree = NotImplemented
        self.root = NotImplemented

    def reset(self):
        self.selectable = {}
        self.deletable = []
        self.measures = {}
        self.next_tla_id = 0
        self.selection_box = None
        self.selected_elements = []
        self.new_selection = []
        self.previous_selection = []
        self.selection_mode = self.SELECTION_MODE.NEW

    def __refresh_svg(self):
        super().load(bytearray(ET.tostring(self.root)))

    def load(self, path: Path) -> None:
        self.blockSignals(True)
        self.path = path
        with open(path) as file:
            self.tree = ET.parse(file)
        self.root = self.tree.getroot()
        self.svg_width = round(float(self.root.attrib.get("width", 500)))
        self.svg_height = round(float(self.root.attrib.get("height", 500)))
        self.reset()
        self.get_editable_elements(self.root)

        self.__refresh_svg()
        self.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(self.svg_width, self.svg_height)
        self.show()
        self.blockSignals(False)

    def get_editable_elements(self, node: ET.Element):
        if v_class := node.attrib.get("class", None):
            match v_class:
                case "vf-stavenote":
                    self.selectable[node.attrib["id"]] = {"node": node}
                case "tla-annotation":
                    self.selectable[(id := node.attrib["id"])] = {"node": node}
                    self.deletable.append(id)
                    id = int(id.split("tla_")[1])
                    if self.next_tla_id <= id:
                        self.next_tla_id = id + 1
                case "vf-measure":
                    self.measures[node.attrib["id"]] = {"node": node}

        for glyph in node.findall("g"):
            self.get_editable_elements(glyph)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.update_bounds()

    def _get_bounds(self, d: dict, id: str):
        d[id].update(
            {
                "bounds": (
                    self.renderer()
                    .transformForElement(id)
                    .scale(self.transform_x, self.transform_y)
                    .mapToPolygon(self.renderer().boundsOnElement(id).toAlignedRect())
                )
            }
        )

    def update_bounds(self):
        def update(to_update: dict):
            for id in to_update.keys():
                self._get_bounds(to_update, id)

        self.transform_x = self.width() / self.renderer().viewBox().size().width()
        self.transform_y = self.height() / self.renderer().viewBox().size().height()
        update(self.selectable)
        update(self.measures)

    def mousePressEvent(self, a0):
        if Qt.KeyboardModifier.ControlModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.SYMMETRIC_DIFFERENCE
        elif Qt.KeyboardModifier.ShiftModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.UNION
        else:
            self.selection_mode = self.SELECTION_MODE.NEW

        self.selection_box = SvgSelectionBox(a0.position().x(), a0.position().y(), 0, 0)
        self.previous_selection = self.selected_elements

        return super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0):
        if self.selection_box is not None:
            self.selection_box.close_box(a0.position())
            sb = QPolygon(self.selection_box.toAlignedRect(), True)
            self.new_selection = [
                k for (k, v) in self.selectable.items() if v["bounds"].intersects(sb)
            ]
            self.selection_box = None
            self.update_selection()
        return super().mouseReleaseEvent(a0)

    def add_to_selection(self, ids: set[str]):
        def make_coloured(cur_node: ET.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#ff0000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#ff0000"  # use settings
            for child in cur_node:
                make_coloured(child)

        for id in ids:
            make_coloured(self.selectable[id]["node"])
            self.selected_elements.append(id)

    def remove_from_selection(self, ids: set[str]):
        def make_black(cur_node: ET.Element):
            if (fill := cur_node.attrib.get("fill", "none")) and fill != "none":
                cur_node.attrib["fill"] = "#000000"  # use settings
            if (stroke := cur_node.attrib.get("stroke", "none")) and stroke != "none":
                cur_node.attrib["stroke"] = "#000000"  # use settings
            for child in cur_node:
                make_black(child)

        for id in ids:
            make_black(self.selectable[id]["node"])
            self.selected_elements.remove(id)

    def update_selection(self):
        selected = set(self.new_selection)
        previous = set(self.previous_selection)
        match self.selection_mode:
            case self.SELECTION_MODE.NEW:
                self.add_to_selection(selected)
                self.remove_from_selection(previous)

            case self.SELECTION_MODE.SYMMETRIC_DIFFERENCE:
                self.add_to_selection(list(selected.difference(previous)))
                self.remove_from_selection(list(selected.intersection(previous)))

            case self.SELECTION_MODE.UNION:
                self.add_to_selection(list(selected.difference(previous)))

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
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Delete
            ): self.delete_tla_annotation,
            QKeyCombination(
                Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return
            ): self.add_tla_annotation,
        }
        if action := key_comb_to_action.get(a0.keyCombination()):
            action()
        return super().keyPressEvent(a0)

    def delete_tla_annotation(self):
        if deletable := list(set(self.selected_elements).intersection(self.deletable)):
            for element_id in deletable:
                self.root.remove(self.selectable[element_id]["node"])
                self.selectable.pop(element_id)
                self.deletable.remove(element_id)
                self.selected_elements.remove(element_id)
            self.save_to_file()
        else:
            self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def _add_text(self, point: QPoint, text: str):
        id = "tla_" + str(self.next_tla_id)
        glyph = ET.Element("g", {"class": "tla-annotation", "id": id})
        glyph_text = ET.Element(
            "text",
            {
                "stroke-width": "0.3",
                "fill": "#000000",
                "stroke": "none",
                "stroke-dasharray": "none",
                "font-family": "Times New Roman",
                "font-size": "200px",
                "font-weight": "normal",
                "font-style": "normal",
                "x": str(point.x() / self.transform_x),
                "y": str(point.y() / self.transform_y),
            },
        )
        glyph_text.text = text
        glyph.append(glyph_text)
        self.root.append(glyph)
        self.selectable[id] = {"node": glyph}
        self.deletable.append(id)
        self.__refresh_svg()
        self._get_bounds(self.selectable, id)
        self.next_tla_id += 1

    def add_tla_annotation(self):
        if annotatable := list(set(self.selected_elements).difference(self.deletable)):
            for element_id in annotatable:
                self._add_text(
                    self.selectable[element_id]["bounds"].first(), str(self.next_tla_id)
                )
            self.save_to_file()
        else:
            self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def zoom_in(self):
        self.resize(round(self.width() * 1.1), round(self.height() * 1.1))

    def zoom_out(self):
        self.resize(round(self.width() / 1.1), round(self.height() / 1.1))

    def save_to_file(self):
        self.remove_from_selection(self.selected_elements)
        self.tree.write(self.path.__str__())

    def closeEvent(self, a0):
        self.save_to_file()
        return super().closeEvent(a0)


class VexflowViewer(QDockWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Score Viewer")
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

    def load(self, path: Path) -> None:
        self.svg_widget.load(path)

    def closeEvent(self, event):
        self.svg_widget.close()
        return super().closeEvent(event)


app = QApplication(sys.argv)
renderer = VexflowViewer()
renderer.load("tilia/parsers/score/test.svg")
renderer.show()
app.exec()
