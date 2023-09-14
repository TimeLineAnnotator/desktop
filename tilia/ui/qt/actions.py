from dataclasses import dataclass
from enum import Enum, auto

from tilia.requests import Post


class Actions(Enum):
    BEAT_ADD = auto()
    BEAT_DELETE = auto()


@dataclass
class ActionParams:
    request: Post
    text: str
    icon: str
    shortcut: str


action_to_params = {
    Actions.BEAT_ADD: ActionParams(Post.BEAT_TOOLBAR_BUTTON_ADD, "Add beat at current position", 'add_beat30', 'b'),
    Actions.BEAT_DELETE: ActionParams(Post.BEAT_TOOLBAR_BUTTON_DELETE, "Delete selected beat", 'delete_beat30', 'Delete')
}

action_to_qaction = {}  # will be initialized elsewhere

