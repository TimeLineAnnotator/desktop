"""`.tla` files: reading every TiLiA version, migrating old files, and the one writer.

The names here are provisional until they are documented.
"""

from tilia_core.tla.errors import FileChanged, UnreadableFile
from tilia_core.tla.ids import new_id
from tilia_core.tla.model import (
    BeatUnit,
    Component,
    Document,
    FileResult,
    Measure,
    MeasureTable,
    Media,
    MigrationReport,
    ReadWarning,
    Score,
    Timeline,
    UnknownKind,
)
from tilia_core.tla.read import loads, read
from tilia_core.tla.write import FORMAT_VERSION, canonical_bytes, new_document

__all__ = [
    "FORMAT_VERSION",
    "BeatUnit",
    "Component",
    "Document",
    "FileChanged",
    "FileResult",
    "Measure",
    "MeasureTable",
    "Media",
    "MigrationReport",
    "ReadWarning",
    "Score",
    "Timeline",
    "UnknownKind",
    "UnreadableFile",
    "canonical_bytes",
    "loads",
    "new_document",
    "new_id",
    "read",
]
