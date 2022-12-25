from typing import Any


def default_str_dunder(object_: Any) -> str:
    return f"{object_.__class__.__name__}({id(object_)})"
