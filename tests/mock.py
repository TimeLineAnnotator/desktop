from typing import Any, Sequence
from unittest.mock import patch, Mock

from tilia.requests import Get, Post, serve, server, stop_serving
from tilia.requests import get as get_original
from tilia.requests import post as post_original


class PatchGetMultiple:
    def __init__(self, module: str, requests_to_return_values: dict[Get, Any]):
        self.module = module
        self.requests_to_return_values = requests_to_return_values
        self.mock_request = None
        self.mock = None

    def __enter__(self):
        self.patcher = patch(self.module + ".get", self.request_mock)
        self.patcher.start()
        self.mock = Mock()
        return self.mock

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.patcher.stop()

    def request_mock(self, request: Get, *args, **kwargs):
        if request in self.requests_to_return_values:
            self.mock(request, *args, **kwargs)
            return self.requests_to_return_values[request]
        else:
            return get_original(request, *args, **kwargs)


class Serve:
    def __init__(self, request: Get, return_value: Any):
        self.request = request
        self.return_value = return_value
        self.original_server, self.original_callback = server(self.request)
        self.called = False

    def __enter__(self):
        if self.original_server:
            stop_serving(self.original_server, self.request)
        serve(self, self.request, self._callback)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        stop_serving(self, self.request)
        if self.original_server:
            serve(self.original_server, self.request, self.original_callback)

    def _callback(self, *_, **__):
        self.called = True
        return self.return_value



class ServeSequence:
    def __init__(self, request: Get, return_values: Sequence[Any]):
        self.request = request
        self.return_values = return_values
        self.return_count = 0
        self.original_server, self.original_callback = server(self.request)

    def __enter__(self):
        if self.original_server:
            stop_serving(self.original_server, self.request)
        serve(self, self.request, self._callback)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_server:
            stop_serving(self, self.request)
        serve(self.original_server, self.request, self.original_callback)

    def _callback(self, *_, **__):
        try:
            return_value = self.return_values[self.return_count]
        except IndexError as exc:
            raise IndexError('Not enough return values to serve')

        self.return_count += 1
        return return_value


class PatchGet:
    def __init__(self, module: str, request_to_mock: Get, return_value: Any):
        self.module = module
        self.request_to_mock = request_to_mock
        self.return_value = return_value
        self.mock_request = None
        self.mock = None

    def __enter__(self):
        self.patcher = patch(self.module + ".get", self.request_mock)
        self.patcher.start()
        self.mock = Mock()
        return self.mock

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.patcher.stop()

    def request_mock(self, request: Get, *args, **kwargs):
        if request == self.request_to_mock:
            self.mock(request, *args, **kwargs)
            return self.return_value
        else:
            return get_original(request, *args, **kwargs)


class PatchPost:
    def __init__(self, module: str, request_to_mock: Post):
        self.module = module
        self.request_to_mock = request_to_mock
        self.mock_request = None
        self.mock = None

    def __enter__(self):
        self.patcher = patch(self.module + ".post", self.request_mock)
        self.patcher.start()
        self.mock = Mock()
        return self.mock

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.patcher.stop()

    def request_mock(self, request: Post, *args, **kwargs):
        if request == self.request_to_mock:
            self.mock(request, *args, **kwargs)
        else:
            post_original(request, *args, **kwargs)
