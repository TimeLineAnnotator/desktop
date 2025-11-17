from PySide6.QtGui import QColor


def get_tinted_color(color: str, factor: int) -> str:
    return QColor(color).darker(factor).name()


def get_untinted_color(color: str, factor: int) -> str:
    return QColor(color).lighter(factor).name()
