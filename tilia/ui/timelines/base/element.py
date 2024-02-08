from __future__ import annotations
import logging
from abc import ABC, abstractmethod

from typing import Optional, Any

from PyQt6.QtCore import QPoint

from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu
from tilia.utils import get_tilia_class_string

from PyQt6.QtWidgets import QGraphicsScene

from tilia.requests import stop_listening_to_all

logger = logging.getLogger(__name__)


class TimelineUIElement(ABC):
    UPDATE_TRIGGERS = []
    CONTEXT_MENU_CLASS: Optional[type(TimelineUIElementContextMenu)] = None
    FIELD_NAMES_TO_ATTRIBUTES: dict[str, str] = {}

    def __init__(
        self,
        *args,
        id: id,
        timeline_ui,
        scene: QGraphicsScene,
        **kwargs,
    ):
        super().__init__()

        self.timeline_ui = timeline_ui
        self.id = id
        self.scene = scene

    def __repr__(self):
        return get_tilia_class_string(self)

    def __lt__(self, other):
        return self.tl_component < other.tl_component

    @property
    def tl_component(self):
        return self.timeline_ui.get_timeline_component(self.id)

    def get_data(self, attr: str):
        return self.timeline_ui.get_component_data(self.id, attr)

    def set_data(self, attr: str, value: Any):
        self.timeline_ui.set_component_data(self.id, attr, value)

    def update(self, attr: str):
        if attr not in self.UPDATE_TRIGGERS:
            return

        update_func_name = "update_" + attr
        if not hasattr(self, update_func_name):
            raise ValueError(f"{self} has no updater function for attribute '{attr}'")

        getattr(self, update_func_name)()

    def is_selected(self):
        return self in self.timeline_ui.selected_elements

    @abstractmethod
    def child_items(self): ...

    def selection_triggers(self):
        return self.child_items()

    def right_click_triggers(self):
        return self.child_items()

    def left_click_triggers(self):
        return []

    def double_left_click_triggers(self):
        return self.child_items()

    def on_right_click(self, x, y, _):
        if not self.CONTEXT_MENU_CLASS:
            return

        menu = self.CONTEXT_MENU_CLASS(self)
        menu.exec(QPoint(x, y))

    def on_select(self):
        ...

    def on_deselect(self):
        ...

    def delete(self):
        for item in self.child_items():
            if item.parentItem():
                continue  # item will be removed with parent
            self.scene.removeItem(item)

        stop_listening_to_all(self)
