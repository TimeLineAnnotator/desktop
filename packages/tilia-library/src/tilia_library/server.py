"""The library's web server and its router.

Standard library only. Every request goes through one dispatch that checks
access (see ``security``), then routes, then answers.
"""

from __future__ import annotations

import email.message
import importlib.metadata
import json
import logging
import re
import secrets
import socket
import socketserver
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote

from tilia_library import security
from tilia_library.backend import Backend, NotAvailable

logger = logging.getLogger(__name__)

PROTOCOL = 1  # the version of the library's HTTP API (the core will own this later)
MAX_BODY = 16 * 1024 * 1024

Handler = Callable[["Request"], "Response"]

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
}

JSON_TYPE = "application/json; charset=utf-8"

FORBIDDEN_PAGE = (
    "<!doctype html>\n"
    '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    "<title>TiLiA Library</title>\n</head>\n<body>\n"
    "<h1>TiLiA Library</h1>\n"
    "<p>This address can't be opened directly. TiLiA Library is opened with "
    "the command <code>tilia library</code>, which starts it and opens your "
    "browser at the right address.</p>\n"
    "</body>\n</html>\n"
)

ACCESS_VALUES = ("any", "bearer")
METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


class ApiError(Exception):
    """Raised by a handler to answer with a given status and a JSON error."""

    def __init__(self, status: int, message: str, detail: str | None = None) -> None:
        super().__init__(status, message, detail)
        self.status = status
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class Route:
    """One method and path pattern, with its handler and who may call it."""

    method: str
    pattern: str
    handler: Handler
    access: str = "any"  # "any": cookie or bearer; "bearer": bearer only


@dataclass
class Request:
    """What a handler gets to know about a request."""

    method: str
    path: str
    query: dict[str, list[str]]
    headers: email.message.Message
    params: dict[str, str]
    body: bytes
    server: LibraryServer
    credential: str  # "cookie" or "bearer"

    def json(self) -> Any:
        """The body parsed as JSON; answers 400 when it isn't JSON."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError as error:
            raise ApiError(400, "bad JSON") from error


@dataclass
class Response:
    """What a handler answers."""

    status: int = 200
    body: bytes = b""
    content_type: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def json_response(data: object, status: int = 200) -> Response:
    """Answer with ``data`` as UTF-8 JSON."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(status, body, JSON_TYPE)


def error_response(
    status: int, message: str, detail: str | None = None, **extra: object
) -> Response:
    """Answer with a JSON error: ``{"error": ..., "detail"?: ..., **extra}``."""
    data: dict[str, object] = {"error": message}
    if detail is not None:
        data["detail"] = detail
    data.update(extra)
    return json_response(data, status)


# (kind, value): kind is "lit", "param" or "path"
_Segment = tuple[str, str]
_PARAM = re.compile(r"^\{(\w+)(:path)?\}$")


def _compile(pattern: str) -> list[_Segment]:
    if not pattern.startswith("/"):
        raise ValueError(f"pattern must start with '/': {pattern!r}")
    parts = pattern.split("/")[1:]
    compiled: list[_Segment] = []
    for index, part in enumerate(parts):
        found = _PARAM.match(part)
        if found is None:
            if "{" in part or "}" in part:
                raise ValueError(f"bad parameter in pattern: {pattern!r}")
            compiled.append(("lit", part))
        elif found.group(2):
            if index != len(parts) - 1:
                raise ValueError(f"a path parameter must be last: {pattern!r}")
            compiled.append(("path", found.group(1)))
        else:
            compiled.append(("param", found.group(1)))
    return compiled


def _try_match(
    compiled: list[_Segment], segments: list[str]
) -> tuple[dict[str, str], tuple[int, ...]] | None:
    """Params and a specificity score when the segments fit, else None."""
    has_path = bool(compiled) and compiled[-1][0] == "path"
    if has_path:
        if len(segments) < len(compiled):
            return None
    elif len(segments) != len(compiled):
        return None
    params: dict[str, str] = {}
    score: list[int] = []
    for index, (kind, value) in enumerate(compiled):
        if kind == "path":
            params[value] = "/".join(segments[index:])
            score.append(0)
        elif kind == "param":
            if not segments[index]:
                return None
            params[value] = segments[index]
            score.append(0)
        else:
            if segments[index] != value:
                return None
            score.append(1)
    return params, tuple(score)


