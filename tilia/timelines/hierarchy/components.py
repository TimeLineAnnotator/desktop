"""
Defines the Hierarchy class, the single TimelineComponent kind of a HierarchyTimeline.
"""

from __future__ import annotations

from typing import Union, Any, TYPE_CHECKING

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.state_actions import StateAction
from tilia.misc_enums import StartOrEnd

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.timeline import HierarchyTimeline

import tkinter as tk
import tkinter.messagebox

from tilia.exceptions import AppException

from tilia.timelines.common import (
    TimelineComponent,
    log_object_deletion,
)
from tilia.files import UndoRedoStack
import tilia.globals_ as globals_

import logging

logger = logging.getLogger(__name__)

LOGGER = logging.getLogger(__name__)


class HierarchyLoadError(Exception):
    pass


class Hierarchy(TimelineComponent):

    # to be used on future reimplementation of copy/paste
    COPYABLE_ATTRS = ["label", "formal_type", "formal_function", "comments", "color"]
    COPY_HELPER_ATTRS = ["level"]

    # serializer attributes
    SERIALIZABLE_BY_VALUE = [
        "start",
        "end",
        "level",
        "formal_type",
        "formal_function",
        "comments",
    ]

    SERIALIZABLE_BY_UI_VALUE = ["label", "color"]
    SERIALIZABLE_BY_ID = ["parent"]
    SERIALIZABLE_BY_ID_LIST = ["children"]

    KIND = ComponentKind.HIERARCHY

    def __init__(
        self,
        timeline: HierarchyTimeline,
        start: float,
        end: float,
        level: int,
        parent=None,
        children=None,
        comments="",
        formal_type="",
        formal_function="",
        **_,
    ):

        super().__init__(timeline)

        self.start = start
        self.end = end
        self.level = level
        self.comments = comments

        self.formal_type = formal_type
        self.formal_function = formal_function

        self.parent = parent

        if children:
            self.children = children
        else:
            self.children = []

        self.ui = None

    @classmethod
    def create(
        cls, timeline: HierarchyTimeline, start: float, end: float, level: int, **kwargs
    ):
        return Hierarchy(timeline, start, end, level, **kwargs)

    def receive_delete_request_from_ui(self) -> None:
        self.timeline.on_request_delete_component(self)
        self.ui.delete()

    def on_ui_changes_start_or_end_time(
        self, time: float, extremity: StartOrEnd
    ) -> None:
        logger.debug(f"Changing {self} {extremity.value} to {time}")
        setattr(self, extremity.value, time)

        # noinspection PyUnresolvedReferences
        class HierarchyRightClickMenu(tk.Menu):
            def __init__(self, unit):
                super().__init__(tearoff=0)
                self.add_command(
                    label="Change unit color", command=unit.ask_change_color
                )
                self.add_command(label="Reset unit color", command=unit.reset_color)

        def __repr__(self):
            repr_ = f"Hierarchy({self.start}, {self.end}, {self.level}"
            try:
                if self.ui.label:
                    repr_ += f", {self.ui.label}"
            except AttributeError:
                pass  # UI has not been created yet
            repr_ += ")"
            return repr_


# noinspection PyUnresolvedReferences,PySuperArguments
class OldCopyPaster:
    """Kept for easy reference. Will be deleted soon."""

    def receive_paste(self, copy_dict: dict[str:Any], no_record=False):

        if not no_record:
            self.collection.state_stack.record("Paste")

        super().receive_paste(copy_dict)
        self.update_drawing()

    def copy(self) -> dict:
        copy_dict = super().copy()
        if self.children:
            copy_dict["children"] = [child.copy() for child in self.children]

        return copy_dict

    def _check_paste(self, copy_dict: dict) -> bool:
        if self.comments:
            return self.ask_confirm_paste_overwrite_comments()
        else:
            return True

    @staticmethod
    def ask_confirm_paste_overwrite_comments():
        return tkinter.messagebox.askyesno(
            "Confirm paste",
            f"Destination unit has comments. Paste and overwrite comments?",
        )

    def _check_special_paste(self, copy_dict: dict) -> bool:
        if self.level != int(copy_dict["helper_attrs"]["level"]):
            globals_.APP.display_error(
                "Can't paste all of unit's attributes into unit of different level."
            )
            return False
        elif any(
            [bool(unit.comments) for unit in self.collection.get_units_below(self)]
        ):
            return self.ask_confirm_special_paste_overwrite_comments()
        else:
            return True

    @staticmethod
    def ask_confirm_special_paste_overwrite_comments():
        return tkinter.messagebox.askyesno(
            "Confirm paste",
            f"Destination unit and/or its children have comments. Paste and overwrite comments?",
        )

    def higher_unit_authorizes_special_paste(self):
        return any(
            [
                unit.authorizes_special_paste
                for unit in self.collection.get_units_above(self)
            ]
        )

    def special_receive_paste(self, copy_dict: dict, no_record=False) -> None:
        """Receives special paste and overwrites self's children, if any,
        with copied children."""

        if not self._check_special_paste(copy_dict):
            return

        if not no_record:
            self.collection.state_stack.record("paste")

        super(Hierarchy, self).special_receive_paste(copy_dict)

        if self.children:
            for child in self.children.copy():
                child.delete(no_record=True, delete_descendants=True)

        copied_length = copy_dict["extension"]["end"] - copy_dict["extension"]["start"]
        scale_factor = self.length_in_seconds / copied_length

        try:
            self._receive_children_paste(copy_dict, scale_factor)
        except KeyError:
            pass

        self.gui.update_gui(*self.get_update_gui_args())
        self.collection.special_paste_authorized = False

    def _receive_children_paste(self, copy_dict: dict, scale_factor: float):
        children_dicts = copy_dict["children"]

        for child_dict in children_dicts:
            start = child_dict["extension"]["start"] - copy_dict["extension"]["start"]
            end = child_dict["extension"]["end"] - copy_dict["extension"]["start"]
            level = child_dict["helper_attrs"]["level"]
            pasted_child = Hierarchy(
                scale_factor * start + self.start,
                scale_factor * end + self.start,
                level,
                self.collection,
                parent=self,
            )
            self.receive_child(pasted_child)

            pasted_child.special_receive_paste(child_dict, no_record=True)


class HierarchyOperationError(AppException):
    pass
