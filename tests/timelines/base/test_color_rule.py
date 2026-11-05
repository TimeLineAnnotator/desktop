from PySide6.QtGui import QColor

from tilia.timelines.base.validators import validate_color
from tilia_core import rules


def _samples():
    names = QColor.colorNames()
    return [
        *names,
        *(name.upper() for name in names),
        *(" ".join(name) for name in names),
        "#fff",
        "#FfF",
        "#ffff",
        "#fffff",
        "#ff00ff00",
        "#fffffffff",
        "#ffffffffffff",
        "#fffffffffffffff",
        "#",
        "#+12345",
        "#12 345",
        "#\tfff",
        "#fff\t",
        " #fff",
        "fff",
        "red\t",
        "\tr\te\td\t",
        "red\n",
        "red ",
        "red\x00",
        "re\x00d",
        "redΩ",
        "redΩblah",
        "Khaki",
        "whİte",
        "ſteelblue",
        "ＲＥＤ",
        "red\U0001f3bb",
        "re\ud83d",
        "red\ud83d",
        "\ud83dred",
        "red\udfbb",
        " " * 251 + "red\ud83d",
        " " * 252 + "red\ud83d",
        "notacolor",
        "a" * 300,
        " " * 300 + "red",
        " " * 250 + "red",
    ]


def test_colors_are_those_qt_reads():
    disagree = [
        sample
        for sample in _samples()
        if rules.color(sample).ok is not QColor(sample).isValid()
    ]

    assert disagree == []


def test_the_app_accepts_the_colors_the_core_accepts():
    disagree = [
        sample
        for sample in _samples()
        if validate_color(sample) is not rules.color(sample).ok
    ]

    assert disagree == []


def test_the_app_accepts_the_default_color_and_refuses_what_is_not_text():
    assert validate_color(None) and validate_color("")
    assert not validate_color(0)
    assert not validate_color(True)


def test_the_app_asks_the_core_whether_text_is_a_color(monkeypatch):
    monkeypatch.setattr(rules, "color", lambda value: rules.OK)

    assert validate_color("notacolor")
