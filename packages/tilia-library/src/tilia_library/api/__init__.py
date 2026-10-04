"""The API's handlers, one module per panel."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tilia_library.api import edits, files, library, query, statistics
from tilia_library.api import liveness as liveness_api
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.liveness import Liveness
from tilia_library.previews import Previews
from tilia_library.server import LibraryServer


def register_all(
    server: LibraryServer,
    corpora: Corpora,
    liveness: Liveness | None = None,
    *,
    previews: Previews | None = None,
    skip_files: Callable[[str], set[Path]] = lambda cid: set(),
) -> CorpusHandles:
    """Add every panel's routes to the server and return the corpus handles.

    Without a ``liveness``, one is made and started; a given one is used as it is. The edit previews are kept in one
    ``Previews`` for the server (a given one, or a new one).
    """
    if liveness is None:
        liveness = Liveness(server.backend)
        liveness.start()
    handles = CorpusHandles(server.backend, corpora, on_open=liveness.watch)
    library.register(server, corpora, liveness=liveness)
    files.register(server, corpora, handles)
    liveness_api.register(server, corpora, handles, liveness)
    query.register(server, corpora, handles)
    edits.register(
        server, corpora, handles, liveness, previews or Previews(), skip_files
    )
    statistics.register(server, corpora, handles)
    return handles
