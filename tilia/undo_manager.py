from __future__ import annotations

import tilia.requests.post
from tilia.requests import Post, listen, post
from tilia.utils import get_tilia_class_string


class UndoManager:
    def __init__(self) -> None:
        self._setup_requests()
        self.stack = []
        self.current_state_index = -1
        self.last_repeat_id = None
        self.is_recording = True

    def __str__(self):
        return get_tilia_class_string(self)
    
    def _setup_requests(self):
        LISTENS = {
            (Post.EDIT_UNDO, self.undo),
            (Post.EDIT_REDO, self.redo),
            (Post.UNDO_MANAGER_SET_IS_RECORDING, self.set_is_recording)
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

    @property
    def is_cleared(self):
        return len(self.stack) == 1

    def set_is_recording(self, value: bool):
        if not isinstance(value, bool):
            raise ValueError("UndoManager.is_recording must be a boolean")
        self.is_recording = value

    def record(
        self,
        state,
        action: str,
        no_repeat=False,
        repeat_identifier="",
    ):
        """
        Records given app 'state' to UndoManager's stack. Should be called by the App
        object. The App call should to be triggered by posting
        Post.REQUEST_RECORD_STATE *after* 'action' has been done.
        """
        if not self.is_recording:
            return

        # discard undone states, if any
        self.discard_undone()

        if no_repeat and self.last_repeat_id == repeat_identifier:
            # No repeat is on and action is same as last. Replace recorded state."
            self.stack[-1]["state"] = state
            return

        self.stack.append({"state": state, "action": action})

        if repeat_identifier:
            self.last_repeat_id = repeat_identifier

    def undo(self):
        if abs(self.current_state_index) == len(self.stack) or not self.stack:
            return

        last_state = self.stack[self.current_state_index - 1]["state"]

        post(Post.APP_STATE_RESTORE, last_state)

        self.current_state_index -= 1

    def redo(self):
        if self.current_state_index == -1:
            return

        next_state = self.stack[self.current_state_index + 1]["state"]

        post(Post.APP_STATE_RESTORE, next_state)

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


class PauseUndoManager:
    def __enter__(self):
        post(Post.UNDO_MANAGER_SET_IS_RECORDING, False)

    def __exit__(self, exc_type, exc_val, exc_tb):
        post(Post.UNDO_MANAGER_SET_IS_RECORDING, True)