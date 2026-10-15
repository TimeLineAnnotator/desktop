"""TimelineView catches the arrows itself and posts a request that each
timeline kind handles; other tests post those requests directly. These press
the keys."""

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tilia.requests import Post

NONE = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.mark.parametrize(
    "key,modifier,request_",
    [
        (Qt.Key.Key_Left, NONE, Post.TIMELINE_KEY_PRESS_LEFT),
        (Qt.Key.Key_Right, NONE, Post.TIMELINE_KEY_PRESS_RIGHT),
        (Qt.Key.Key_Up, NONE, Post.TIMELINE_KEY_PRESS_UP),
        (Qt.Key.Key_Down, NONE, Post.TIMELINE_KEY_PRESS_DOWN),
        (Qt.Key.Key_Up, CTRL, Post.TIMELINE_KEY_PRESS_CTRL_UP),
        (Qt.Key.Key_Down, CTRL, Post.TIMELINE_KEY_PRESS_CTRL_DOWN),
        # Ctrl with other modifiers still counts as Ctrl.
        (Qt.Key.Key_Up, CTRL | SHIFT, Post.TIMELINE_KEY_PRESS_CTRL_UP),
        # Ctrl only changes the vertical arrows; other modifiers change none.
        (Qt.Key.Key_Left, CTRL, Post.TIMELINE_KEY_PRESS_LEFT),
        (Qt.Key.Key_Right, SHIFT, Post.TIMELINE_KEY_PRESS_RIGHT),
        (Qt.Key.Key_Down, SHIFT, Post.TIMELINE_KEY_PRESS_DOWN),
    ],
)
def test_arrow_posts_its_request(marker_tlui, key, modifier, request_):
    with patch("tilia.ui.timelines.view.post") as post:
        QTest.keyClick(marker_tlui.view, key, modifier)

    assert [call.args for call in post.call_args_list] == [(request_,)]


def test_other_keys_post_nothing(marker_tlui):
    with patch("tilia.ui.timelines.view.post") as post:
        QTest.keyClick(marker_tlui.view, Qt.Key.Key_A)
        QTest.keyClick(marker_tlui.view, Qt.Key.Key_PageUp, CTRL)

    post.assert_not_called()
