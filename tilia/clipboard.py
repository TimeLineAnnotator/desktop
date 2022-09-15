"""
Defines the Clipboard object, that holds the
data copied by the user.
"""

from tilia.events import Subscriber, EventName


class Clipboard(Subscriber):
    def __init__(self):
        super().__init__(subscriptions=[EventName.TIMELINE_COMPONENT_COPIED])
        self._contents = []

    def get_contents_for_pasting(self):
        return self._contents

    def on_subscribed_event(
        self, event_name: EventName, *args: tuple, **kwargs: dict
    ) -> None:
        if event_name == EventName.TIMELINE_COMPONENT_COPIED:
            self._contents = args[0]
