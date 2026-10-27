"""The bulk edit routes: preview a statement, then apply the writes kept."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from tilia_library.backend import QueryError
from tilia_library.corpora import Corpora, Corpus, CorpusHandles
from tilia_library.liveness import Liveness
from tilia_library.previews import Previews, same_writes, writes_by_key
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)


def _query_error(error: QueryError) -> Response:
    return error_response(
        400, error.msg, detail=error.msg, pos=error.pos, end=error.end
    )


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    liveness: Liveness,
    previews: Previews,
    skip_files: Callable[[str], set[Path]] = lambda cid: set(),
    on_written: Callable[[str, list[str], str], None] | None = None,
) -> None:
    """Add the bulk edit routes to the server."""
    apply_lock = threading.Lock()  # one apply at a time, so a preview is written once

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

    def preview_response(
        status: int, statement: str, answer: dict, cid: str, tab: str, **extra: object
    ) -> Response:
        preview = previews.add(cid, tab, statement, answer)
        return json_response(
            {**extra, "preview": preview.id, "statement": statement, **answer},
            status,
        )

    def post_edit(request: Request) -> Response:
        _, handle = handle_of(request)
        body = body_of(request)
        statement = body.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            raise ApiError(400, "empty statement")
        tab = body.get("tab")
        if not isinstance(tab, str) or not tab:
            raise ApiError(400, "missing tab")
        cid = request.params["cid"]
        try:
            answer = server.backend.plan(handle, statement, skip_files(cid))
        except QueryError as error:
            return _query_error(error)
        return preview_response(200, statement, answer, cid, tab)

    def post_apply(request: Request) -> Response:
        _, handle = handle_of(request)
        body = body_of(request)
        preview_id = body.get("preview")
        only = body.get("only")
        if not isinstance(only, list) or not all(isinstance(k, str) for k in only):
            raise ApiError(400, "only must be a list of keys")
        if not only:
            raise ApiError(400, "nothing to apply")
        cid = request.params["cid"]
        with apply_lock:
            return apply_preview(cid, handle, preview_id, only)

    def apply_preview(
        cid: str, handle: object, preview_id: object, only: list[str]
    ) -> Response:
        preview = previews.get(preview_id) if isinstance(preview_id, str) else None
        if preview is None or preview.cid != cid:
            raise ApiError(410, "the preview expired; preview again")
        planned = writes_by_key(preview.answer)
        for key in only:
            if key not in planned:
                return error_response(400, "unknown key", detail=key)
        try:
            fresh = server.backend.plan(handle, preview.statement, skip_files(cid))
        except QueryError as error:
            return _query_error(error)
        if not same_writes(preview.answer, fresh, only):
            return preview_response(
                409,
                preview.statement,
                fresh,
                cid,
                preview.tab,
                error="the files changed since the preview",
            )
        result = server.backend.apply(handle, fresh, set(only), skip_files(cid))
        previews.discard(preview.id)
        liveness.poke(cid)
        if on_written is not None:
            on_written(cid, list(result["written"]), result["entry"])
        return json_response(result)

    router = server.router
    router.add("POST", "/api/{cid}/ql-edit", post_edit)
    router.add("POST", "/api/{cid}/ql-apply", post_apply)
