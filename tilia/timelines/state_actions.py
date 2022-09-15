"""Enum for action names to be recorded by UndoRedoStack (to be implemented)."""

from enum import Enum


class StateAction(Enum):
    PASTE = "PASTE"
    MERGE = "MERGE"
    CLEAR_TIMELINE = "CLEAR COMPONENT MANAGER"
    SPLIT = "SPLIT"
    GROUP = "GROUP"
    CHANGE_LEVEL = "CHANGE LEVEL"
    CREATE_UNIT_BELOW = "CREATE UNIT BELOW"
    DELETE = "DELETE"
