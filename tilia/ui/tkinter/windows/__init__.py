from tilia.ui.tkinter.windows.kinds import WindowKind


class UniqueWindowDuplicate(Exception):
    def __init__(self, window_kind: WindowKind):
        ...
