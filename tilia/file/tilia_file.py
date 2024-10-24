from dataclasses import dataclass, field

import tilia.constants
from tilia.file.media_metadata import MediaMetadata


@dataclass
class TiliaFile:
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = field(default_factory=MediaMetadata)
    timelines: dict = field(default_factory=lambda: {})
    timelines_hash: str = ""
    app_name: str = tilia.constants.APP_NAME
    version: str = tilia.constants.VERSION


def validate_tla_data(data: dict) -> tuple[bool, str]:
    for key in ['file_path', 'media_path', 'media_metadata', 'timelines', 'app_name', 'version']:
        if key not in data:
            return False, f"Missing field: {key}"

    return True, ""
