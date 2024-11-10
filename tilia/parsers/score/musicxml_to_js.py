from PyQt6.QtWidgets import QApplication, QDockWidget, QScrollArea
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPolygon
import sys
from pathlib import Path
from PyQt6.QtSvgWidgets import QSvgWidget
import xml.etree.ElementTree as ET
from enum import Enum, auto
from collections import OrderedDict


class SvgSelectionBox(QRectF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = QPointF(self.bottomLeft())

    def update(self, point: QPointF):
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
        self.tree_c = NotImplemented

    def reset(self):
        self.annotatable = OrderedDict()
        self.tla_annotation = OrderedDict()
        self.measures = OrderedDict()
        self.next_tla_id = 0
        self.selection_box = None
        self.selected_elements = []
        self.selection_mode = self.SELECTION_MODE.NEW

    def load(self, path: Path) -> None:
        self.blockSignals(True)
        self.path = path
        with open(path) as file:
            self.tree = ET.parse(file)
        with open(path) as file:
            self.tree_c = ET.parse(file)
        root = self.tree.getroot()
        root_c = self.tree_c.getroot()
        self.svg_width = round(float(root.attrib.get("width", 500)))
        self.svg_height = round(float(root.attrib.get("height", 500)))
        self.reset()
        self.get_editable_elements(root, root_c)

        super().load(path.__str__())
        self.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(self.svg_width, self.svg_height)
        self.show()
        self.blockSignals(False)

    def get_editable_elements(self, node: ET.Element, node_c: ET.Element):
        if node.attrib != node_c.attrib:
            print(node, node_c)
        nodes = {"node": node, "node_c": node_c}
        if (v_class := node.attrib.get("class", None)) == "vf-stavenote":
            self.annotatable[node.attrib["id"]] = nodes
        elif v_class == "tla-annotation":
            self.tla_annotation[(id := node.attrib["id"])] = nodes
            id = int(id.split("tla_")[1])
            if self.next_tla_id <= id:
                self.next_tla_id = id + 1
        elif v_class == "vf-measure":
            self.measures[node.attrib["id"]] = nodes
        for glyph, glyph_c in zip(node.findall("g"), node_c.findall("g")):
            self.get_editable_elements(glyph, glyph_c)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.update_bounds()

    def update_bounds(self):
        def update(to_update: OrderedDict):
            for id in to_update.keys():
                to_update[id].update(
                    {
                        "bounds": (
                            self.renderer()
                            .transformForElement(id)
                            .scale(self.transform_x, self.transform_y)
                            .mapToPolygon(
                                self.renderer().boundsOnElement(id).toAlignedRect()
                            )
                        )
                    }
                )

        self.transform_x = self.width() / self.renderer().viewBox().size().width()
        self.transform_y = self.height() / self.renderer().viewBox().size().height()
        update(self.annotatable)
        update(self.measures)
        update(self.tla_annotation)

    def add_text(self, x_list: list[int], y_list: list[int], text: str):
        root = self.tree.getroot()
        root_c = self.tree_c.getroot()
        for x, y in zip(x_list, y_list):
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
                    "x": str(x),
                    "y": str(y),
                },
            )
            glyph_text.text = text
            glyph.append(glyph_text)
            root.append(glyph)
            root_c.append(glyph)
            self.tla_annotation[id] = {"node": glyph, "node_c": glyph}
            self.next_tla_id += 1

        self.tree_c.write(self.path.__str__())
        super().load(self.path.__str__())
        # update coloured tree to match

    def mousePressEvent(self, a0):
        if Qt.KeyboardModifier.ControlModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.SYMMETRIC_DIFFERENCE
        elif Qt.KeyboardModifier.ShiftModifier in a0.modifiers():
            self.selection_mode = self.SELECTION_MODE.UNION
        else:
            self.selection_mode = self.SELECTION_MODE.NEW

        self.selection_box = SvgSelectionBox(a0.position().x(), a0.position().y(), 0, 0)
        self.previous_selection = self.selected_elements
        self.selected_elements = []

        return super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0):
        if self.selection_box is not None:
            self.selection_box.update(a0.position())
            sb = QPolygon(self.selection_box.toAlignedRect(), True)
            self.selected_elements = [
                k for (k, v) in self.annotatable.items() if v["bounds"].intersects(sb)
            ] + [
                k
                for (k, v) in self.tla_annotation.items()
                if v["bounds"].intersects(sb)
            ]
            self.selection_box = None
        else:
            self.selected_elements = [
                k
                for (k, v) in self.annotatable.items()
                if v["bounds"].containsPoint(
                    a0.position().toPoint(), Qt.FillRule.OddEvenFill
                )
            ] + [
                k
                for (k, v) in self.tla_annotation.items()
                if v["bounds"].containsPoint(
                    a0.position().toPoint(), Qt.FillRule.OddEvenFill
                )
            ]

        self.update_selection()
        return super().mouseReleaseEvent(a0)

    def update_selection(self):
        def added_to_selection(ids: list[str]):
            print(ids)

        def removed_from_selection(ids: list[str]):
            print(ids)

        selected = set(self.selected_elements)
        previous = set(self.previous_selection)
        match self.selection_mode:
            case self.SELECTION_MODE.NEW:
                added_to_selection(self.selected_elements)
                removed_from_selection(self.previous_selection)

            case self.SELECTION_MODE.SYMMETRIC_DIFFERENCE:
                added_to_selection(list(selected.difference(previous)))
                removed_from_selection(list(selected.intersection(previous)))
                self.selected_elements = list(selected.symmetric_difference(previous))

            case self.SELECTION_MODE.UNION:
                added_to_selection(list(selected.difference(previous)))
                self.selected_elements = list(selected.union(previous))

        print("final", self.selected_elements)

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

        if Qt.KeyboardModifier.ControlModifier in a0.modifiers():
            if dy > 0:
                self.zoom_in
            else:
                self.zoom_out
            return

    # TODO: delete, zoom
    # def keyPressEvent(self, a0):
    #     if (a0.key() < 71):
    #         self.zoom_in()
    #     else:
    #         self.zoom_out()
    #     return super().keyPressEvent(a0)

    def zoom_in(self):
        self.size().scale
        self.resize(round(self.width() * 1.1), round(self.height() * 1.1))

    def zoom_out(self):
        self.resize(round(self.width() / 1.1), round(self.height() / 1.1))

    def closeEvent(self, a0):
        self.tree.write(self.path.__str__())
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


app = QApplication(sys.argv)
renderer = VexflowViewer()
renderer.load("tilia/parsers/score/test.svg")
renderer.show()
app.exec()
