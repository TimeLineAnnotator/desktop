"""Building a document from a script: a new file, its fields, its media and its timelines."""

from __future__ import annotations

import logging
import math
import numbers
import os
import re
import struct
from pathlib import Path
from typing import BinaryIO

from tilia_core import tla
from tilia_core.labels import nfc
from tilia_core.timemap import pattern
from tilia_core.tla.layout import TIMELINE_SHAPES

logger = logging.getLogger(__name__)

# TiLiA's texts (tilia/errors.py and tilia/ui/cli/), word for word.
_CANT_SET_MEDIA_LENGTH = (
    "Cannot set media length with 'metadata set'."
    " Use 'metadata set-media-length' instead."
)
_NOT_A_MEDIA_LENGTH = (
    "Cannot set media metadata to {}. Media length must be a positive number."
)
_MEDIA_LOADED = "Can't change media length when a media file is loaded."
_MEDIA_NOT_FOUND = "No media available at '{}'. Try using another path."
_NO_DURATION = (
    "No media loaded and no duration set. Load a media file with 'load-media'"
    " or set a duration with 'metadata set-media-length'."
)
_NOT_APPLICABLE = "'{}' is not valid for timeline kind '{}'."
_INVALID_BEAT_PATTERN = "Invalid beat pattern '{}': {}"
# The spec's, where TiLiA has none (FR-052, FR-056), and the one text for a
# value that isn't one (TimeLineAnnotator/project-management#298 (texts for the
# rules)), which rules.not_valid will give.
_HAS_COMPONENTS = (
    "The media length can't change once timelines have components:"
    " rescale the file in TiLiA."
)
_NO_LENGTH = (
    "{}: give its length with --duration-if-error,"
    " or set it first with metadata set-media-length"
)
_NOT_VALID = "{} is not a valid {}."

# A millisecond, the precision of TiLiA's player: a file TiLiA saved holds its
# media's length in whole milliseconds, and a WAV's header gives it exactly
# (TimeLineAnnotator/project-management#327 (a media length within a
# millisecond)).
_SAME_LENGTH = 0.001

# tilia.constants.YOUTUBE_URL_REGEX. A stand-in until WP3 gives its copy
# (TimeLineAnnotator/project-management#176 (media paths)), which replaces it
# (TimeLineAnnotator/project-management#317 (WP3's YouTube pattern in build)).
_YOUTUBE_URL = re.compile(
    r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))"
    r"(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
)

# The kinds a script adds; the others come with WP28.
_KINDS = ("beat", "hierarchy", "marker", "harmony")
# Without a height, TiLiA's out-of-the-box defaults, fixed in the core: its
# settings' default heights, and for a beat timeline 35 plus the band its time
# signatures take (34), which a new one shows. A harmony timeline has no height
# of its own: its levels have one.
_DEFAULT_HEIGHTS = {"marker": 30, "hierarchy": 120, "beat": 35 + 34}
# TiLiA's set_data refuses a lower height
# (TimeLineAnnotator/project-management#316 (which heights timelines add accepts)).
_MIN_HEIGHT = 10


def new_script_document() -> tla.Document:
    """A new document with TiLiA's two required fields, `title` "Untitled" and
    `notes` "", and no others (FR-054)."""
    document = tla.new_document()
    document.metadata = {"title": "Untitled", "notes": ""}
    return document


def set_field(document: tla.Document, name: str, value: str | list[str]) -> None:
    """Set the file field `name`, or add it after the others (FR-050).

    Raises ValueError for `media length`, which isn't a field: it is set with
    `set_media_length`.
    """
    if name.lower() == "media length":
        raise ValueError(_CANT_SET_MEDIA_LENGTH)
    if isinstance(value, str):
        text: str | list[str] = nfc(value)
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        text = [nfc(item) for item in value]
    else:
        raise TypeError(f"a field's value is text or a list of texts, not {value!r}")
    document.metadata[nfc(name)] = text


def set_media_length(document: tla.Document, seconds: float) -> None:
    """Set the media length, in seconds (FR-051, FR-056).

    Raises ValueError for a length that isn't a positive number; while media is
    attached, whose length comes with it; and for a change to a known length
    once timelines have components, which nothing moves or crops. A length
    less than a millisecond from the known one isn't a change then, and the
    known one stays.
    """
    length = _media_length(seconds)
    if document.media_path:
        raise ValueError(_MEDIA_LOADED)
    document.media_length = _check_change(document, length)


