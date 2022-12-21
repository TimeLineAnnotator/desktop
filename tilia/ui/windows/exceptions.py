from .kinds import WindowKind


class UniqueWindowDuplicate(Exception):
    def __init__(self, kind: WindowKind):
        self.kind = kind

    def __str__(self):
        return f"Can't instance a second window of kind '{self.kind.value}'"
