from __future__ import annotations

from typing import Callable

from tilia.requests import Post


class RequestHandler:
    def __init__(self, request_to_callback: dict[Post, Callable]):
        base_request_to_callback = {}
        self.request_to_callback = base_request_to_callback | request_to_callback

    def on_request(self, request, *args, **kwargs):
        return self.request_to_callback[request](*args, **kwargs)


class RequestFailure:
    pass


def fallible(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return RequestFailure() if result is False else result
    return wrapper