class Router:
    """Finds the route for a method and a path."""

    def __init__(self) -> None:
        self.routes: list[Route] = []
        self._compiled: list[list[_Segment]] = []

    def add(
        self, method: str, pattern: str, handler: Handler, access: str = "any"
    ) -> Route:
        """Register a route and return it."""
        if access not in ACCESS_VALUES:
            raise ValueError(f"unknown access: {access!r}")
        compiled = _compile(pattern)
        route = Route(method.upper(), pattern, handler, access)
        self.routes.append(route)
        self._compiled.append(compiled)
        return route

    def _candidates(self, path: str) -> list[tuple[Route, dict[str, str], tuple]]:
        if not path.startswith("/"):
            return []
        segments = [unquote(part) for part in path.split("/")[1:]]
        found = []
        for route, compiled in zip(self.routes, self._compiled, strict=True):
            result = _try_match(compiled, segments)
            if result is not None:
                found.append((route, result[0], result[1]))
        return found

    def match(
        self, method: str, path: str
    ) -> tuple[Route | None, dict[str, str], set[str]]:
        """The route for this method and path, its params, and the path's methods."""
        candidates = self._candidates(path)
        methods = {route.method for route, _, _ in candidates}
        if "GET" in methods:
            methods.add("HEAD")
        wanted = "GET" if method == "HEAD" else method
        fitting = [c for c in candidates if c[0].method == wanted]
        if not fitting:
            return None, {}, methods
        route, params, _ = max(fitting, key=lambda c: c[2])
        return route, params, methods

    def path_access(self, path: str) -> str:
        """The access a path needs: the strictest among the routes it matches."""
        accesses = {route.access for route, _, _ in self._candidates(path)}
        return "bearer" if "bearer" in accesses else "any"


def _serve_file(root: Path, relative: str) -> Response:
    """Answer with a file from the web folder, or 404."""
    not_found = ApiError(404, "not found")
    segments = relative.split("/")
    if any(s in ("", ".", "..") for s in segments):
        raise not_found
    if any(c in relative for c in ("\\", "\0", ":")):
        raise not_found
    content_type = CONTENT_TYPES.get(Path(segments[-1]).suffix.lower())
    if content_type is None:
        raise not_found
    try:
        base = root.resolve()
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base) or not candidate.is_file():
            raise not_found
        data = candidate.read_bytes()
    except (OSError, ValueError) as error:
        raise not_found from error
    return Response(200, data, content_type)


def _redact(text: str, token: str) -> str:
    text = re.sub(r"token=[^&\s\"]*", "token=…", text)
    return text.replace(token, "…") if token else text


class _HTTPServer(ThreadingHTTPServer):
    """The standard threading server, bound the way the library needs."""

    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"
    library: LibraryServer

    def handle_error(self, request: object, client_address: object) -> None:
        """Log errors instead of printing them; a client hanging up is routine."""
        error = sys.exc_info()[1]
        if isinstance(error, ConnectionError):
            logger.debug("connection from %s dropped: %s", client_address, error)
        else:
            logger.exception("error while serving %s", client_address)

    def server_bind(self) -> None:
        # On Windows SO_REUSEADDR lets a second server share a taken port; the
        # exclusive option stops that. The base class's server_bind also does
        # a slow reverse lookup of the host name, which we don't need.
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port


class _RequestHandler(BaseHTTPRequestHandler):
    """Sends every method through one dispatch."""

    protocol_version = "HTTP/1.1"
    server: _HTTPServer

    def do_GET(self) -> None:
        self._dispatch()

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_GET

    def log_message(self, format: str, *args: object) -> None:
        """Send request lines to the debug log, never with the token."""
        message = _redact(format % args, self.server.library.token)
        logger.debug("%s - %s", self.address_string(), message)

    def send_error(
        self, code: int, message: str | None = None, explain: str | None = None
    ) -> None:
        """Answer the standard library's own errors as JSON too."""
        self.log_error("code %d, message %s", code, message)
        self.close_connection = True
        self._write(error_response(code, message or "error"), {"Connection": "close"})

    def _write(self, response: Response, extra: dict[str, str] | None = None) -> None:
        head_only = self.command == "HEAD"
        self.send_response(response.status)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if response.content_type:
            self.send_header("Content-Type", response.content_type)
        for name, value in {**response.headers, **(extra or {})}.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if not head_only and response.status >= 200:
            self.wfile.write(response.body)

    def _read_body(self) -> bytes | Response:
        """The request body, or the response that refuses it."""
        if self.headers.get("Transfer-Encoding") is not None:
            return self._refuse(400, "chunked bodies are not accepted")
        raw = self.headers.get("Content-Length")
        if raw is None:
            return b""
        if not raw.strip().isdigit():
            return self._refuse(400, "bad Content-Length")
        length = int(raw)
        if length > MAX_BODY:
            return self._refuse(413, "request body too large")
        body = self.rfile.read(length)
        if len(body) != length:
            return self._refuse(400, "incomplete request body")
        return body

    def _refuse(self, status: int, message: str) -> Response:
        self.close_connection = True
        response = error_response(status, message)
        response.headers["Connection"] = "close"
        return response

    def _forbidden(self, path: str, reason: str) -> Response:
        if path == "/api" or path.startswith("/api/"):
            return error_response(403, "forbidden", reason)
        return Response(403, FORBIDDEN_PAGE.encode("utf-8"), "text/html; charset=utf-8")

    def _dispatch(self) -> None:
        library = self.server.library
        method = self.command
        target = self.path
        if not target.startswith("/"):
            self._write(self._refuse(400, "bad request target"))
            return
        path, _, rest = target.partition("?")
        query_text = rest.partition("#")[0]
        path = path.partition("#")[0]

        body = self._read_body()
        if isinstance(body, Response):
            self._write(body)
            return

        query = parse_qs(query_text, keep_blank_values=True)
        if not security.host_ok(self.headers, library.port):
            self._write(error_response(400, "bad Host header"))
            return

        if method == "GET" and path == "/" and "token" in query:
            self._write(library._enter(query["token"][0]))
            return

        route, params, methods = library.router.match(method, path)
        access = route.access if route else library.router.path_access(path)
        verdict = security.check_request(
            method,
            self.headers,
            port=library.port,
            token=library.token,
            access=access,
        )
        if verdict.status == 403:
            self._write(self._forbidden(path, verdict.reason))
            return
        if verdict.status is not None:
            self._write(error_response(verdict.status, verdict.reason))
            return

        if route is None:
            if methods:
                response = error_response(405, "method not allowed")
                response.headers["Allow"] = ", ".join(sorted(methods))
            else:
                response = error_response(404, "not found")
            self._write(response)
            return

        request = Request(
            method=method,
            path=path,
            query=query,
            headers=self.headers,
            params=params,
            body=body,
            server=library,
            credential=verdict.credential or "bearer",
        )
        self._write(self._call(route, request))

    def _call(self, route: Route, request: Request) -> Response:
        try:
            return route.handler(request)
        except NotAvailable as error:
            return error_response(501, "not available yet", needs=error.needs)
        except ApiError as error:
            return error_response(error.status, error.message, error.detail)
        except Exception:
            logger.exception("handler for %s %s failed", request.method, route.pattern)
            return error_response(500, "internal error")


