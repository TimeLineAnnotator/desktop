"""`.tla` files: reading every TiLiA version, migrating old files, and the one writer.

The names here are provisional until they are documented.
"""

from tilia_core.tla.errors import FileChanged, FileInUse, UnreadableFile
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
from tilia_core.tla.layout import FORMAT_VERSION, schema
from tilia_core.tla.media import media  # the function, in place of its module
from tilia_core.tla.reader import loads, read
from tilia_core.tla.writer import (
    ABSENT,
    TEMPORARY_PATTERN,
    canonical_bytes,
    fingerprint,
    fingerprint_of,
    is_temporary,
    new_document,
    write,
)

__all__ = [
    "ABSENT",
    "FORMAT_VERSION",
    "TEMPORARY_PATTERN",
    "BeatUnit",
    "Component",
    "Document",
    "FileChanged",
    "FileInUse",
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
    "fingerprint",
    "fingerprint_of",
    "is_temporary",
    "loads",
    "media",
    "new_document",
    "new_id",
    "read",
    "schema",
    "write",
]
