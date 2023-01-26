from __future__ import annotations

from tilia import events
from tilia.events import Event, subscribe

import logging

from typing import TYPE_CHECKING, Protocol

from tilia.repr import default_str

if TYPE_CHECKING:
    from tilia._tilia import TiLiA

from tilia.timelines.state_actions import Action

logger = logging.getLogger(__name__)


class UndoManager:
    def __init__(self) -> None:

        subscribe(self, Event.REQUEST_TO_UNDO, self.undo)
        subscribe(self, Event.REQUEST_TO_REDO, self.redo)

        self.stack = []
        self.current_state_index = -1
        self.last_repeat_id = None

    def __str__(self):
        return default_str(self)

    def record(
        self,
        state,
        action: Action,
        no_repeat=False,
        repeat_identifier="",
    ):
        """
        Records given app 'state' to UndoManager's stack. Should be called by the TiLiA object.
        The TiLiA call should to be triggered by posting Event.REQUEST_RECORD_STATE
        *after*
        'action' has been done.
        """

        # discard undone states, if any
        self.discard_undone()

        logger.debug(f"Recording {action}.")

        if no_repeat and self.last_repeat_id == repeat_identifier:
            logger.debug(
                f"No repeat is on and action is same last ({action}, {repeat_identifier})."
                f" Updating recorded state."
            )
            self.stack[-1]["state"] = state
            return

        self.stack.append({"state": state, "action": action})
        logger.debug(f"State recorded.")

        if repeat_identifier:
            self.last_repeat_id = repeat_identifier

    def undo(self):
        """Undoes last action"""

        if abs(self.current_state_index) == len(self.stack):
            logger.debug(f"No actions to undo.")
            return

        last_state = self.stack[self.current_state_index - 1]["state"]
        last_action = self.stack[self.current_state_index - 1]["action"]
        current_action = self.stack[self.current_state_index]["action"]

        logger.debug(f"Undoing {current_action}...")

        events.post(Event.REQUEST_RESTORE_APP_STATE, last_state)

        logger.debug(f"Undone {current_action}.")

        self.current_state_index -= 1

    def redo(self):
        """Redoes next action on stack"""
        logger.debug(f"Redoing action...")

        if self.current_state_index == -1:
            logger.debug(f"No action to redo.")
            return

        next_state = self.stack[self.current_state_index + 1]["state"]
        next_action = self.stack[self.current_state_index + 1]["action"]

        logger.debug(f"Redoing {next_action}...")

        events.post(Event.REQUEST_RESTORE_APP_STATE, next_state)

        logger.debug(f"Redone {next_action}.")

        self.current_state_index += 1

    def discard_undone(self):
        """Discard, if necessary, any states in front of self.current_state_index, resets self.current_state_index and self.saved_current"""
        if self.current_state_index != -1:
            self.stack = self.stack[: self.current_state_index + 1]
            self.current_state_index = -1

    def clear(self):
        self.stack = []
        self.current_state_index = -1
