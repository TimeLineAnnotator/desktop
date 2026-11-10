from __future__ import annotations

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
        listen(self, Post.UNDO_MANAGER_SET_IS_RECORDING, self.set_is_recording)

    def update_media_length(self, media_path: str, length: float) -> None:
        """
        Corrects states recorded with this media before its real length was
        known (e.g. a YouTube video's opening state, which holds the length
        stored in the file). Restoring one would otherwise bring back the
        stale length and prompt to scale when the real one is reported again.
        """
        for entry in self.stack:
            state = entry["state"]
            if state["media_path"] == media_path:
                state["media_metadata"]["media length"] = length

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

    def replace_current_state(self, state: dict) -> None:
        """
        Overwrites the current state without adding a step to undo. Like
        recording, it discards undone states, as they don't include the change,
        and does nothing while recording is paused. With no current state, the
        next one to be recorded will include the change.
        """
        if not self.is_recording or not self.stack:
            return

        self.discard_undone()
        self.stack[-1]["state"] = state

    def undo(self):
        if abs(self.current_state_index) == len(self.stack) or not self.stack:
            return

        last_state = self.stack[self.current_state_index - 1]["state"]

        post(Post.APP_STATE_RESTORE, last_state)

        self.current_state_index -= 1

        post(Post.APP_STATE_UNDO_OR_REDO_DONE)

    def redo(self):
        if self.current_state_index == -1:
            return

        next_state = self.stack[self.current_state_index + 1]["state"]

        post(Post.APP_STATE_RESTORE, next_state)

        self.current_state_index += 1
        post(Post.APP_STATE_UNDO_OR_REDO_DONE)

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
