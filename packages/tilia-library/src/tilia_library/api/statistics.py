"""The statistics panel's route: tables of a query's result, with chart hints."""

from __future__ import annotations

from tilia_library.backend import QueryError
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)


def _chart(table: dict, by: list[str]) -> dict | None:
    """What to draw for a table, or None for a table that is only read."""
    name = table["name"]
    if name == "counts":
        series = by[1] if len(by) > 1 else None
        return {"kind": "bar", "x": by[0], "y": "matches", "series": series}
    if name == "durations":
        return {"kind": "bar", "x": by[0], "y": "median", "series": None}
    if name == "positions":
        return {"kind": "bar", "x": "from_pct", "y": "n", "series": by[0]}
    return None


def register(server: LibraryServer, corpora: Corpora, handles: CorpusHandles) -> None:
    """Add the statistics route to the server."""

    def post_statistics(request: Request) -> Response:
        try:
            _, handle = handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None
        body = request.json()
        if not isinstance(body, dict):
            raise ApiError(400, "bad request")
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ApiError(400, "empty query")
        by = body.get("by")
        if (
            not isinstance(by, list)
            or len(by) not in (1, 2)
            or not all(isinstance(key, str) and key for key in by)
        ):
            raise ApiError(400, "by must name one or two keys")
        fold = body.get("fold", False)
        if not isinstance(fold, bool):
            raise ApiError(400, "fold must be true or false")
        tab = body.get("tab")
        if not isinstance(tab, str) or not tab:
            raise ApiError(400, "missing tab")
        try:
            result = server.backend.statistics(handle, query, by, fold=fold)
        except QueryError as error:
            return error_response(
                400, error.msg, detail=error.msg, pos=error.pos, end=error.end
            )
        for table in result["tables"]:
            table["chart"] = _chart(table, by)
        result.setdefault("warnings", [])
        return json_response(result)

    server.router.add("POST", "/api/{cid}/statistics", post_statistics)
