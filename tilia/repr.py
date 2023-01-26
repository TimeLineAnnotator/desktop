from typing import Any


def default_str(self: Any) -> str:
    return self.__class__.__name__ + "-" + str(id(self))
