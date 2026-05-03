from typing import Optional, TypedDict

from tilia.requests import Get, Post, listen, serve
from tilia.timelines.base.timeline import Timeline
from tilia.utils import get_tilia_class_string


class ClipboardContents(TypedDict):
    components: dict[str, dict]
    timeline_type: Optional[type(Timeline)]


class Clipboard:
    def __init__(self) -> None:
        self._setup_requests()
        self._contents: ClipboardContents = {"components": {}, "timeline_type": None}

    def __str__(self):
        return get_tilia_class_string(self)

    def _setup_requests(self):
        LISTENS = {
            (Post.TIMELINE_ELEMENT_COPY_DONE, self.on_timeline_element_copy_done)
        }

        SERVES = {(Get.CLIPBOARD_CONTENTS, self.get_contents)}

        for post, callback in LISTENS:
            listen(self, post, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def get_contents(self) -> ClipboardContents:
        return self._contents

    def on_timeline_element_copy_done(self, contents):
        self._contents = contents
