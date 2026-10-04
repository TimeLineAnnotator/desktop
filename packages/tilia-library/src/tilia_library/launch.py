"""Opening a file in TiLiA, without importing the app."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from tilia_library.corpora import Corpora, Corpus, CorpusHandles
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)

_STARTFILE = getattr(os, "startfile", None)  # only Windows has it


class TiliaNotFound(Exception):
    """Neither the TiLiA program nor the system could open the file."""


def _tilia_script(executable: str, platform: str) -> Path:
    name = "tilia.exe" if platform == "win32" else "tilia"
    return Path(executable).parent / name


def open_in_tilia(
    path: Path,
    *,
    entry_points=importlib.metadata.entry_points,
    popen=subprocess.Popen,
    startfile=_STARTFILE,
    platform: str = sys.platform,
    executable: str = sys.executable,
) -> str:
    """Open a file in TiLiA's window; return "tilia-gui", or "system".

    When TiLiA's ``gui`` command is installed next to this Python, run it;
    otherwise ask the system to open the file with whatever is registered for
    it. Raises ``TiliaNotFound`` when nothing could be started.
    """
    windows = platform == "win32"
    detach: dict[str, object] = {"close_fds": True}
    if windows:
        detach["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        detach["start_new_session"] = True

    def start(command: list[str]) -> None:
        popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **detach,
        )

    try:
        script = _tilia_script(executable, platform)
        has_gui = any(e.name == "gui" for e in entry_points(group="tilia.commands"))
        if has_gui and script.is_file():
            start([str(script), "gui", str(path)])
            return "tilia-gui"
        if windows:
            if startfile is None:
                raise TiliaNotFound("no way to open files on this system")
            startfile(str(path))
        else:
            start(["open" if platform == "darwin" else "xdg-open", str(path)])
    except OSError as error:
        raise TiliaNotFound(str(error)) from error
    return "system"


def register(
    server: LibraryServer,
    corpora: Corpora,
    handles: CorpusHandles,
    opener: Callable[[Path], str] = open_in_tilia,
) -> None:
    """Add the route that opens a file in TiLiA to the server."""

    def open_file(request: Request) -> Response:
        try:
            corpus, handle = handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None
        rows = server.backend.files(handle)
        row = next((r for r in rows if r["file_id"] == request.params["file"]), None)
        if row is None:
            raise ApiError(404, "unknown file")
        path = _path_of(corpus, row["path"])
        if not path.is_file():
            raise ApiError(404, "the file is gone")
        try:
            how = opener(path)
        except TiliaNotFound:
            return error_response(503, "TiLiA wasn't found")
        return json_response({"how": how}, 202)

    server.router.add("POST", "/api/{cid}/files/{file}/open", open_file)


def _path_of(corpus: Corpus, text: str) -> Path:
    """A file's path as the core gives it: absolute, or inside the corpus folder."""
    path = Path(text)
    return path if path.is_absolute() else corpus.path / path
