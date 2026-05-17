import pytest

from tilia.requests import LongOperation, Post, post


@pytest.fixture(autouse=True)
def drain_stack(qtui):
    yield
    toolbar = qtui._long_op_toolbar
    while toolbar._stack:
        post(Post.LONG_OPERATION, LongOperation.DONE)


class TestLongOperationToolbar:
    def test_toolbar_hidden_initially(self, qtui):
        assert qtui._long_op_toolbar.isHidden()

    def test_toolbar_shows_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert not qtui._long_op_toolbar.isHidden()

    def test_toolbar_hides_after_done(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert qtui._long_op_toolbar.isHidden()

    def test_label_text_set_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Loading file")
        assert qtui._long_op_toolbar._label.text() == "Loading file"

    def test_bar_indeterminate_on_started(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        assert qtui._long_op_toolbar._bar.maximum() == 0

    def test_bar_updates_on_progress(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        post(Post.LONG_OPERATION, LongOperation.PROGRESS, 5, 10)
        assert toolbar._bar.maximum() == 10
        assert toolbar._bar.value() == 5

    def test_nested_toolbar_stays_visible_after_inner_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert not toolbar.isHidden()

    def test_nested_toolbar_hides_after_outer_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert toolbar.isHidden()

    def test_nested_restores_outer_label_after_inner_done(self, qtui):
        toolbar = qtui._long_op_toolbar
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Outer")
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Inner")
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert toolbar._label.text() == "Outer"

    def test_done_without_started_is_safe(self, qtui):
        post(Post.LONG_OPERATION, LongOperation.DONE)
        assert qtui._long_op_toolbar.isHidden()
