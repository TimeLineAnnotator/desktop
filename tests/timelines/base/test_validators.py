from PySide6.QtGui import QColor

from tilia.timelines.base.validators import validate_color


def test_validate_color_none():
    assert validate_color(None) is True


def test_validate_color_empty_string():
    assert validate_color("") is True


def test_validate_color_valid_name():
    assert validate_color("red") is True
    assert validate_color("blue") is True


def test_validate_color_valid_hex():
    assert validate_color("#ff0000") is True
    assert validate_color("#f00") is True


def test_validate_color_valid_qcolor():
    assert validate_color(QColor("red")) is True


def test_validate_color_invalid_string():
    assert validate_color("not-a-color") is False


def test_validate_color_invalid_type():
    assert validate_color(object()) is False
    assert validate_color([]) is False
    assert validate_color({}) is False
