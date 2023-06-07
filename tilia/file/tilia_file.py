from dataclasses import dataclass, field

from tilia import globals_
from tilia.file.media_metadata import MediaMetadata


@dataclass
class TiliaFile:
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = field(default_factory=MediaMetadata)
    timelines: dict = field(default_factory=lambda: {})
    app_name: str = globals_.APP_NAME
    version: str = globals_.VERSION
