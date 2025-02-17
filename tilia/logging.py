import logging
from pathlib import Path
from datetime import datetime
from tilia import dirs
from tilia.settings import settings


class TiliaLogger(logging.Logger):
    """
    Logs to file and console.
    settings.dev.log_requests sets console log level to INFO when True, WARNING when False.
    (Only logs of level or higher will be logged by the handler.)

    Log level   |Message type
    ------------|------------
    DEBUG       |file dumps, autosave file name
    INFO        |tilia.posts
    WARNING     |tilia.errors
    ERROR       |Qt log messages
    CRITICAL    |Crash messages
    """

    def __init__(self):
        super().__init__(__name__)
        self.setLevel(logging.DEBUG)

        console_formatter = logging.Formatter("{message}", style="{")
        self.console_handler = logging.StreamHandler()
        self.console_handler.setFormatter(console_formatter)
        self.console_handler.setLevel(self._get_console_level())
        self.addHandler(self.console_handler)

    def _get_console_level(self) -> int:
        return logging.INFO if settings.get("dev", "log_requests") else logging.ERROR

    def setup_file_log(self):
        def make_room_for_new_log():
            log_paths = [
                str(Path(dirs.logs_path, file))
                for file in dirs.os.listdir(dirs.logs_path)
            ]
            if (
                delete_logs := len(log_paths) - settings.get("dev", "max_stored_logs")
            ) >= 0:
                log_paths = sorted(log_paths, key=lambda x: dirs.os.path.getctime(x))
                for path in log_paths[:delete_logs]:
                    dirs.os.remove(path)

        make_room_for_new_log()
        file_formatter = logging.Formatter("{asctime} {levelname} {message}", style="{")
        log_fname = Path(dirs.logs_path, "{:%Y%m%d%H%M%S}.log".format(datetime.now()))
        file_handler = logging.FileHandler(log_fname, mode="a", encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        self.addHandler(file_handler)

    def on_settings_updated(self):
        self.console_handler.setLevel(self._get_console_level())


logger = TiliaLogger()
