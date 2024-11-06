import math
from typing import Any

from PyQt6.QtGui import QColor


def validate_time(value):
    return isinstance(value, (float, int)) and value >= 0


def validate_string(value):
    return isinstance(value, str)


def validate_bool(value):
    return isinstance(value, bool)


def validate_color(value):
    if value is None:
        return True
    return QColor(value).isValid()


def validate_read_only(_):
    return False


def validate_boolean(value):
    return isinstance(value, bool)


def validate_integer(value):
    return isinstance(value, int)


def validate_non_negative_integer(value):
    return isinstance(value, int) and value >= 0


def validate_positive_integer(value):
    return isinstance(value, int) and value > 0


def validate_bounded_integer(value: int, lower=-math.inf, upper=math.inf):
    return isinstance(value, int) and lower <= value <= upper


def validate_pre_validated(_):
    return True


def validate_is_instance(cls: type, value: Any) -> bool:
    return isinstance(value, cls)
