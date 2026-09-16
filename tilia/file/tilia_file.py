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
    # tls not recognised in this version; stored so they can be saved back out without loss.
    unknown_timelines: dict = field(default_factory=dict)
    # tls not recognised in this version; stored temporarily so the app reconises the need to prompt to save the discard.
    deleted_timelines: dict = field(default_factory=dict)


def validate_tla_data(data: dict) -> tuple[bool, str]:
    for key in [
        "file_path",
        "media_path",
        "media_metadata",
        "timelines",
        "app_name",
        "version",
    ]:
        if key not in data:
            return False, f"Missing field: {key}"

    if not isinstance(data["timelines"], dict):
        return False, "'timelines' must be a mapping of timeline id to timeline data."

    for tl_id, timeline in data["timelines"].items():
        if not isinstance(timeline, dict):
            return (
                False,
                f"Timeline '{tl_id}' data must be a mapping, got {type(timeline).__name__}.",
            )

    return True, ""
