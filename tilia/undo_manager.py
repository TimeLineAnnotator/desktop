from __future__ import annotations
from tilia.events import Event, subscribe

import logging

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tilia.timelines.common import Timeline

from tilia.timelines.state_actions import StateAction

logger = logging.getLogger(__name__)


class CanRestoreState(Protocol):
    def restore_state(self, state: dict, action: StateAction) -> None:
        ...

    def get_state(self) -> dict:
        ...


class UndoManager:

    def __init__(self) -> None:
        subscribe(self, Event.RECORD_STATE, self.on_record_state)
        subscribe(self, Event.REQUEST_TO_UNDO, self.undo)
        subscribe(self, Event.REQUEST_TO_REDO, self.redo)

        self.stack = []
        self.max_size = 10
        self.pos = -1
        self.saved_current = False
        self.last_action = StateAction.FILE_LOAD
        self.last_action_no_repeat = False
        self.last_action_repeat_id = ''
        self.last_timeline = None
        self.last_repeat_id = ''
        # self.obj_to_save = obj_to_save # __init__ had an object to save parameter

    def on_record_state(
        self,
        recording_obj: CanRestoreState | None,
        action: StateAction,
        custom_state=None,
        no_repeat=False,
        repeat_identifier='',
    ):

        # discard undone states, if any
        self.discard_undone()

        logger.debug(f"Recording {action} by {recording_obj}.")

        if all(
            [
                no_repeat,
                self.last_action == action,
                self.last_repeat_id == repeat_identifier,
            ]
        ):
            logger.debug(f"No repeat is on and action is same last ({action}, {repeat_identifier}). Won't record.")
            return



        # record current state, if necessary
        if not self.saved_current:
            logger.debug(
                f"Current state is not saved. Appending current state to stack..."
            )
            if custom_state:
                self.stack.append((custom_state, self.last_action))
            else:
                self.stack.append(
                    (recording_obj, recording_obj.get_state(), self.last_action)
                )
            logger.debug(f"State appended.")

        # update last action
        self.last_action = action
        self.last_timeline = recording_obj

        if repeat_identifier:
            self.last_repeat_id = repeat_identifier

        # changes will be made after record was called in the beginning of function
        self.saved_current = False


    def undo(self):
        """Undoes last action"""
        if self.last_action != StateAction.FILE_LOAD:
            logger.debug(f"Undoing {self.last_action}...")
            prev_state = self.get_previous()

            logging.disable(logging.CRITICAL)
            prev_state[0].restore_state(prev_state[1], prev_state[2])
            logging.disable(logging.NOTSET)

            logger.debug(f"Undone {self.last_action}.")

    def redo(self):
        """Redoes next action on stack"""
        next_state = self.get_next()
        logger.debug(f"Redoing action {next_state[2]}...")

        logging.disable(logging.CRITICAL)
        next_state[0].restore_state(next_state[1], next_state[2])
        logging.disable(logging.NOTSET)

        logger.debug(f"Redone action {next_state[2]}.")

    def discard_undone(self):
        """Discard, if necessary, any states in front of self.pos, resets self.pos and self.saved_current"""
        if self.pos != -1:
            self.stack = self.stack[: self.pos + 1]
            self.saved_current = True
            self.pos = -1
            # self.manager.discard_undone()

    def get_previous(self):
        """Clears APP object and returns state before self.pos"""
        self.save_current_if_necessary()
        self.update_pos(-1)
        prev = self.stack[self.pos]

        return prev

    def get_next(self):
        """Clears APP object and returns state after self.pos"""
        self.save_current_if_necessary()
        self.update_pos(1)
        next_state = self.stack[self.pos]

        return next_state

    def save_current_if_necessary(self) -> None:
        if not self.saved_current:
            self.on_record_state(self.last_timeline, self.last_action)
            self.saved_current = True

    def update_pos(self, value: int) -> None:
        """Updates current position"""
        # updates if change will keep position inside list range, else does nothing
        if -1 >= self.pos + value >= len(self) * -1:
            self.pos += value

    def __len__(self) -> int:
        return len(self.stack)
