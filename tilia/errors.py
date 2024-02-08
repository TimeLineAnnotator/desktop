from typing import NamedTuple

from tilia.requests import Post, post


class Error(NamedTuple):
    title: str
    message: str


CREATE_TIMELINE_WITHOUT_MEDIA = Error(
    "Create timeline error", "Can't create timeline with no media loaded."
)
UNSUPPORTED_MEDIA_FORMAT = Error(
    "Media format not supported",
    "Media file of type '.{}' not supported. Try loading a supported file type.",
)
CHANGE_MEDIA_LENGTH_WITH_MEDIA_LOADED = Error(
    "Change media length",
    "Can't change media length when a media file is loaded.",
)
MEDIA_NOT_FOUND = Error(
    "Media load error", "No file found at '{}'. Try loading another media file."
)
MEDIA_LOAD_FAILED = Error(
    "Media load failed", "Could not load media at '{}'. Try loading another media file"
)


def display(error: Error, *args):
    post(Post.DISPLAY_ERROR, error.title, error.message.format(*args))
