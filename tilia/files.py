"""
Contains classes that relate to file and state management:
    - AutoSaver (not reimplemented yet);
    - UndoRedoStack and UndoRedoManager (not reimplemented yet);
    - MediaMetadata;
    - TiliaFile (centralizes informations that pertain to the .tla file).

"""
import logging
import os
import time
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from threading import Thread

from tilia import globals_
from tilia.misc_enums import SingleOrMultiple

logger = logging.getLogger(__name__)


class AutoSaver:
    MAX_SAVED_FILES = 500
    SAVE_INTERVAL = 300
    AUTOSAVE_DIR = os.path.join(os.path.dirname(__file__), "../autosaves")

    def __init__(self):
        self.last_autosave_dict = dict()
        self.exception_list = []
        self._thread = Thread(target=self._auto_save_loop, args=(self.exception_list,))
        self._thread.start()

    def _auto_save_loop(self, exception_list: list) -> None:
        while True:
            try:
                time.sleep(self.SAVE_INTERVAL)
                if self.needs_auto_save():
                    self.make_room_for_new_autosave()
                    path = self.get_current_autosave_path()
                    do_file_save(path, auto_save=True)
            except Exception as excp:
                exception_list.append(excp)
                self._raise_save_loop_exception(excp)

    @staticmethod
    def _raise_save_loop_exception(excp: Exception):
        raise excp

    def needs_auto_save(self):
        if not globals_.MODIFIED:
            return False

        if (autosave_dict := create_save_dict()) != self.last_autosave_dict:
            self.last_autosave_dict = autosave_dict
            return True
        else:
            return False

    @staticmethod
    def get_file_name():
        if globals_.METADATA.title:
            title = globals_.METADATA.title + f"{globals_.FILE_EXTENSION}"
        else:
            title = f"Untitled - {globals_.FILE_EXTENSION}"
        date = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"{date}_{title}"

    def get_current_autosave_path(self):
        return os.path.join(self.AUTOSAVE_DIR, self.get_file_name())

    def make_room_for_new_autosave(self) -> None:
        if (
            remaining_autosaves := len(self.get_autosaves_paths())
            - self.MAX_SAVED_FILES
        ) >= 0:
            self.delete_older_autosaves(remaining_autosaves + 1)

    def get_autosaves_paths(self) -> list[str]:
        return [
            os.path.join(self.AUTOSAVE_DIR, file)
            for file in os.listdir(self.AUTOSAVE_DIR)
        ]

    def delete_older_autosaves(self, amount: int):
        paths_by_creation_date = sorted(
            self.get_autosaves_paths(),
            key=lambda x: os.path.getctime(x),
        )
        for path in paths_by_creation_date[:amount]:
            os.remove(path)


@dataclass
class MediaMetadata:
    title: str = "Untitled"
    composer: str = ""
    tonality: str = ""
    time_signature: str = ""
    performer: str = ""
    performance_year: str = ""
    arranger: str = ""
    composition_year: str = ""
    recording_year: str = ""
    form: str = ""
    instrumentation: str = ""
    genre: str = ""
    lyrics: str = ""
    audio_length: str = ""
    notes: str = ""

    def clear(self):
        for attr in self.__dict__:
            setattr(self, attr, "")


@dataclass
class TiliaFile:
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = None
    timelines: dict = None
    app_name: str = globals_.APP_NAME
    version: str = globals_.VERSION


class UndoRedoStack(ABC):
    """Stack to store application states"""

    def __init__(self, obj_to_save):
        super().__init__()
        self.stack = []
        self.max_size = 10
        self.pos = -1
        self.saved_current = False
        self.last_action = "file_load"
        self.last_obj = None
        self.obj_to_save = obj_to_save
        # self.manager = globals_.TIMELINE_STATE_STACK_MANAGER

    def record(self, action_id, custom_state=None, no_repeat=False, last_obj=None):
        """Records current state, if necessary"""

        # discard undone states, if any
        self.discard_undone()

        if no_repeat:
            # check if last_action was the same
            if self.last_action == action_id and last_obj == self.last_obj:
                return

        logger.debug(f"Recording {action_id} on state stack")
        # record current state, if necessary
        if not self.saved_current:
            if custom_state:
                self.stack.append((custom_state, self.last_action))
            else:
                self.stack.append((self.obj_to_save.to_dict(), self.last_action))

        # update last action
        self.last_action = action_id
        if last_obj:
            self.last_obj = last_obj

        # changes will be made after record was called in the beginning of function
        self.saved_current = False

        self.update_modified()

        # # notify manager
        # self.manager.notify(self, action_id)

    def undo(self):
        """Undoes last action"""
        if self.last_action != "file_load":
            logger.debug(f"Undoing {self.last_action}")
            self.obj_to_save.from_dict(self.get_previous())

    def redo(self):
        """Redoes next action on stack"""
        logger.debug(f"Redoing action")
        self.obj_to_save.from_dict(self.get_next())

    def discard_undone(self):
        """Discard, if necessary, any states in front of self.pos, resets self.pos and self.saved_current"""
        if self.pos != -1:
            self.stack = self.stack[: self.pos + 1]
            self.saved_current = True
            self.pos = -1
            # self.manager.discard_undone()

    def get_previous(self):
        """Clears APP object and returns state before self.pos"""
        if not self.saved_current:
            self.record(self.last_action)
            self.saved_current = True
        self.clear_action()
        # globals_.APP.clear(player=False)
        self.update_pos(-1)
        prev = self.stack[self.pos][0]

        # update globals_.MODIFIED
        self.update_modified()

        return prev

    def get_next(self):
        """Clears APP object and returns state after self.pos"""
        if not self.saved_current:
            self.record(self.last_action)
            self.saved_current = True
        self.clear_action()
        # globals_.APP.clear(player=False)
        self.update_pos(1)
        next_state = self.stack[self.pos][0]

        # update globals_.MODIFIED
        self.update_modified()

        return next_state

    def update_pos(self, value):
        """Updates current position"""
        # updates if change will keep position inside list range, else does nothing
        if -1 >= self.pos + value >= len(self) * -1:
            self.pos += value

    def update_modified(self):
        """Update globals_.MODIFIED status"""

        if abs(self.pos) == len(self) and not globals_.NEW_FILE:
            globals_.MODIFIED = False
        if not self.saved_current:
            globals_.MODIFIED = True

    def clear_action(self):
        """Prepares obj_to_save for loading previous state"""
        self.obj_to_save.clear()

    def __len__(self):
        return len(self.stack)

    def __repr__(self):
        return f"{self.__class__.__name__}, {len(self)} state(s), last action={self.stack[-1][1][1]}"


class UndoRedoManager:
    def __init__(self):
        self.stacks = []
        self.actions: list[tuple[UndoRedoStack | None, str]] = [(None, "file_load")]
        self.pos = -1

    def notify(self, notifier: UndoRedoStack, action_id: str) -> None:
        """Registers which state stack has made the notified action"""
        self.actions.append((notifier, action_id))

    def undo(self):
        """Redirects the undo request to stack that recorded the previous action"""
        if self.actions[self.pos][1] != "file_load":
            self.actions[self.pos][0].undo()
            self.pos -= 1

        else:
            logger.info("No actions to undo.")

    def discard_undone(self):
        """Removes actions undone previously"""

        self.actions = self.actions[: self.pos + 1]
        self.pos = -1

    def redo(self):
        """Redirects the redo request to stack that recorded the following action"""
        if self.pos != -1:
            self.actions[self.pos + 1][0].redo()
            self.pos += 1
        else:
            logger.info("No actions to redo.")
