"""The edit log routes: list what bulk edits did, and undo one."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
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


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    liveness: Liveness,
    skip_files: Callable[[str], set[Path]] = lambda cid: set(),
    on_written: Callable[[str, list[str], str], None] | None = None,
) -> None:
    """Add the edit log routes to the server."""
    undo_lock = threading.Lock()  # one undo at a time, so an entry is undone once

    def handle_of(request: Request) -> object:
        try:
            return handles.get(request.params["cid"])[1]
        except KeyError:
            raise ApiError(404, "unknown corpus") from None

    def names_of(handle: object, file_ids: Iterable[str]) -> dict[str, str]:
        """The names of the files the backend still lists, among these ids."""
        wanted = set(file_ids)
        return {
            f["file_id"]: f["name"]
            for f in server.backend.files(handle)
            if f["file_id"] in wanted
        }

    def get_log(request: Request) -> Response:
        handle = handle_of(request)
        entries = server.backend.edit_log(handle)
        mentioned = [fid for entry in entries for fid in entry["files"]]
        return json_response(
            {
                "entries": entries,
                "file_names": names_of(handle, mentioned),
                "generation": server.backend.generation(handle),
            }
        )

    def post_undo(request: Request) -> Response:
        handle = handle_of(request)
        with undo_lock:
            return undo_entry(request, handle)

    def undo_entry(request: Request, handle: object) -> Response:
        cid = request.params["cid"]
        entry_id = request.params["entry"]
        found = [e for e in server.backend.edit_log(handle) if e["entry"] == entry_id]
        if not found:
            return error_response(404, "unknown edit")
        if found[0]["undone"]:
            return error_response(409, "this edit was already undone")
        try:
            result = server.backend.undo(handle, entry_id, skip_files(cid))
        except KeyError:
            return error_response(404, "unknown edit")
        liveness.poke(cid)
        if on_written is not None:
            on_written(cid, list(result["restored"]), entry_id)
        mentioned = (
            result["restored"]
            + [r["file_id"] for r in result["refused"]]
            + [s["file_id"] for s in result["skipped"]]
        )
        return json_response({**result, "file_names": names_of(handle, mentioned)})

    router = server.router
    router.add("GET", "/api/{cid}/edit-log", get_log)
    router.add("POST", "/api/{cid}/edit-log/{entry}/undo", post_undo)
