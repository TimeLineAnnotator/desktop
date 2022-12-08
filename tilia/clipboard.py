"""
Defines the Clipboard object, that holds the
data copied by the user.
"""

from tilia import events
from tilia.events import Event


class Clipboard:
    def __init__(self) -> None:
        events.subscribe(self, Event.TIMELINE_COMPONENT_COPIED, self.on_timeline_component_copied)
        self._contents = []

    def get_contents_for_pasting(self):
        return self._contents

    def on_timeline_component_copied(self, contents):
        self._contents = contents
