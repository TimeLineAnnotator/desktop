from tilia.ui.windows.kinds import WindowKind


class UniqueWindowDuplicate(Exception):
    def __init__(self, window_kind: WindowKind):
        ...
