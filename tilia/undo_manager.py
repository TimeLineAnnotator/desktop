from __future__ import annotations
import logging

from tilia.requests import Post, listen, post
from tilia.repr import default_str
from tilia.timelines.state_actions import Action

logger = logging.getLogger(__name__)


class UndoManager:
    def __init__(self) -> None:
        listen(self, Post.REQUEST_TO_UNDO, self.undo)
        listen(self, Post.REQUEST_TO_REDO, self.redo)

        self.stack = []
        self.current_state_index = -1
        self.last_repeat_id = None

    def __str__(self):
        return default_str(self)

    def record(
        self,
        state,
        action: Action | str,
        no_repeat=False,
        repeat_identifier="",
    ):
        """
        Records given app 'state' to UndoManager's stack. Should be called by the App
        object. The App call should to be triggered by posting
        Post.REQUEST_RECORD_STATE *after* 'action' has been done.
        """

        # discard undone states, if any
        self.discard_undone()

        logger.debug(f"Recording {action}.")

        if no_repeat and self.last_repeat_id == repeat_identifier:
            logger.debug(
                f"No repeat is on and action is same last ({action},"
                f" {repeat_identifier}). Updating recorded state."
            )
            self.stack[-1]["state"] = state
            return

        self.stack.append({"state": state, "action": action})
        logger.debug("State recorded.")

        if repeat_identifier:
            self.last_repeat_id = repeat_identifier

    def undo(self):
        """Undoes last action"""

        if abs(self.current_state_index) == len(self.stack):
            logger.debug("No actions to undo.")
            return

        last_state = self.stack[self.current_state_index - 1]["state"]
        current_action = self.stack[self.current_state_index]["action"]

        logger.debug(f"Undoing {current_action}...")

        post(Post.REQUEST_RESTORE_APP_STATE, last_state)

        logger.debug(f"Undone {current_action}.")

        self.current_state_index -= 1

    def redo(self):
        """Redoes next action on stack"""
        logger.debug("Redoing action...")

        if self.current_state_index == -1:
            logger.debug("No action to redo.")
            return

        next_state = self.stack[self.current_state_index + 1]["state"]
        next_action = self.stack[self.current_state_index + 1]["action"]

        logger.debug(f"Redoing {next_action}...")

        post(Post.REQUEST_RESTORE_APP_STATE, next_state)

        logger.debug(f"Redone {next_action}.")

        self.current_state_index += 1

    def discard_undone(self):
        """
        Discard, if necessary, any states in front of self.current_state_index,
        resets self.current_state_index and self.saved_current
        """
        if self.current_state_index != -1:
            self.stack = self.stack[: self.current_state_index + 1]
            self.current_state_index = -1

    def clear(self):
        self.stack = []
        self.current_state_index = -1
