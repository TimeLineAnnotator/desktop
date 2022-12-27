import os
from datetime import datetime


class AutoSaver:
    MAX_SAVED_FILES = 500
    SAVE_INTERVAL = 300
    AUTOSAVE_DIR = os.path.join(os.path.dirname(__file__), "autosaves")

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
        if not app_globals.MODIFIED:
            return False

        if (autosave_dict := file.create_save_dict()) != self.last_autosave_dict:
            self.last_autosave_dict = autosave_dict
            return True
        else:
            return False

    @staticmethod
    def get_file_name():
        if app_globals.METADATA.title:
            title = app_globals.METADATA.title + f"{app_globals.FILE_EXTENSION}"
        else:
            title = f"Untitled - {app_globals.FILE_EXTENSION}"
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
