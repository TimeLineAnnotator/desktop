from __future__ import annotations

import typing

import music21
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsTextItem
from music21.roman import RomanNumeral

from . import harmony_attrs
from tilia.requests import get, Get, post, Post
from tilia.ui.coords import get_x_by_time, get_time_by_x
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.drag import DragManager
from tilia.ui.timelines.harmony.constants import (
    INT_TO_NOTE_NAME,
    QUALITY_TO_ABBREVIATION,
    INT_TO_ROMAN,
    INVERSION_TO_INTERVAL,
    Accidental,
)
from tilia.ui.timelines.harmony.context_menu import HarmonyContextMenu
from tilia.ui.timelines.harmony.utils import to_roman_numeral

if typing.TYPE_CHECKING:
    from tilia.ui.timelines.harmony import HarmonyTimelineUI


class HarmonyUI(TimelineUIElement):
    INSPECTOR_FIELDS = harmony_attrs.INSPECTOR_FIELDS
    FIELD_NAMES_TO_ATTRIBUTES = harmony_attrs.FIELD_NAMES_TO_ATTRIBUTES
    DEFAULT_COPY_ATTRIBUTES = harmony_attrs.DEFAULT_COPY_ATTRIBUTES
    UPDATE_TRIGGERS = [
        "step",
        "accidental",
        "quality",
        "inversion",
        "level",
        "time",
        "applied_to",
        "display_mode",
        "custom_text",
        "custom_text_font_type",
    ]

    CONTEXT_MENU_CLASS = HarmonyContextMenu

    def __init__(
        self,
        id: int,
        timeline_ui: HarmonyTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()

        self.dragged = False
        self.drag_manager = None

    def _setup_body(self):
        self.body = HarmonyBody(self.x, self.y, self.label, self.font_type)
        self.scene.addItem(self.body)

    @property
    def x(self):
        return get_x_by_time(self.get_data("time"))

    @property
    def y(self):
        return (self.timeline_ui.get_y(self.get_data("level"))) + 5

    @property
    def font_type(self):
        if self.get_data("display_mode") == "custom":
            return self.get_data("custom_text_font_type")
        else:
            return "analytic"

    @property
    def key(self):
        return self.timeline_ui.get_key_by_time(self.get_data("time"))

    @property
    def chord_symbol(self):
        symbol = music21.harmony.ChordSymbol(
            INT_TO_NOTE_NAME[self.get_data("step")]
            + Accidental.get_from_int(
                "music21",
                self.get_data("accidental"),
            )
            + QUALITY_TO_ABBREVIATION[self.get_data("quality")],
            inversion=self.get_data("inversion"),
        )
        applied_to = self.get_data("applied_to")
        if applied_to:
            symbol.romanNumeral = RomanNumeral(
                f"{symbol.romanNumeral.figure}/{INT_TO_ROMAN[applied_to]}"
            )
        return symbol

    @property
    def roman_numeral(self):
        return self.chord_symbol.romanNumeral

    @property
    def label(self):
        match self.get_data("display_mode"):
            case "chord":
                return self.chord_symbol_label
            case "roman":
                return self.roman_numeral_label
            case "custom":
                return self.get_data("custom_text")
            case _:
                raise ValueError("Invalid display mode.")

    @property
    def alternate_label(self):
        return (
            self.chord_symbol_label
            if self.get_data("display_mode") == "roman"
            else self.roman_numeral_label
        )

    @property
    def roman_numeral_label(self):
        return to_roman_numeral(
            self.get_data("step"),
            self.get_data("accidental"),
            self.get_data("quality"),
            self.key,
            self.get_data("applied_to"),
            self.get_data("inversion"),
        )

    @property
    def chord_symbol_label(self):
        figure = self.chord_symbol.figure
        match self.get_data("quality"):
            case "Italian":
                return "It6+"
            case "French":
                return "Fr6+"
            case "German":
                return "Gr6+"
            case "Neapolitan":
                return "N6"
            case "power":
                return figure.replace("o", "@o")
            case "Tristan":
                return figure.replace("n", "@n")
            case "seventh-flat-five":
                return figure.replace("dom7dim5", "7((b5))")
        match self.get_data("accidental"):
            case -2:
                figure = figure.replace("--", "`b`b")
            case -1:
                figure = figure.replace("-", "b")
            case 2:
                figure = figure.replace("##", "`#`#")

        if inversion := self.get_data("inversion"):
            # bass_step = harmony.calculate.bass_step(self.get_data('step'), inversion)
            # figure += '/' + INT_TO_NOTE_NAME[bass_step]  # TODO calculate bass note
            figure += "/&" + str(INVERSION_TO_INTERVAL[inversion])

        figure = figure.replace("M7", "^^7")
        figure = figure.replace("M9", "^^9")
        figure = figure.replace("M11", "^^11")
        figure = figure.replace("M13", "^^13")

        if "11th" in self.get_data("quality"):
            figure += "   "

        return figure

    @property
    def seek_time(self):
        return self.get_data("time")

    def update_step(self):
        self.update_label()

    def update_accidental(self):
        self.update_label()

    def update_quality(self):
        self.update_label()

    def update_inversion(self):
        self.update_label()

    def update_applied_to(self):
        self.update_label()

    def update_level(self):
        self.update_label()

    def update_display_mode(self):
        self.update_label()
        self.update_custom_text_font_type()

    def update_custom_text(self):
        self.update_label()

    def update_custom_text_font_type(self):
        if (
            self.get_data("display_mode") == "custom"
            and self.get_data("custom_text_font_type") == "normal"
        ):
            self.body.set_font_type("normal")
        else:
            self.body.set_font_type("analytic")

    def update_label(self):
        self.body.set_text(self.label)
        # self.body.set_alternate_text(self.alternate_lable)
        self.body.set_position(self.x, self.y)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.x, self.y)

    def child_items(self):
        return [self.body]

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body]

    def on_left_click(self, _) -> None:
        self.setup_drag()

    def double_left_click_triggers(self):
        return [self.body]

    def on_double_left_click(self, _):
        if self.drag_manager:
            self.drag_manager.on_release()
            self.drag_manager = None
        post(Post.PLAYER_SEEK, self.seek_time)

    def setup_drag(self):
        self.drag_manager = DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def before_each_drag(self):
        if not self.dragged:
            post(Post.ELEMENT_DRAG_START)
            self.dragged = True

    def after_each_drag(self, drag_x: int):
        self.set_data("time", get_time_by_x(drag_x))
        self.update_label()

    def on_drag_end(self):
        if self.dragged:
            post(Post.APP_RECORD_STATE, "harmony drag")
            post(Post.ELEMENT_DRAG_END)

        self.dragged = False
        self.drag_manager = None

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def get_inspector_dict(self) -> dict:
        return harmony_attrs.get_inspector_dict(self)


