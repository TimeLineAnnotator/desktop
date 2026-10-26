"""The library's own routes: which corpora there are, adding and removing them."""

from __future__ import annotations

from pathlib import Path

from tilia_library.corpora import Corpora, Corpus
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    json_response,
)

HOW_TO_ADD = "tilia library FOLDER"


def _listing(corpus: Corpus) -> dict[str, object]:
    return {
        "id": corpus.id,
        "name": corpus.name,
        "path": str(corpus.path),
        "available": corpus.available,
        "files": None,
        "unreadable": None,
        "unavailable": None,
    }


def register(server: LibraryServer, corpora: Corpora) -> None:
    """Add the library routes to the server, working on ``corpora``."""

    def get_library(request: Request) -> Response:
        listed = corpora.all()
        last = corpora.last()
        notices: list[str] = []
        if corpora.set_aside_to is not None:
            notices.append(
                "library.toml couldn't be read; kept as "
                f"{corpora.set_aside_to.name}, starting with no corpora"
            )
        data: dict[str, object] = {
            "corpora": [_listing(c) for c in listed],
            "last_corpus": last.id if last else None,
        }
        if not listed:
            data["how_to_add"] = HOW_TO_ADD
        data["notices"] = notices
        return json_response(data)

    def add_corpus(request: Request) -> Response:
        body = request.json()
        path = body.get("path") if isinstance(body, dict) else None
        if not isinstance(path, str):
            raise ApiError(400, "the body must be an object with a string path")
        if not Path(path).is_absolute():
            raise ApiError(400, f"{path} is not an absolute path")
        try:
            corpus = corpora.add(Path(path))
        except NotADirectoryError:
            raise ApiError(400, f"{path} is not a folder") from None
        return json_response({"id": corpus.id})

    def delete_corpus(request: Request) -> Response:
        if not corpora.remove(request.params["cid"]):
            raise ApiError(404, "unknown corpus")
        return Response(204)

    server.router.add("GET", "/api/library", get_library)
    server.router.add("POST", "/api/corpora", add_corpus)
    server.router.add("DELETE", "/api/corpora/{cid}", delete_corpus)
