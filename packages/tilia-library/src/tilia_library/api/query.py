"""The query panel's routes: run a TQL query or SQL, stop it, and show context."""

from __future__ import annotations

import threading

from tilia_library.backend import QueryError, SqlError
from tilia_library.corpora import Corpora, Corpus, CorpusHandles
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)

MAX_MATCHES = 20_000
TIME_LIMIT_S = 30.0


class _Runs:
    """The cancel event of each tab's current run, one per (corpus, tab)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[tuple[str, str], threading.Event] = {}

    def begin(self, cid: str, tab: str) -> threading.Event:
        """Cancel the tab's current run, if any, and return a fresh event."""
        event = threading.Event()
        with self._lock:
            old = self._events.get((cid, tab))
            self._events[(cid, tab)] = event
        if old is not None:
            old.set()
        return event

    def end(self, cid: str, tab: str, event: threading.Event) -> None:
        """Forget the event when it is still the tab's current one."""
        with self._lock:
            if self._events.get((cid, tab)) is event:
                del self._events[(cid, tab)]

    def stop(self, cid: str, tab: str) -> None:
        """Cancel the tab's current run; nothing happens when there is none."""
        with self._lock:
            event = self._events.get((cid, tab))
        if event is not None:
            event.set()


def _tab_of(body: object) -> str:
    tab = body.get("tab") if isinstance(body, dict) else None
    if not isinstance(tab, str) or not tab:
        raise ApiError(400, "missing tab")
    return tab


def _query_error(error: QueryError) -> Response:
    return error_response(
        400, error.msg, detail=error.msg, pos=error.pos, end=error.end
    )


def register(server: LibraryServer, corpora: Corpora, handles: CorpusHandles) -> None:
    """Add the query routes to the server."""
    runs = _Runs()

    def handle_of(request: Request) -> tuple[Corpus, object]:
        try:
            return handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None

    def body_of(request: Request) -> dict:
        body = request.json()
        if not isinstance(body, dict):
            raise ApiError(400, "bad request")
        return body

    def post_ql(request: Request) -> Response:
        _, handle = handle_of(request)
        body = body_of(request)
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ApiError(400, "empty query")
        limit = body.get("limit")
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 0
        ):
            raise ApiError(400, "limit must be a non-negative integer")
        tab = _tab_of(body)
        cid = request.params["cid"]
        event = runs.begin(cid, tab)
        try:
            result = server.backend.run(
                handle,
                query,
                max_matches=MAX_MATCHES,
                time_limit=TIME_LIMIT_S,
                cancel=event,
            )
        except QueryError as error:
            return _query_error(error)
        finally:
            runs.end(cid, tab, event)
        total = len(result["rows"])
        if limit is not None:
            result["rows"] = result["rows"][:limit]
            result["matches"] = result["matches"][:limit]
        result["count"] = len(result["rows"])
        result["total"] = total
        result["truncated"] = result["count"] < total
        result.setdefault("action_error", None)
        return json_response(result)

    def post_ql_stop(request: Request) -> Response:
        handle_of(request)
        runs.stop(request.params["cid"], _tab_of(body_of(request)))
        return Response(204)

    def post_ql_sql(request: Request) -> Response:
        _, handle = handle_of(request)
        query = body_of(request).get("query")
        if not isinstance(query, str) or not query.strip():
            raise ApiError(400, "empty query")
        try:
            return json_response(server.backend.query_sql(handle, query))
        except QueryError as error:
            return _query_error(error)

    def post_sql(request: Request) -> Response:
        _, handle = handle_of(request)
        body = body_of(request)
        sql = body.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ApiError(400, "empty SQL")
        tab = _tab_of(body)
        cid = request.params["cid"]
        event = runs.begin(cid, tab)
        try:
            result = server.backend.sql(
                handle,
                sql,
                max_rows=MAX_MATCHES,
                time_limit=TIME_LIMIT_S,
                cancel=event,
            )
        except SqlError as error:
            return error_response(400, error.message)
        finally:
            runs.end(cid, tab, event)
        return json_response(result)

    def get_context(request: Request) -> Response:
        _, handle = handle_of(request)
        ids = [
            part
            for value in request.query.get("tl", [])
            for part in value.split(",")
            if part
        ]
        try:
            return json_response(
                server.backend.context(handle, request.params["file"], ids)
            )
        except KeyError:
            raise ApiError(404, "unknown file") from None

    router = server.router
    router.add("POST", "/api/{cid}/ql", post_ql)
    router.add("POST", "/api/{cid}/ql-stop", post_ql_stop)
    router.add("POST", "/api/{cid}/ql-sql", post_ql_sql)
    router.add("POST", "/api/{cid}/sql", post_sql)
    router.add("GET", "/api/{cid}/ql-context/{file}", get_context)
