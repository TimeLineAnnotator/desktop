from typing import TypedDict, Optional

from tilia.requests import Post, listen, serve, Get
from tilia.utils import get_tilia_class_string
from tilia.timelines.timeline_kinds import TimelineKind


class ClipboardContents(TypedDict):
    components: dict[str, dict]
    timeline_kind: Optional[TimelineKind]


class Clipboard:
    def __init__(self) -> None:
        listen(
            self, Post.TIMELINE_ELEMENT_COPY_DONE, self.on_timeline_element_copy_done
        )
        serve(self, Get.CLIPBOARD_CONTENTS, self.get_contents)
        self._contents: ClipboardContents = {"components": {}, "timeline_kind": None}

    def __str__(self):
        return get_tilia_class_string(self)

    def get_contents(self) -> ClipboardContents:
        return self._contents

    def on_timeline_element_copy_done(self, contents):
        self._contents = contents
