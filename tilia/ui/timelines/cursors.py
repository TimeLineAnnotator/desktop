from PySide6.QtGui import QGuiApplication


# noinspection PyUnresolvedReferences
class CursorMixIn:
    def __init__(self, cursor_shape, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.cursor_shape = cursor_shape
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event) -> None:
        QGuiApplication.setOverrideCursor(self.cursor_shape)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        QGuiApplication.restoreOverrideCursor()
        super().hoverLeaveEvent(event)

    def cleanup(self):
        QGuiApplication.restoreOverrideCursor()
