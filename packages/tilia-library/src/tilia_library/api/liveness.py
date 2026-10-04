"""The routes that tell a page whether the files changed, and ask for a rescan."""

from __future__ import annotations

from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.liveness import Liveness
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    json_response,
)


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    liveness: Liveness,
) -> None:
    """Add the state and rescan routes to the server."""

    def get_state(request: Request) -> Response:
        cid = request.params["cid"]
        state = liveness.state(cid)
        if state is None:
            corpus = corpora.get(cid)
            if corpus is None:
                raise ApiError(404, "unknown corpus")
            state = {
                "generation": None,
                "scanning": False,
                "available": corpus.available,
                "files": None,
                "unreadable": None,
                "unavailable": None,
                "last_scan": None,
            }
        return json_response(state)

    def rescan(request: Request) -> Response:
        cid = request.params["cid"]
        try:
            handles.get(cid)
        except KeyError:
            raise ApiError(404, "unknown corpus") from None
        liveness.poke(cid)
        return json_response({}, 202)

    server.router.add("GET", "/api/{cid}/state", get_state)
    server.router.add("POST", "/api/{cid}/rescan", rescan)
