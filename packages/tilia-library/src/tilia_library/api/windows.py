"""The window routes: TiLiA windows say what they have open, and when they save."""

from __future__ import annotations

import os
from pathlib import Path

from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.liveness import Liveness
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)
from tilia_library.windows import LEASE_S, POLL_S, Windows, path_key


def _absolute(value: object) -> str:
    if not isinstance(value, str) or not value or not os.path.isabs(value):
        raise ApiError(400, "a path must be absolute")
    return value


def _files_of(body: object) -> list[tuple[str, bool]]:
    files = body.get("files") if isinstance(body, dict) else None
    if not isinstance(files, list):
        raise ApiError(400, "files must be a list")
    found = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("unsaved"), bool):
            raise ApiError(400, "each file needs a path and an unsaved flag")
        found.append((_absolute(item.get("path")), item["unsaved"]))
    return found


def _inside(folder: Path, path: Path) -> bool:
    folder_key = os.path.join(path_key(folder), "")
    return path_key(path).startswith(folder_key)


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    liveness: Liveness,
    windows: Windows,
) -> None:
    """Add the window routes to the server."""

    def unknown() -> Response:
        return error_response(404, "unknown window")

    def post_window(request: Request) -> Response:
        body = request.json()
        pid = body.get("pid") if isinstance(body, dict) else None
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ApiError(400, "pid must be an integer")
        window = windows.register(pid, _files_of(body))
        return json_response(
            {"window": window, "poll_seconds": POLL_S, "lease_seconds": LEASE_S}
        )

    def post_sync(request: Request) -> Response:
        files = _files_of(request.json())
        try:
            events = windows.sync(request.params["window"], files)
        except KeyError:
            return unknown()
        return json_response({"events": events})

    def post_saved(request: Request) -> Response:
        body = request.json()
        path = _absolute(body.get("path") if isinstance(body, dict) else None)
        try:
            windows.saved(request.params["window"], path)
        except KeyError:
            return unknown()
        resolved = Path(path).resolve()
        for cid, corpus, handle in handles.opened():
            if _inside(corpus.path, resolved):
                server.backend.reread(handle, resolved)
                liveness.poke(cid)
        return Response(204)

    def delete_window(request: Request) -> Response:
        windows.close(request.params["window"])
        return Response(204)

    router = server.router
    router.add("POST", "/api/windows", post_window, access="bearer")
    router.add("POST", "/api/windows/{window}/sync", post_sync, access="bearer")
    router.add("POST", "/api/windows/{window}/saved", post_saved, access="bearer")
    router.add("DELETE", "/api/windows/{window}", delete_window, access="bearer")
