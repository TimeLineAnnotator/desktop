from PyQt6.QtWidgets import QApplication, QDockWidget, QScrollArea
from PyQt6.QtCore import Qt
import sys
from pathlib import Path
from PyQt6.QtSvgWidgets import QSvgWidget
import xml.etree.ElementTree as ET


class SvgWidget(QSvgWidget):
    def load(self, path: Path) -> None:
        self.blockSignals(True)
        self.path = path
        with open(path) as file:
            root = ET.parse(file).getroot()
        self.svg_width = round(float(root.attrib.get("width", 500)))
        self.svg_height = round(float(root.attrib.get("height", 500)))
        self.annotatable_ids = []
        self.tla_annotation_ids = []
        self.measure_ids = []
        self.annotatable_bounds = {}
        self.measure_bounds = {}
        self.next_tla_id = 0
        self.get_editable_elements(root)

        super().load(path.__str__())
        self.renderer().setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(self.svg_width, self.svg_height)
        self.show()
        self.blockSignals(False)
        self.update_bounds()

    def get_editable_elements(self, node: ET.Element):
        if (v_class := node.attrib.get("class", None)) == "vf-stavenote":
            self.annotatable_ids.append(node.attrib["id"])
        elif v_class == "tla-annotation":
            self.tla_annotation_ids.append((id := node.attrib["id"]))
            id = int(id.split("tla_")[1])
            if self.next_tla_id <= id:
                self.next_tla_id = id + 1
        elif v_class == "vf-measure":
            self.measure_ids.append(node.attrib["id"])
        for glyph in node.findall("g"):
            self.get_editable_elements(glyph)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.update_bounds()

    def update_bounds(self):
        self.transform_x = self.width() / self.renderer().viewBox().size().width()
        self.transform_y = self.height() / self.renderer().viewBox().size().height()
        self.annotatable_bounds = {}
        self.measure_bounds = {}
        for id in self.annotatable_ids:
            self.annotatable_bounds[id] = (
                self.renderer()
                .transformForElement(id)
                .scale(self.transform_x, self.transform_y)
                .mapToPolygon(self.renderer().boundsOnElement(id).toAlignedRect())
            )
        for id in self.measure_ids:
            self.measure_bounds[id] = (
                self.renderer()
                .transformForElement(id)
                .scale(self.transform_x, self.transform_y)
                .mapToPolygon(self.renderer().boundsOnElement(id).toAlignedRect())
            )

    def add_text(self, x: int, y: int):
        with open(self.path) as file:
            tree = ET.parse(file)
        root = tree.getroot()
        annotation = ET.Element(
            "g", {"class": "tla-annotation", "id": "tla_" + str(self.next_tla_id)}
        )
        text = ET.Element(
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
        text.text = str(self.next_tla_id)
        annotation.append(text)

        root.append(annotation)
        tree.write(self.path.__str__())

        super().load(self.path.__str__())
        self.next_tla_id += 1

    def mouseReleaseEvent(self, a0):
        hit_elements = [
            k
            for (k, v) in self.annotatable_bounds.items()
            if v.containsPoint(a0.position().toPoint(), Qt.FillRule.OddEvenFill)
        ]
        if hit_elements:
            self.add_text(
                round(a0.position().x() / self.transform_x),
                round(a0.position().y() / self.transform_y),
            )
        return super().mouseReleaseEvent(a0)

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
