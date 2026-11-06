"""`.tla` files: reading every TiLiA version, migrating old files, and the one writer.

The names here are provisional until they are documented.
"""

from tilia_core.tla.edits import CantMoveMark, delete_beat, mark_edited, mark_moved
from tilia_core.tla.errors import (
    BrokenRules,
    DraftFormat,
    FileChanged,
    FileInUse,
    NewerFormat,
    UnreadableFile,
)
from tilia_core.tla.folder import migrate_folder
from tilia_core.tla.ids import new_id
from tilia_core.tla.model import (
    BeatUnit,
    Component,
    Document,
    FileResult,
    FolderNotListed,
    Measure,
    MeasureTable,
    Media,
    MigrationReport,
    Outcome,
    ReadWarning,
    Score,
    Timeline,
    UnknownKind,
    measure_table,
)
from tilia_core.tla.layout import FORMAT_VERSION, schema
from tilia_core.tla.media_files import as_media_path, media
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
    "DraftFormat",
    "FORMAT_VERSION",
    "TEMPORARY_PATTERN",
    "BeatUnit",
    "BrokenRules",
    "CantMoveMark",
    "Component",
    "Document",
    "FileChanged",
    "FileInUse",
    "FileResult",
    "FolderNotListed",
    "Measure",
    "MeasureTable",
    "Media",
    "MigrationReport",
    "NewerFormat",
    "Outcome",
    "ReadWarning",
    "Score",
    "Timeline",
    "UnknownKind",
    "UnreadableFile",
    "as_media_path",
    "canonical_bytes",
    "delete_beat",
    "fingerprint",
    "fingerprint_of",
    "is_temporary",
    "loads",
    "mark_edited",
    "mark_moved",
    "measure_table",
    "media",
    "migrate_folder",
    "new_document",
    "new_id",
    "read",
    "schema",
    "write",
]
