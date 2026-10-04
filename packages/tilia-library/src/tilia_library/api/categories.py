"""The categories panel's routes: the chips, the components of a selection, and edits of them."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from tilia_library import chips
from tilia_library.api.query import MAX_MATCHES, TIME_LIMIT_S
from tilia_library.backend import QueryError
from tilia_library.corpora import Corpora, Corpus, CorpusHandles
from tilia_library.previews import Previews
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


def _text(body: dict, name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise ApiError(400, f"{name} must be text")
    return value


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    previews: Previews,
    skip_files: Callable[[str], set[Path]] = lambda cid: set(),
) -> None:
    """Add the categories routes to the server."""

    def handle_of(request: Request) -> tuple[Corpus, object]:
        try:
            return handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None

    def selection_of(request: Request) -> tuple[dict, list[str], str, str]:
        """The body, and its categories, mode and tab, checked."""
        body = request.json()
        if not isinstance(body, dict):
            raise ApiError(400, "bad request")
        categories = body.get("categories")
        if not isinstance(categories, list) or not all(
            isinstance(c, str) for c in categories
        ):
            raise ApiError(400, "categories must be a list of text")
        if not isinstance(body.get("fold"), bool):
            raise ApiError(400, "fold must be true or false")
        tab = body.get("tab")
        if not isinstance(tab, str) or not tab:
            raise ApiError(400, "missing tab")
        return body, categories, _text(body, "mode"), tab

    def get_categories(request: Request) -> Response:
        _, handle = handle_of(request)
        fold = request.query.get("fold", [None])[0]
        if fold not in ("0", "1"):
            raise ApiError(400, "fold must be 0 or 1")
        answer = server.backend.categories(handle, fold == "1")
        answer["categories"].sort(key=lambda row: (-row["n"], row["category"]))
        return json_response(answer)

    def post_components(request: Request) -> Response:
        _, handle = handle_of(request)
        body, categories, mode, _ = selection_of(request)
        grammar = server.backend.categories(handle, body["fold"])["grammar"]
        try:
            statement = chips.selection(categories, mode, grammar)
        except chips.Refused as refused:
            return error_response(400, str(refused))
        try:
            result = server.backend.run(
                handle,
                statement,
                max_matches=MAX_MATCHES,
                time_limit=TIME_LIMIT_S,
                cancel=threading.Event(),
            )
        except QueryError as error:
            return _query_error(error)
        return json_response({"statement": statement, **result})

    def post_edit(request: Request) -> Response:
        _, handle = handle_of(request)
        body, categories, mode, tab = selection_of(request)
        grammar = server.backend.categories(handle, body["fold"])["grammar"]
        op = body.get("op")
        field = _text(body, "field")
        try:
            if op == "set":
                statement = chips.set_statement(
                    categories, mode, grammar, field, _text(body, "value")
                )
            elif op == "replace":
                every = body.get("every", False)
                if not isinstance(every, bool):
                    raise ApiError(400, "every must be true or false")
                statement = chips.replace_statement(
                    categories,
                    mode,
                    grammar,
                    field,
                    _text(body, "pattern"),
                    _text(body, "replacement"),
                    every,
                )
            else:
                raise ApiError(400, 'op is "set" or "replace"')
        except chips.Refused as refused:
            return error_response(400, str(refused))
        cid = request.params["cid"]
        try:
            answer = server.backend.plan(handle, statement, skip_files(cid))
        except QueryError as error:
            return _query_error(error)
        preview = previews.add(cid, tab, statement, answer)
        return json_response({"preview": preview.id, "statement": statement, **answer})

    router = server.router
    router.add("GET", "/api/{cid}/categories", get_categories)
    router.add("POST", "/api/{cid}/categories/components", post_components)
    router.add("POST", "/api/{cid}/categories/edit", post_edit)