def load_media(
    document: tla.Document,
    path: str | os.PathLike[str],
    *,
    duration_if_error: float | None = None,
) -> float:
    """Record the media, a local file or a YouTube link, and set its length
    (FR-052, FR-056). Returns the length set.

    A local path must be a file, and is stored absolute: the writer stores it
    relative to the saved file. The length is a WAV's, read from its header;
    else `duration_if_error`; else, while no media is attached, the known
    length. Without one, or for a change `set_media_length` refuses, raises
    ValueError, and the document is left as it was. Where `set_media_length`
    keeps the known length, so does this.
    """
    text = os.fspath(path)
    length: float | None = None
    if _YOUTUBE_URL.match(text):
        stored = name = text
    else:
        local = Path(text.replace("\\", "/"))
        # Not Path.exists: a folder isn't media, and os.path.isfile gives False,
        # rather than raising, for a path the system can't look at.
        if not os.path.isfile(local):
            raise ValueError(_MEDIA_NOT_FOUND.format(local))
        stored = str(local.resolve()).replace("\\", "/")
        name = local.name
        if local.suffix.lower() == ".wav":
            length = wav_length(local)
    if length is None:
        if duration_if_error is not None:
            length = _media_length(duration_if_error)
        elif not document.media_path:
            length = _known_length(document)
        if length is None:
            raise ValueError(_NO_LENGTH.format(name))
    length = _check_change(document, length)
    document.media_path = stored
    document.media_length = length
    return length


def wav_length(path: str | os.PathLike[str]) -> float | None:
    """A WAV file's length in seconds, from its header; None for a file that
    isn't a WAV, or whose header can't be read (research R8).

    The header is read with `struct`, since Python's `wave` module refuses
    floating-point WAVs, and WAVE_FORMAT_EXTENSIBLE before Python 3.12.
    """
    try:
        with open(path, "rb") as file:
            return _wav_length(file, os.fstat(file.fileno()).st_size)
    except OSError as error:
        logger.info("Can't read %s: %s", path, error)
        return None


def _wav_length(file: BinaryIO, size: int) -> float | None:
    """The `data` chunk's size over the `fmt ` chunk's byte rate (or block
    align times sample rate). The `fmt ` chunk's first 14 bytes, the oldest
    form of it, hold both. A data size past the end of the file, as a WAV
    written as a stream gives it, counts the bytes there."""
    head = file.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:] != b"WAVE":
        return None
    byte_rate: int | None = None
    data_size: int | None = None
    position = 12
    while byte_rate is None or data_size is None:
        file.seek(position)
        header = file.read(8)
        if len(header) < 8:
            return None
        name, (chunk_size,) = header[:4], struct.unpack("<I", header[4:])
        start = position + 8
        if name == b"fmt ":
            fmt = file.read(14)
            if chunk_size < 14 or len(fmt) < 14:
                return None
            _, _, rate, bytes_per_second, align = struct.unpack("<HHIIH", fmt)
            byte_rate = bytes_per_second or align * rate
        elif name == b"data":
            data_size = min(chunk_size, size - start)
        position = start + chunk_size + chunk_size % 2  # a pad byte after odd sizes
    if not byte_rate or not data_size:
        return None
    return data_size / byte_rate


