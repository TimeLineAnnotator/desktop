"""The API's handlers, one module per panel."""

from __future__ import annotations

from tilia_library.api import files, library
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.server import LibraryServer


def register_all(server: LibraryServer, corpora: Corpora) -> CorpusHandles:
    """Add every panel's routes to the server and return the corpus handles."""
    handles = CorpusHandles(server.backend, corpora)
    library.register(server, corpora)
    files.register(server, corpora, handles)
    return handles
