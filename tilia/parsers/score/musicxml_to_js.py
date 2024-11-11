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
        MOVE = auto()

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
        self.selected_elements = set()
        self.new_selection = set()
        self.previous_selection = set()
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
                    self.selectable[(element := node.attrib["id"])] = {"node": node}
                    self.deletable.append(element)
                    element = int(element.split("tla_")[1])
                    if self.next_tla_id <= element:
                        self.next_tla_id = element + 1
                case "vf-measure":
                    self.measures[node.attrib["id"]] = {"node": node}

        for glyph in node.findall("g"):
            self.get_editable_elements(glyph)

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
        if self.selection_box is not None:
            if self.selection_mode is self.SELECTION_MODE.MOVE:
                self.move_annotation(
                    self.selection_box.bottomLeft(), a0.position(), False
                )
                self.selection_box.moveBottomLeft(a0.position())
            else:
                self.selection_box.close_box(a0.position())
                sb = QPolygon(self.selection_box.toAlignedRect(), True)
                self.new_selection = {
                    k
                    for (k, v) in self.selectable.items()
                    if v["bounds"].intersects(sb)
                }
                self.update_selection()

        return super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0):
        if self.selection_box is not None:
            if self.selection_mode is self.SELECTION_MODE.MOVE:
                self.move_annotation(self.selection_box.bottomLeft(), a0.position())
            else:
                self.selection_box.close_box(a0.position())
                sb = QPolygon(self.selection_box.toAlignedRect(), True)
                self.new_selection = {
                    k
                    for (k, v) in self.selectable.items()
                    if v["bounds"].intersects(sb)
                }
                self.update_selection()
            self.selection_box = None
        return super().mouseReleaseEvent(a0)

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
            self.save_to_file()
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
        if deletable := self.selected_elements.intersection(self.deletable):
            for element in deletable:
                self.root.remove(self.selectable[element]["node"])
                self.selectable.pop(element)
                self.deletable.remove(element)
                self.selected_elements.remove(element)
            self.save_to_file()
        else:
            self.remove_from_selection(self.selected_elements)
        self.__refresh_svg()

    def _add_text(self, point: QPoint, text: str):
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
        self.deletable.append(tla_id)
        self.__refresh_svg()
        self._get_bounds(self.selectable, tla_id)
        self.next_tla_id += 1

    def add_tla_annotation(self):
        if annotatable := self.selected_elements.difference(self.deletable):
            for element in annotatable:
                self._add_text(
                    self.selectable[element]["bounds"].first(), str(self.next_tla_id)
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