def add_timeline(
    document: tla.Document,
    kind: str,
    name: str = "",
    *,
    height: int | None = None,
    beat_pattern: str | None = None,
) -> str:
    """Add an empty timeline after the others, and return its id (FR-055, FR-060).

    `kind` is "beat", "hierarchy", "marker" or "harmony". Without a height, the
    timeline gets TiLiA's default; a harmony timeline takes none. A beat
    timeline shows its time signatures, and keeps `beat_pattern` as given
    ("4" without one).

    Raises ValueError while no media length is known, and for a height or a
    beat pattern the kind doesn't take or TiLiA wouldn't keep; TypeError for a
    beat pattern that isn't text.
    """
    if _known_length(document) is None:
        raise ValueError(_NO_DURATION)
    if kind not in _KINDS:
        kinds = ", ".join(_KINDS)
        raise ValueError(f"can't add a timeline of kind {kind!r}: give one of {kinds}")
    if beat_pattern is not None and kind != "beat":
        raise ValueError(_NOT_APPLICABLE.format("--beat-pattern", kind))
    if height is not None and kind == "harmony":
        raise ValueError(_NOT_APPLICABLE.format("--height", kind))
    if height is not None and not _is_height(height):
        raise ValueError(_NOT_VALID.format(height, "height"))
    if beat_pattern is not None:
        if not isinstance(beat_pattern, str):
            raise TypeError(
                f"a beat pattern is text, such as '10[4] 3', not {beat_pattern!r}"
            )
        parsed = pattern.parse(beat_pattern)
        if not parsed.is_complete:
            raise ValueError(_INVALID_BEAT_PATTERN.format(beat_pattern, parsed.error))

    # The format's defaults, as the reader fills them in. A beat timeline's
    # show_time_signatures is true there, as desktop#621 makes new ones.
    defaults = TIMELINE_SHAPES[kind].defaults
    attrs = {key: value for key, value in defaults.items() if key != "name"}
    if kind != "harmony":
        attrs["height"] = _DEFAULT_HEIGHTS[kind] if height is None else int(height)
    if beat_pattern is not None:
        attrs["beat_pattern"] = beat_pattern
    ordinals = (timeline.ordinal for timeline in document.timelines.values())
    timeline_id = tla.new_id()
    document.timelines[timeline_id] = tla.Timeline(
        id=timeline_id,
        kind=kind,
        ordinal=max(ordinals, default=0) + 1,
        name=nfc(name),
        attrs=attrs,
    )
    return timeline_id


def find_timeline(
    document: tla.Document, *, name: str | None = None, ordinal: int | None = None
) -> str:
    """The id of the timeline with this ordinal, or else of the first, by
    ordinal, with this name, as TiLiA's command line finds an import's target.

    Raises ValueError when there is none.
    """
    if ordinal is not None:
        for timeline_id, timeline in document.timelines.items():
            if timeline.ordinal == ordinal:
                return timeline_id
        raise ValueError(f"No timeline found with {ordinal=}")
    if name is None:
        raise TypeError("find_timeline needs a name or an ordinal")
    wanted = nfc(name)
    by_ordinal = sorted(document.timelines.items(), key=lambda item: item[1].ordinal)
    for timeline_id, timeline in by_ordinal:
        if timeline.name == wanted:
            return timeline_id
    raise ValueError(f"No timeline found with {name=}")


def _media_length(value: object) -> float:
    """`value` as a media length: a number of seconds above 0. A file can't hold
    NaN or infinity."""
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        try:
            length = float(value)
        except OverflowError:
            length = math.inf
        if math.isfinite(length) and length > 0:
            return length
    raise ValueError(_NOT_A_MEDIA_LENGTH.format(value))


def _known_length(document: tla.Document) -> float | None:
    """The document's media length, as it is, when `_media_length` accepts it;
    else None. The reader keeps a file's length as the file has it, and one
    the format doesn't allow (text, a bool, zero or less, a whole number too
    large for a float) counts as no length, as WP9's time map reads it
    (TimeLineAnnotator/project-management#216 (choose a document's time map
    by role))."""
    length = document.media_length
    try:
        _media_length(length)
    except ValueError:
        return None
    return length


def _check_change(document: tla.Document, length: float) -> float:
    """The length to set: a known length can't change once timelines have
    components (FR-056). Then a length less than a millisecond from it is the
    same one, and the known length stays, as the components were checked
    against it. The difference is rounded to the nanosecond first, since
    3.126 - 3.125 computes as a little under 0.001."""
    known = _known_length(document)
    if known is None or not _has_components(document):
        return length
    if round(abs(length - known), 9) < _SAME_LENGTH:
        return known
    raise ValueError(_HAS_COMPONENTS)


def _has_components(document: tla.Document) -> bool:
    for timeline in document.timelines.values():
        if timeline.components:
            return True
        # A kind the core doesn't know keeps its components in `raw`.
        if timeline.raw is not None and timeline.raw.get("components"):
            return True
    return False


def _is_height(value: object) -> bool:
    # True and False are below it too.
    return isinstance(value, numbers.Integral) and value >= _MIN_HEIGHT
