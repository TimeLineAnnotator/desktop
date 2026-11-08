import sys

import pytest

from tilia.requests import Post, listen, post, stop_listening_to_all

POST = Post.APP_STATE_RESTORE


@pytest.fixture(autouse=True)
def no_other_listeners(monkeypatch):
    # Only this test's listeners hear the post. The module, not the name:
    # reset() rebinds it.
    module = sys.modules["tilia.requests.post"]
    monkeypatch.setitem(module._posts_to_listeners, POST, {})


class Listener:
    def __init__(self):
        self.calls = 0

    def on_post(self):
        self.calls += 1


class TestPost:
    def test_listener_stopped_during_dispatch_is_not_called(self):
        stopped = Listener()

        def stop_the_other():
            stop_listening_to_all(stopped)

        stopper = Listener()
        listen(stopper, POST, stop_the_other)
        listen(stopped, POST, stopped.on_post)
        try:
            post(POST)
        finally:
            stop_listening_to_all(stopper)
            stop_listening_to_all(stopped)

        assert stopped.calls == 0

    def test_listener_added_during_dispatch_waits_for_next_post(self):
        added = Listener()

        def add_another():
            listen(added, POST, added.on_post)

        adder = Listener()
        listen(adder, POST, add_another)
        try:
            post(POST)
            assert added.calls == 0
            post(POST)
            assert added.calls == 1
        finally:
            stop_listening_to_all(adder)
            stop_listening_to_all(added)
