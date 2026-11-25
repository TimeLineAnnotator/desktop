from PySide6.QtGui import QFontMetricsF, QTextCharFormat
from PySide6.QtWidgets import QGraphicsTextItem

from tilia.ui.timelines.harmony.utils import UNREADABLE


class LabelBody(QGraphicsTextItem):
    """A harmony's or a mode's label. The marks that stand where TiLiA can't read what
    a file holds are drawn in Arial, the rest in the label's font: MusAnalysis draws a
    question mark as a bar, and "C-" is a way to write C minor (Anne, 2026-11-25,
    TimeLineAnnotator/project-management#689, b)."""

    has_marks = False

    def set_plain_text(self, text: str, has_marks: bool) -> None:
        """`has_marks` is whether the question marks in it are marks."""
        self.setPlainText(text)
        self.has_marks = has_marks and UNREADABLE in text
        if not self.has_marks:
            return
        # The family alone, so that a mark is bold when the label is.
        arial = QTextCharFormat()
        arial.setFontFamilies(["Arial"])
        mark = self.document().find(UNREADABLE)
        while not mark.isNull():
            mark.mergeCharFormat(arial)
            mark = self.document().find(UNREADABLE, mark)

    def marks_y_offset(self) -> float:
        """How far down a label with marks goes for its line to be where the others'
        is: the line of a mark alone is as high as Arial, not as the label's font."""
        if not self.has_marks:
            return 0
        line = self.document().firstBlock().layout().lineAt(0)
        return QFontMetricsF(self.font()).ascent() - line.ascent()