class LibraryServer:
    """The local web server: binds 127.0.0.1 and answers only its owner."""

    def __init__(
        self,
        backend: Backend,
        *,
        port: int = 0,
        token: str | None = None,
        instance: str | None = None,
        web_root: Path | None = None,
        library_version: str | None = None,
    ) -> None:
        self.backend = backend
        self.token: str = token or security.new_token()
        self.instance: str = instance or secrets.token_hex(8)
        self.web_root: Path = (
            web_root
            if web_root is not None
            else Path(__file__).resolve().parent / "web"
        )
        self.library_version: str = library_version or _installed_version()
        self.router = Router()
        self._lock = threading.Lock()
        self._serving = False
        self._closed = False
        self._thread: threading.Thread | None = None
        self._httpd = _HTTPServer(("127.0.0.1", port), _RequestHandler)
        self._httpd.library = self
        self.port: int = self._httpd.server_address[1]
        self.address: str = f"http://127.0.0.1:{self.port}/"
        self.entry_url: str = f"http://127.0.0.1:{self.port}/?token={self.token}"
        self.router.add("GET", "/", self._index)
        self.router.add("GET", "/web/{path:path}", self._static)
        self.router.add("GET", "/api/ping", self._ping)

    def _enter(self, given: str) -> Response:
        """The browser's entry: trade the token in the address for a cookie."""
        if not security.token_matches(given, self.token):
            return self._entry_refused()
        headers = {
            "Location": "/",
            "Set-Cookie": security.entry_cookie(self.port, self.token),
        }
        return Response(303, b"", None, headers)

    @staticmethod
    def _entry_refused() -> Response:
        return Response(403, FORBIDDEN_PAGE.encode("utf-8"), "text/html; charset=utf-8")

    def _index(self, request: Request) -> Response:
        return _serve_file(self.web_root, "index.html")

    def _static(self, request: Request) -> Response:
        return _serve_file(self.web_root, request.params["path"])

    def _ping(self, request: Request) -> Response:
        return json_response(
            {
                "instance": self.instance,
                "library_version": self.library_version,
                "protocol": PROTOCOL,
            }
        )

    def start(self) -> None:
        """Serve in a daemon thread and return at once."""
        with self._lock:
            if self._closed or self._serving:
                return
            self._serving = True
        self._thread = threading.Thread(
            target=self._run, name="tilia-library-server", daemon=True
        )
        self._thread.start()

    def serve_forever(self) -> None:
        """Serve in the calling thread until ``stop()``."""
        with self._lock:
            if self._closed or self._serving:
                return
            self._serving = True
        self._run()

    def _run(self) -> None:
        try:
            self._httpd.serve_forever(poll_interval=0.05)
        finally:
            with self._lock:
                self._serving = False

    def stop(self) -> None:
        """Stop serving and close the socket. Safe to call again."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            serving = self._serving
        if serving:
            self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> LibraryServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def _installed_version() -> str:
    try:
        return importlib.metadata.version("tilia-library")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"
