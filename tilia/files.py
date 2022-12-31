"""
Contains classes that relate to file and state management:
    - AutoSaver (not reimplemented yet);
    - MediaMetadata;
    - TiliaFile (centralizes informations that pertain to the .tla file).

"""
import logging
from collections import OrderedDict
from dataclasses import dataclass, field

from tilia import globals_, settings

logger = logging.getLogger(__name__)

MANDATORY_METADATA_FIELDS = [
    "title"
]

DEFAULT_METADATA_FIELDS = settings.settings['media_metadata']['default_fields']

DEFAULT_TITLE = "Untitled"


def create_new_media_metadata():

    media_metadata = OrderedDict()
    for field in MANDATORY_METADATA_FIELDS + DEFAULT_METADATA_FIELDS:
        media_metadata[field] = ""

    media_metadata["title"] = DEFAULT_TITLE
    return media_metadata


@dataclass
class TiliaFile:
    file_path: str = ""
    media_path: str = ""
    media_metadata: OrderedDict = field(default_factory=create_new_media_metadata)
    timelines: dict = field(default_factory=lambda: {})
    app_name: str = globals_.APP_NAME
    version: str = globals_.VERSION
