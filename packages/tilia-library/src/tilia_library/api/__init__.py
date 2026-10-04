"""The API's handlers, one module per panel."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from tilia_library.api import (
    categories,
    edit_log,
    edits,
    files,
    library,
    media,
    query,
    statistics,
)
from tilia_library.api import windows as windows_api
from tilia_library.api import liveness as liveness_api
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library import launch
from tilia_library.launch import open_in_tilia
from tilia_library.liveness import Liveness
from tilia_library.previews import Previews
from tilia_library.server import LibraryServer
from tilia_library.windows import Windows

logger = logging.getLogger(__name__)


def register_all(
    server: LibraryServer,
    corpora: Corpora,
    liveness: Liveness | None = None,
    *,
    previews: Previews | None = None,
    skip_files: Callable[[str], set[Path]] | None = None,
    windows: Windows | None = None,
    opener: Callable[[Path], str] = open_in_tilia,
) -> CorpusHandles:
    """Add every panel's routes to the server and return the corpus handles.

    Without a ``liveness``, one is made and started; a given one is used as it is. The edit previews are kept in one
    ``Previews`` for the server (a given one, or a new one), shared by the edit and categories routes. The TiLiA
    windows are tracked in one ``Windows`` (a given one, or a new one); unless ``skip_files`` is given, the files they
    report as unsaved are the ones edits leave alone.
    """
    if windows is None:
        windows = Windows()
    if skip_files is None:
        skip_files = lambda cid: windows.unsaved()  # noqa: E731
    open_windows = windows

    if liveness is None:
        liveness = Liveness(server.backend)
        liveness.start()
    handles = CorpusHandles(server.backend, corpora, on_open=liveness.watch)
    library.register(server, corpora, liveness=liveness)
    files.register(server, corpora, handles)
    liveness_api.register(server, corpora, handles, liveness)
    query.register(server, corpora, handles)

    def on_written(cid: str, file_ids: list[str], entry: str) -> None:
        # The files are written by now: failing to tell the windows must not
        # turn the edit's answer into an error.
        try:
            corpus, handle = handles.get(cid)
            paths = {}
            for row in server.backend.files(handle):
                path = Path(row["path"])
                paths[row["file_id"]] = (
                    path if path.is_absolute() else corpus.path / path
                )
            open_windows.written(
                [paths[fid] for fid in file_ids if fid in paths], cid, entry
            )
        except Exception:
            logger.exception("could not tell TiLiA windows about edit %s", entry)

    windows_api.register(server, corpora, handles, liveness, windows)
    previews = previews or Previews()
    edits.register(server, corpora, handles, liveness, previews, skip_files, on_written)
    categories.register(server, corpora, handles, previews, skip_files)
    statistics.register(server, corpora, handles)
    media.register(server, corpora, handles)
    launch.register(server, corpora, handles, opener)
    edit_log.register(server, corpora, handles, liveness, skip_files, on_written)
    return handles
