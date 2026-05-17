# noinspection PyUnresolvedReferences
class CursorMixIn:
    def __init__(self, cursor_shape, *args, **kwargs):
        super().__init__(*args, *kwargs)
        self.setCursor(cursor_shape)
        self.setAcceptHoverEvents(True)
