"""The file open in TiLiA: what `FileManager.file` is."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tilia.file.media_metadata import MediaMetadata
from tilia_core import tla


@dataclass(eq=False)
class OpenDocument:
    """The file open in TiLiA, and what its state is compared with to tell whether
    the file is modified.

    `document` is the document the core read from the file, None for a file TiLiA
    didn't read, such as a new one. TiLiA builds its timelines from it and keeps it,
    with what TiLiA doesn't show, such as the timelines of kinds it doesn't know.

    `media_path` is where the media was found, not the path the file stores.
    `timelines` and `timelines_hash` are the state's when the file was last read or
    saved. `unknown_discarded` says timelines of kinds TiLiA doesn't know were taken
    out of the document, so that the file reads as modified until it is saved.

    Two are the same file only if they are the same object.
    """

    document: tla.Document | None = None
    file_path: str = ""
    media_path: str = ""
    media_metadata: MediaMetadata = field(default_factory=MediaMetadata)
    timelines: dict[str, Any] = field(default_factory=dict)
    timelines_hash: str = ""
    unknown_discarded: bool = False
