from collections import OrderedDict

from tilia import settings


class MediaMetadata(OrderedDict):
    REQUIRED_FIELDS = {"title": "Untitled", "notes": ""}

    def __init__(self, init_default_fields=True):
        super().__init__()
        for field, value in self.REQUIRED_FIELDS.items():
            self[field] = value

        # should not be initialized if setting media metadata directly
        if init_default_fields:
            for field in settings.get("media_metadata", "default_fields"):
                self[field] = ""

    @classmethod
    def from_dict(cls, data: dict):
        metadata = cls(init_default_fields=False)
        metadata.update(data)
        return metadata
