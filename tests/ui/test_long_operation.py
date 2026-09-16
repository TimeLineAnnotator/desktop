from unittest.mock import patch

import pytest

import tilia.ui.webengine_tracking as webengine_tracking
from tilia.requests import LongOperation, Post, post


@pytest.fixture(autouse=True)
def drain_stack(qtui):
    yield
    toolbar = qtui._long_op_toolbar
    while toolbar._stack:
        post(Post.LONG_OPERATION, LongOperation.DONE)


@pytest.fixture(autouse=True)
def no_webengine(monkeypatch):
    # any_web_engine_view_created() is a sticky, process-global flag; pin it
    # to the common case so these tests don't flake based on test order.
    monkeypatch.setattr(webengine_tracking, "_any_web_engine_view_created", False)


class _FakeElapsedTimer:
    """Deterministic stand-in for QElapsedTimer so throttle tests don't
    depend on real wall-clock timing."""

    def __init__(self):
        self.elapsed_ms = 0

    def start(self):
        self.elapsed_ms = 0

    def restart(self):
        self.elapsed_ms = 0

    def elapsed(self):
        return self.elapsed_ms


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

    def test_progress_throttles_process_events(self, qtui):
        toolbar = qtui._long_op_toolbar
        toolbar._progress_timer = _FakeElapsedTimer()
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        with patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe:
            for i in range(50):
                post(Post.LONG_OPERATION, LongOperation.PROGRESS, i, 50)
            assert mock_pe.call_count == 0
            assert toolbar._bar.value() == 49

    def test_progress_processes_events_after_throttle_elapses(self, qtui):
        toolbar = qtui._long_op_toolbar
        fake_timer = _FakeElapsedTimer()
        toolbar._progress_timer = fake_timer
        post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
        fake_timer.elapsed_ms = 150
        with patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe:
            post(Post.LONG_OPERATION, LongOperation.PROGRESS, 1, 50)
            assert mock_pe.call_count == 1

    def test_started_avoids_process_events_once_webengine_is_used(self, qtui):
        with (
            patch(
                "tilia.ui.long_operation.any_web_engine_view_created",
                return_value=True,
            ),
            patch("tilia.ui.long_operation.QApplication.processEvents") as mock_pe,
            patch(
                "tilia.ui.long_operation.QCoreApplication.sendPostedEvents"
            ) as mock_spe,
        ):
            post(Post.LONG_OPERATION, LongOperation.STARTED, "Op")
            assert mock_pe.call_count == 0
            assert mock_spe.call_count == 1
