import logging
import sentry_sdk
from pathlib import Path
from datetime import datetime

import sentry_sdk.integrations
import sentry_sdk.integrations.logging
import sentry_sdk.profiler
import sentry_sdk.session
from tilia import dirs
from tilia.constants import APP_NAME, VERSION
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
        self.setup_console_log()
        self.setup_sentry()

    def _get_console_level(self) -> int:
        return logging.INFO if settings.get("dev", "log_requests") else logging.ERROR

    def setup_console_log(self):
        console_formatter = logging.Formatter("{message}", style="{")
        self.console_handler = logging.StreamHandler()
        self.console_handler.setFormatter(console_formatter)
        self.console_handler.setLevel(self._get_console_level())
        self.addHandler(self.console_handler)

    def setup_sentry(self):
        sentry_sdk.init(
            dsn="https://8234ef0e41b165cff5fe3d096787d928@o4508813009289216.ingest.us.sentry.io/4508837138399232",
            release=f"{APP_NAME}@{VERSION}",
            integrations=[
                sentry_sdk.integrations.logging.LoggingIntegration(
                    level=logging.WARNING,  # Capture level and above as breadcrumbs
                    event_level=logging.CRITICAL,  # Send records as events
                ),
            ],
            send_default_pii=True,
            traces_sample_rate=1.0,
        )
        sentry_sdk.profiler.start_profiler()

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
        sentry_sdk.get_global_scope().add_attachment(
            path=file_handler.baseFilename,
            content_type="text/plain",
            add_to_transactions=True,
        )

    def on_settings_updated(self):
        self.console_handler.setLevel(self._get_console_level())


logger = TiliaLogger()
