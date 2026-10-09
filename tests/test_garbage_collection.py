import inspect
import threading
import weakref

from tests import garbage_collection


class Cycle:
    def __init__(self):
        self.cycle = self


def leave_garbage(collected_on: list):
    weakref.finalize(
        Cycle(), lambda: collected_on.append(threading.current_thread().name)
    )


def allocate():
    # Far more objects than it takes to set off an automatic collection.
    return [[] for _ in range(100_000)]


class TestGarbageCollection:
    """Python collects garbage on its own once enough objects have been
    allocated, on whatever thread allocated them. Doing that on an xdist
    worker's own thread, or on the main thread in the middle of a Qt call,
    destroys Qt objects left over from earlier tests while Qt is still using
    them, and the worker segfaults.
    """

    def test_garbage_is_not_collected_while_a_test_runs(self):
        collected_on = []
        leave_garbage(collected_on)

        allocate()

        assert collected_on == []

    def test_garbage_is_not_collected_on_other_threads(self):
        collected_on = []
        leave_garbage(collected_on)

        thread = threading.Thread(target=allocate)
        thread.start()
        thread.join()

        assert collected_on == []

    def test_garbage_is_collected_on_the_main_thread_after_each_test(self, pytester):
        pytester.makeconftest(inspect.getsource(garbage_collection))
        pytester.makepyfile(
            """
            import threading
            import weakref

            collected_on = []


            class Cycle:
                def __init__(self):
                    self.cycle = self


            def test_leave_garbage():
                weakref.finalize(
                    Cycle(), lambda: collected_on.append(threading.current_thread().name)
                )


            def test_garbage_was_collected_on_the_main_thread():
                assert collected_on == ["MainThread"]
            """
        )

        result = pytester.runpytest_subprocess("-p", "no:cacheprovider")

        result.assert_outcomes(passed=2)