class HarmonyBody(QGraphicsTextItem):
    REGULAR_FONT_Y_OFFSET = 5
    def __init__(
        self,
        x: float,
        y: float,
        text: str,
        # alternate_text: str,
        font_type: str,
    ):
        super().__init__()
        self._setup_font(font_type)
        self.set_text(text)
        self.set_position(x, y)
        # self.setToolTip(alternate_text)

    def _setup_font(self, font_type):
        self.setFont(self.get_font(font_type))
        self.setDefaultTextColor(QColor("black"))

    @staticmethod
    def get_font(font_type):
        return QFont("MusAnalysis" if font_type == "analytic" else "Georgia", 10)

    def get_point(self, x: float, y: float):
        return QPointF(
            x - self.boundingRect().width() / 2,
            y + (self.REGULAR_FONT_Y_OFFSET if self.font().family() == 'Georgia' else 0)
        )

    def set_position(self, x, y):
        self.setPos(self.get_point(x, y))

    def set_text(self, value: str):
        self.setPlainText(value)

    def set_font_type(self, font_type):
        font = self.get_font(font_type)
        if font.family() == self.font().family():
            return

        self.setFont(font)
        self.setY(self.y() + self.REGULAR_FONT_Y_OFFSET * (1 if font_type == "normal" else -1))

    # def set_alternate_text(self, value: str):
    #     self.setToolTip(value)

    def on_select(self):
        font = self.font()
        font.setBold(True)
        self.setFont(font)

    def on_deselect(self):
        font = self.font()
        font.setBold(False)
        self.setFont(font)
