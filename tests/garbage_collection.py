"""Collect garbage only between tests, on the main thread.

Python collects garbage on its own whenever enough objects have been
allocated, on whichever thread allocated them. Here, that can be the thread an
xdist worker uses to talk to the controller, or the main thread in the middle
of a Qt call, e.g. in an event filter while Qt deletes gestures. Destroying Qt
objects left over from earlier tests at such a point crashes the worker, and
there are many of them: each test module's window and app, for instance, sit
in reference cycles that only the collector frees. So automatic collection is
turned off, and garbage is collected after each test's teardown instead, when
no Qt code is running.
"""

import gc

import pytest


def pytest_configure(config):
    gc.disable()


def pytest_collection_finish(session):
    # Modules and test items live for the whole session. Freezing them keeps
    # each collection below from walking all of them again.
    gc.collect()
    gc.freeze()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    try:
        return (yield)
    finally:
        gc.collect()
