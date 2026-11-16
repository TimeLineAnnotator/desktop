"""Restoring a state sets a timeline's attributes again after its components
only when they differ from the state."""

from tilia.requests import Post, listen, stop_listening
from tilia.ui import commands


class _Posts:
    def __init__(self):
        self.attrs = []
        listen(self, Post.TIMELINE_SET_DATA_DONE, self.on_set_data_done)

    def on_set_data_done(self, _id, attr, _value):
        self.attrs.append(attr)

    def stop(self):
        stop_listening(self, Post.TIMELINE_SET_DATA_DONE)


def test_undo_and_redo_adding_a_range_set_no_rows(range_tlui):
    commands.execute("timeline.range.add_range", start=10, end=20)

    posts = _Posts()
    commands.execute("edit.undo")
    commands.execute("edit.redo")
    posts.stop()

    assert len(range_tlui.timeline) == 1
    assert "rows" not in posts.attrs
