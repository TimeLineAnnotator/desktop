"""The API's handlers, one module per panel."""

from __future__ import annotations

from tilia_library.api import files, library, query
from tilia_library.api import liveness as liveness_api
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.liveness import Liveness
from tilia_library.server import LibraryServer


def register_all(
    server: LibraryServer, corpora: Corpora, liveness: Liveness | None = None
) -> CorpusHandles:
    """Add every panel's routes to the server and return the corpus handles.

    Without a ``liveness``, one is made and started; a given one is used as it is.
    """
    if liveness is None:
        liveness = Liveness(server.backend)
        liveness.start()
    handles = CorpusHandles(server.backend, corpora, on_open=liveness.watch)
    library.register(server, corpora, liveness=liveness)
    files.register(server, corpora, handles)
    liveness_api.register(server, corpora, handles, liveness)
    query.register(server, corpora, handles)
    return handles
