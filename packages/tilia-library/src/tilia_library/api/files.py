"""The files panel's routes: the list of files and one file's timelines."""

from __future__ import annotations

from tilia_library.corpora import Corpora, Corpus, CorpusHandles
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    json_response,
)


def register(server: LibraryServer, corpora: Corpora, handles: CorpusHandles) -> None:
    """Add the files routes to the server."""

    def handle_of(request: Request) -> tuple[Corpus, object]:
        try:
            return handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None

    def get_files(request: Request) -> Response:
        corpus, handle = handle_of(request)
        backend = server.backend
        return json_response(
            {
                "generation": backend.generation(handle),
                "available": corpus.available,
                "rows": backend.files(handle),
            }
        )

    def get_file(request: Request) -> Response:
        _, handle = handle_of(request)
        backend = server.backend
        try:
            detail = backend.file_detail(handle, request.params["file"])
        except KeyError:
            raise ApiError(404, "unknown file") from None
        detail["generation"] = backend.generation(handle)
        return json_response(detail)

    server.router.add("GET", "/api/{cid}/files", get_files)
    server.router.add("GET", "/api/{cid}/files/{file}", get_file)
