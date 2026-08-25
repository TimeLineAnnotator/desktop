from tests.utils import wait_until
from tilia.ui.background_task import run_in_background


class TestRunInBackground:
    def test_on_done_receives_result(self, qapplication):
        result = {}

        run_in_background(
            lambda: 1 + 1,
            on_done=lambda value: result.setdefault("value", value),
        )

        wait_until(lambda: "value" in result)
        assert result["value"] == 2

    def test_on_error_receives_exception(self, qapplication):
        result = {}

        def _raise():
            raise ValueError("boom")

        run_in_background(
            _raise,
            on_error=lambda exc: result.setdefault("error", exc),
        )

        wait_until(lambda: "error" in result)
        assert isinstance(result["error"], ValueError)
        assert str(result["error"]) == "boom"

    def test_fn_runs_off_the_gui_thread(self, qapplication):
        import threading

        result = {}
        gui_thread = threading.current_thread()

        run_in_background(
            lambda: threading.current_thread(),
            on_done=lambda value: result.setdefault("worker_thread", value),
        )

        wait_until(lambda: "worker_thread" in result)
        assert result["worker_thread"] is not gui_thread

    def test_on_done_callback_runs_on_the_gui_thread(self, qapplication):
        import threading

        result = {}
        gui_thread = threading.current_thread()

        run_in_background(
            lambda: None,
            on_done=lambda _: result.setdefault(
                "callback_thread", threading.current_thread()
            ),
        )

        wait_until(lambda: "callback_thread" in result)
        assert result["callback_thread"] is gui_thread
