from collections import OrderedDict

from tilia import settings


class MediaMetadata(OrderedDict):
    DEFAULT_TITLE = "Untitled"
    REQUIRED_FIELDS = ["title"]

    def __init__(self):
        super().__init__()
        for field in self.REQUIRED_FIELDS + settings.get(
            "media_metadata", "default_fields"
        ):
            self[field] = ""

        self["title"] = self.DEFAULT_TITLE
