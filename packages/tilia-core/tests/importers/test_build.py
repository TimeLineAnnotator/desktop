"""`tilia_core.build`: a script's new document, its fields, its media and its
timelines (spec FR-050–FR-052, FR-054–FR-056, FR-060; User Story 6)."""

import copy
import json
import math
import struct
import wave
from pathlib import Path

import pytest
from import_docs import component, document, timeline

from tilia_core import build, tla

# TiLiA's texts (tilia/errors.py and its command line), word for word.
CANT_SET_MEDIA_LENGTH = (
    "Cannot set media length with 'metadata set'."
    " Use 'metadata set-media-length' instead."
)
NOT_A_MEDIA_LENGTH = (
    "Cannot set media metadata to {}. Media length must be a positive number."
)
MEDIA_LOADED = "Can't change media length when a media file is loaded."
MEDIA_NOT_FOUND = "No media available at '{}'. Try using another path."
NO_DURATION = (
    "No media loaded and no duration set. Load a media file with 'load-media'"
    " or set a duration with 'metadata set-media-length'."
)
NOT_APPLICABLE = "'{}' is not valid for timeline kind '{}'."
# The spec's texts, where TiLiA has none.
HAS_COMPONENTS = (
    "The media length can't change once timelines have components:"
    " rescale the file in TiLiA."
)
NO_LENGTH = (
    "{}: give its length with --duration-if-error,"
    " or set it first with metadata set-media-length"
)

YOUTUBE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def refused(call, *args, **kwargs) -> str:
    with pytest.raises(ValueError) as error:
        call(*args, **kwargs)
    return str(error.value)


def stored(path: Path) -> str:
    """A local media path as `load_media` stores it: absolute, with "/"."""
    return str(path.resolve()).replace("\\", "/")


# WAVs, written in the test


def pcm16_wav(path: Path, *, rate: int, channels: int, frames: int) -> Path:
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b"\0\0" * channels * frames)
    return path


def chunk(name: bytes, data: bytes, *, size: int | None = None) -> bytes:
    """A RIFF chunk, with its pad byte when its size is odd."""
    header = name + struct.pack("<I", len(data) if size is None else size)
    return header + data + (b"\0" if len(data) % 2 else b"")


def riff(*chunks: bytes) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def fmt(tag: int, *, channels: int, rate: int, bits: int, extra: bytes = b"") -> bytes:
    align = channels * bits // 8
    head = struct.pack("<HHIIHH", tag, channels, rate, rate * align, align, bits)
    return chunk(b"fmt ", head + extra)


def float32_wav(path: Path, *, rate: int, channels: int, frames: int) -> Path:
    """IEEE float (format 3), with the `fact` chunk such files carry."""
    path.write_bytes(
        riff(
            fmt(3, channels=channels, rate=rate, bits=32, extra=struct.pack("<H", 0)),
            chunk(b"fact", struct.pack("<I", frames)),
            chunk(b"data", bytes(4 * channels * frames)),
        )
    )
    return path


# KSDATAFORMAT_SUBTYPE_PCM
_PCM_GUID = struct.pack("<IHH", 1, 0, 0x10) + bytes.fromhex("800000aa00389b71")


def extensible_wav(path: Path, *, rate: int, channels: int, frames: int) -> Path:
    """WAVE_FORMAT_EXTENSIBLE, 24-bit, with an odd-sized chunk before the data."""
    extension = struct.pack("<HHI", 22, 24, 0b111) + _PCM_GUID
    path.write_bytes(
        riff(
            fmt(0xFFFE, channels=channels, rate=rate, bits=24, extra=extension),
            chunk(b"LIST", b"INFO!"),
            chunk(b"data", bytes(3 * channels * frames)),
        )
    )
    return path


# A new document (FR-054)


def test_a_new_document_has_title_and_notes_and_no_other_field():
    # US6 scenario 6.
    doc = build.new_script_document()

    assert list(doc.metadata.items()) == [("title", "Untitled"), ("notes", "")]
    assert doc.media_path == ""
    assert doc.media_length is None
    assert doc.timelines == {}
    assert doc.format_version == tla.FORMAT_VERSION


def test_a_new_document_saved_without_fields_has_only_title_and_notes():
    # US6 scenario 6, in the file's bytes.
    written = json.loads(tla.canonical_bytes(build.new_script_document()))

    assert written["metadata"] == {"title": "Untitled", "notes": ""}
    assert list(written["metadata"]) == ["title", "notes"]


def test_each_new_document_has_its_own_id_and_fields():
    first, second = build.new_script_document(), build.new_script_document()
    build.set_field(first, "composer", "Mozart")

    assert first.document_id != second.document_id
    assert "composer" not in second.metadata


# Fields (FR-050)


def test_a_field_is_added_at_the_end():
    # US6 scenario 1.
    doc = build.new_script_document()

    build.set_field(doc, "composer", "W. A. Mozart")

    assert list(doc.metadata.items()) == [
        ("title", "Untitled"),
        ("notes", ""),
        ("composer", "W. A. Mozart"),
    ]


def test_a_field_that_exists_is_set_where_it_is():
    doc = build.new_script_document()
    build.set_field(doc, "composer", "Mozart")

    build.set_field(doc, "title", "Piano Sonata K. 279")

    assert list(doc.metadata.items()) == [
        ("title", "Piano Sonata K. 279"),
        ("notes", ""),
        ("composer", "Mozart"),
    ]


def test_a_field_is_stored_in_nfc():
    doc = build.new_script_document()

    build.set_field(doc, "compositeur", "Dvořák")

    assert doc.metadata["compositeur"] == "Dvořák"


@pytest.mark.parametrize("name", ["media length", "Media Length", "MEDIA LENGTH"])
def test_media_length_isnt_a_field(name):
    # US6 scenario 2.
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    assert refused(build.set_field, doc, name, "120") == CANT_SET_MEDIA_LENGTH
    assert doc == before


# The media length (FR-051, FR-056)


def test_set_media_length():
    # US6 scenario 3.
    doc = build.new_script_document()

    build.set_media_length(doc, 312.5)

    assert doc.media_length == 312.5


def test_a_whole_number_is_stored_as_seconds():
    doc = build.new_script_document()

    build.set_media_length(doc, 120)

    assert doc.media_length == 120.0
    assert isinstance(doc.media_length, float)


@pytest.mark.parametrize(
    "value", [0, 0.0, -1, -312.5, "312.5", "abc", None, True, math.nan, math.inf]
)
def test_a_media_length_must_be_a_positive_number(value):
    # US6 scenario 3: zero, a negative number or text fails. NaN and infinity
    # too: a file can't hold them.
    doc = build.new_script_document()
    build.set_media_length(doc, 60.0)
    before = copy.deepcopy(doc)

    assert refused(build.set_media_length, doc, value) == NOT_A_MEDIA_LENGTH.format(
        value
    )
    assert doc == before


def test_the_media_length_cant_be_set_while_media_is_attached(tmp_path):
    # US6 scenario 8; FR-051.
    doc = build.new_script_document()
    build.load_media(
        doc, pcm16_wav(tmp_path / "a.wav", rate=8000, channels=1, frames=12000)
    )
    before = copy.deepcopy(doc)

    assert refused(build.set_media_length, doc, 300) == MEDIA_LOADED
    assert doc == before
    assert doc.media_length == 1.5


def test_the_same_length_is_refused_too_while_media_is_attached(tmp_path):
    doc = build.new_script_document()
    build.load_media(
        doc, pcm16_wav(tmp_path / "a.wav", rate=8000, channels=1, frames=12000)
    )

    assert refused(build.set_media_length, doc, 1.5) == MEDIA_LOADED


def test_a_media_length_attached_by_an_opened_file_counts_as_media():
    doc = document(media_length=60.0)
    doc.media_path = "recording.mp3"

    assert refused(build.set_media_length, doc, 30.0) == MEDIA_LOADED


def with_a_marker(media_length):
    marker = timeline("marker", components=[component("marker", time=1.0)])
    return document(media_length=media_length, timelines=[marker])


def test_a_known_length_cant_change_once_timelines_have_components():
    # FR-056.
    doc = with_a_marker(60.0)
    before = copy.deepcopy(doc)

    assert refused(build.set_media_length, doc, 30.0) == HAS_COMPONENTS
    assert doc == before


def test_setting_the_same_length_again_isnt_a_change():
    doc = with_a_marker(60.0)

    build.set_media_length(doc, 60.0)

    assert doc.media_length == 60.0


def test_a_first_length_is_set_although_timelines_have_components():
    doc = with_a_marker(None)

    build.set_media_length(doc, 30.0)

    assert doc.media_length == 30.0


def test_a_known_length_changes_while_no_timeline_has_components():
    doc = document(media_length=60.0, timelines=[timeline("marker")])

    build.set_media_length(doc, 30.0)

    assert doc.media_length == 30.0


def test_components_of_a_kind_the_core_doesnt_know_count():
    raw = {"kind": "Lyrics", "ordinal": 1, "components": {"a": {"time": 1.0}}}
    unknown = tla.Timeline(
        id=tla.new_id(), kind=tla.UnknownKind("Lyrics"), ordinal=1, raw=raw
    )
    doc = document(media_length=60.0, timelines=[unknown])

    assert refused(build.set_media_length, doc, 30.0) == HAS_COMPONENTS


# A WAV's length (research R8)


def test_wav_length_of_16_bit_pcm(tmp_path):
    path = pcm16_wav(tmp_path / "a.wav", rate=8000, channels=2, frames=12000)

    assert build.wav_length(path) == 1.5


def test_wav_length_of_32_bit_float(tmp_path):
    # Python's wave module refuses these.
    path = float32_wav(tmp_path / "a.wav", rate=44100, channels=2, frames=22050)

    assert build.wav_length(path) == 0.5


def test_wav_length_of_wave_format_extensible(tmp_path):
    # Python's wave module refuses these before 3.12.
    path = extensible_wav(tmp_path / "a.wav", rate=48000, channels=3, frames=72000)

    assert build.wav_length(path) == 1.5


def test_without_a_byte_rate_block_align_times_sample_rate_is_used(tmp_path):
    path = tmp_path / "a.wav"
    no_byte_rate = struct.pack("<HHIIHH", 1, 2, 8000, 0, 4, 16)
    path.write_bytes(riff(chunk(b"fmt ", no_byte_rate), chunk(b"data", bytes(16000))))

    assert build.wav_length(path) == 0.5


def test_a_data_size_beyond_the_file_counts_the_bytes_there(tmp_path):
    # A WAV written as a stream gives its data size as 0xFFFFFFFF.
    path = tmp_path / "a.wav"
    path.write_bytes(
        riff(
            fmt(1, channels=1, rate=8000, bits=16),
            chunk(b"data", bytes(16000), size=0xFFFFFFFF),
        )
    )

    assert build.wav_length(path) == 1.0


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not a WAV at all",
        b"RIFF\x00\x00\x00\x00WAVE",  # no chunks
        # A WAV's chunks in another RIFF form, and in big-endian RIFX
        riff(
            fmt(1, channels=1, rate=8000, bits=16), chunk(b"data", bytes(100))
        ).replace(b"WAVE", b"AVI ", 1),
        b"RIFX"
        + riff(fmt(1, channels=1, rate=8000, bits=16), chunk(b"data", bytes(100)))[4:],
        riff(chunk(b"data", bytes(100))),  # no fmt
        riff(fmt(1, channels=1, rate=8000, bits=16)),  # no data
        riff(fmt(1, channels=1, rate=8000, bits=16))[:30],  # cut inside fmt
        riff(fmt(1, channels=0, rate=0, bits=16), chunk(b"data", bytes(100))),
        riff(fmt(1, channels=1, rate=8000, bits=16), chunk(b"data", b"")),  # empty
    ],
)
def test_wav_length_is_none_without_a_header_it_can_read(tmp_path, content):
    path = tmp_path / "a.wav"
    path.write_bytes(content)

    assert build.wav_length(path) is None


def test_wav_length_of_a_missing_file_is_none(tmp_path):
    assert build.wav_length(tmp_path / "missing.wav") is None


# Loading media (FR-052, FR-056)


def test_load_media_records_a_wav_and_its_length(tmp_path):
    # US6 scenario 4. The writer stores the path relative to the saved file
    # (WP3's FR-033); the document keeps it absolute.
    path = pcm16_wav(tmp_path / "recording.wav", rate=8000, channels=1, frames=12000)
    doc = build.new_script_document()

    assert build.load_media(doc, str(path)) == 1.5
    assert doc.media_path == stored(path)
    assert doc.media_length == 1.5


def test_load_media_resolves_a_relative_path(tmp_path, monkeypatch):
    pcm16_wav(tmp_path / "recording.wav", rate=8000, channels=1, frames=8000)
    monkeypatch.chdir(tmp_path)
    doc = build.new_script_document()

    build.load_media(doc, "recording.wav")

    assert doc.media_path == stored(tmp_path / "recording.wav")
    assert Path(doc.media_path).is_absolute()


def test_a_wav_is_known_by_its_extension_in_any_case(tmp_path):
    path = pcm16_wav(tmp_path / "RECORDING.WAV", rate=8000, channels=1, frames=4000)
    doc = build.new_script_document()

    assert build.load_media(doc, path) == 0.5


def test_a_wavs_length_wins_over_duration_if_error(tmp_path):
    path = pcm16_wav(tmp_path / "a.wav", rate=8000, channels=1, frames=12000)
    doc = build.new_script_document()

    assert build.load_media(doc, path, duration_if_error=300.0) == 1.5


def test_media_whose_length_cant_be_read_needs_a_length(tmp_path):
    # US6 scenario 5.
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"ID3")
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    assert refused(build.load_media, doc, path) == NO_LENGTH.format("recording.mp3")
    assert doc == before


def test_duration_if_error_gives_the_length(tmp_path):
    # US6 scenario 5.
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"ID3")
    doc = build.new_script_document()

    assert build.load_media(doc, path, duration_if_error=312.5) == 312.5
    assert doc.media_path == stored(path)
    assert doc.media_length == 312.5


def test_a_length_set_earlier_is_kept(tmp_path):
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"ID3")
    doc = build.new_script_document()
    build.set_media_length(doc, 1043.0)

    assert build.load_media(doc, path) == 1043.0
    assert doc.media_path == stored(path)


def test_a_wav_that_cant_be_read_falls_back_like_any_media(tmp_path):
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a WAV")
    doc = build.new_script_document()

    assert refused(build.load_media, doc, path) == NO_LENGTH.format("broken.wav")
    assert build.load_media(doc, path, duration_if_error=12.0) == 12.0


def test_the_length_of_media_already_attached_isnt_taken_for_new_media(tmp_path):
    # FR-052: the length comes from --duration-if-error or an earlier
    # set-media-length; with media attached, it came with that media (FR-051).
    wav = pcm16_wav(tmp_path / "a.wav", rate=8000, channels=1, frames=12000)
    mp3 = tmp_path / "b.mp3"
    mp3.write_bytes(b"ID3")
    doc = build.new_script_document()
    build.load_media(doc, wav)
    before = copy.deepcopy(doc)

    assert refused(build.load_media, doc, mp3) == NO_LENGTH.format("b.mp3")
    assert doc == before


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_duration_if_error_is_checked_as_a_media_length(tmp_path, value):
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"ID3")
    doc = build.new_script_document()

    message = refused(build.load_media, doc, path, duration_if_error=value)

    assert message == NOT_A_MEDIA_LENGTH.format(value)
    assert doc.media_path == ""


def test_media_that_doesnt_exist_is_refused(tmp_path):
    path = tmp_path / "missing.wav"
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    message = refused(build.load_media, doc, str(path), duration_if_error=10.0)

    assert message == MEDIA_NOT_FOUND.format(Path(str(path).replace("\\", "/")))
    assert doc == before


def test_a_youtube_link_is_recorded_as_it_is():
    doc = build.new_script_document()

    assert build.load_media(doc, YOUTUBE, duration_if_error=212.0) == 212.0
    assert doc.media_path == YOUTUBE
    assert doc.media_length == 212.0


def test_a_youtube_link_needs_a_length():
    doc = build.new_script_document()

    assert refused(build.load_media, doc, YOUTUBE) == NO_LENGTH.format(YOUTUBE)
    assert doc.media_path == ""


def test_a_youtube_link_takes_a_length_set_earlier():
    doc = build.new_script_document()
    build.set_media_length(doc, 212.0)

    assert build.load_media(doc, "https://youtu.be/dQw4w9WgXcQ") == 212.0


def test_media_of_another_length_is_refused_once_timelines_have_components(tmp_path):
    # FR-056.
    doc = with_a_marker(60.0)
    doc.media_path = "a.mp3"
    before = copy.deepcopy(doc)
    wav = pcm16_wav(tmp_path / "b.wav", rate=8000, channels=1, frames=12000)

    assert refused(build.load_media, doc, wav) == HAS_COMPONENTS
    assert refused(build.load_media, doc, YOUTUBE, duration_if_error=30.0) == (
        HAS_COMPONENTS
    )
    assert doc == before


def test_media_of_the_same_length_is_loaded_although_timelines_have_components(
    tmp_path,
):
    doc = with_a_marker(1.5)
    wav = pcm16_wav(tmp_path / "b.wav", rate=8000, channels=1, frames=12000)

    build.load_media(doc, wav)

    assert doc.media_path == stored(wav)
    assert doc.media_length == 1.5


def test_media_with_a_first_length_is_loaded_although_timelines_have_components(
    tmp_path,
):
    doc = with_a_marker(None)
    wav = pcm16_wav(tmp_path / "b.wav", rate=8000, channels=1, frames=12000)

    build.load_media(doc, wav)

    assert doc.media_length == 1.5


# Adding timelines (FR-055, FR-060)


def script_document(media_length=60.0):
    doc = build.new_script_document()
    build.set_media_length(doc, media_length)
    return doc


@pytest.mark.parametrize(
    "kind, height", [("marker", 30), ("hierarchy", 120), ("beat", 69)]
)
def test_a_timeline_without_a_height_gets_tilias_default(kind, height):
    # #254: TiLiA's out-of-the-box defaults, fixed in the core; beat is 35 and
    # 34 for the time signatures' band.
    doc = script_document()

    timeline_id = build.add_timeline(doc, kind, "Name")

    assert doc.timelines[timeline_id].attrs["height"] == height


@pytest.mark.parametrize("kind", ["marker", "hierarchy", "beat"])
def test_a_timeline_gets_the_height_given(kind):
    # A beat timeline's band isn't added to a height given, as in TiLiA.
    doc = script_document()

    timeline_id = build.add_timeline(doc, kind, height=50)

    assert doc.timelines[timeline_id].attrs["height"] == 50


def test_a_harmony_timeline_has_no_height():
    doc = script_document()

    timeline_id = build.add_timeline(doc, "harmony", "Chords")

    assert "height" not in doc.timelines[timeline_id].attrs


def test_a_timeline_is_added_empty_with_its_kind_and_name():
    doc = script_document()

    timeline_id = build.add_timeline(doc, "hierarchy", "Phrases")

    added = doc.timelines[timeline_id]
    assert added.id == timeline_id
    assert added.kind == "hierarchy"
    assert added.name == "Phrases"
    assert added.components == {}
    assert added.metadata == {}


def test_a_timelines_name_is_stored_in_nfc():
    doc = script_document()

    timeline_id = build.add_timeline(doc, "marker", "Cadéncias")

    assert doc.timelines[timeline_id].name == "Cadéncias"


def test_timelines_are_added_after_the_others():
    doc = document(
        media_length=60.0,
        timelines=[timeline("marker", ordinal=1), timeline("marker", ordinal=5)],
    )

    first = build.add_timeline(doc, "marker")
    second = build.add_timeline(doc, "beat")

    assert doc.timelines[first].ordinal == 6
    assert doc.timelines[second].ordinal == 7
    assert first != second


def test_the_first_timeline_has_ordinal_1():
    doc = script_document()

    assert doc.timelines[build.add_timeline(doc, "marker")].ordinal == 1


def test_a_beat_timeline_shows_time_signatures_with_pattern_4():
    doc = script_document()

    beat = doc.timelines[build.add_timeline(doc, "beat", "Measures")]

    assert beat.attrs["show_time_signatures"] is True
    assert beat.attrs["beat_pattern"] == "4"


def test_a_beat_pattern_is_stored_as_given():
    doc = script_document()

    timeline_id = build.add_timeline(doc, "beat", beat_pattern="10[4] 3")

    assert doc.timelines[timeline_id].attrs["beat_pattern"] == "10[4] 3"


def test_a_built_document_reads_back_as_it_was():
    # The file always holds a height (WP3's layout), and reading the file
    # gives what was built.
    doc = script_document(312.5)
    build.set_field(doc, "composer", "W. A. Mozart")
    for kind, name in [
        ("beat", "Measures"),
        ("harmony", "Chords"),
        ("hierarchy", "Phrases"),
        ("marker", "Cadences"),
    ]:
        build.add_timeline(doc, kind, name)

    data = tla.canonical_bytes(doc)
    back = tla.loads(data)

    assert back.metadata == doc.metadata
    assert back.media_length == 312.5
    for timeline_id, built in doc.timelines.items():
        read = back.timelines[timeline_id]
        assert (read.kind, read.name, read.ordinal) == (
            built.kind,
            built.name,
            built.ordinal,
        )
        assert read.attrs == built.attrs
    heights = {
        written["name"]: written.get("height")
        for written in json.loads(data)["timelines"].values()
    }
    assert heights == {"Measures": 69, "Chords": None, "Phrases": 120, "Cadences": 30}


def test_no_timeline_until_the_media_length_is_known():
    # FR-055: checked first, as TiLiA does.
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    assert refused(build.add_timeline, doc, "marker") == NO_DURATION
    assert refused(build.add_timeline, doc, "harmony", height=40) == NO_DURATION
    assert doc == before


def test_a_harmony_timeline_takes_no_height():
    doc = script_document()
    before = copy.deepcopy(doc)

    message = refused(build.add_timeline, doc, "harmony", height=40)

    assert message == NOT_APPLICABLE.format("--height", "harmony")
    assert doc == before


@pytest.mark.parametrize("kind", ["marker", "hierarchy", "harmony"])
def test_only_a_beat_timeline_takes_a_beat_pattern(kind):
    doc = script_document()
    before = copy.deepcopy(doc)

    message = refused(build.add_timeline, doc, kind, beat_pattern="4")

    assert message == NOT_APPLICABLE.format("--beat-pattern", kind)
    assert doc == before


@pytest.mark.parametrize(
    "pattern, reason",
    [
        ("10[", "Unclosed '['."),
        ("0", "Bar lengths must be at least 1."),
        ("4 x", "Unexpected 'x'."),
        ("", "Enter at least one bar length."),
    ],
)
def test_a_beat_pattern_that_doesnt_parse_is_refused(pattern, reason):
    doc = script_document()
    before = copy.deepcopy(doc)

    message = refused(build.add_timeline, doc, "beat", beat_pattern=pattern)

    assert message == f"Invalid beat pattern '{pattern}': {reason}"
    assert doc == before


@pytest.mark.parametrize("height", [0, -5, 9, 10.0, True, "40"])
def test_a_height_is_an_integer_of_at_least_10(height):
    # TiLiA's set_data refuses these (validate_bounded_integer, lower=10), and
    # the strictest of TiLiA's checks applies (TimeLineAnnotator/project-management#316).
    doc = script_document()
    before = copy.deepcopy(doc)

    message = refused(build.add_timeline, doc, "marker", height=height)

    assert message == f"{height} is not a valid height."
    assert doc == before


def test_a_height_of_10_is_kept():
    doc = script_document()

    timeline_id = build.add_timeline(doc, "marker", height=10)

    assert doc.timelines[timeline_id].attrs["height"] == 10


@pytest.mark.parametrize("kind", ["range", "pdf", "score", "slider", "Marker"])
def test_other_kinds_are_refused(kind):
    doc = script_document()
    before = copy.deepcopy(doc)

    message = refused(build.add_timeline, doc, kind)

    assert repr(kind) in message
    assert doc == before


# Finding timelines


def test_a_timeline_is_found_by_name():
    chords = timeline("harmony", name="Chords", ordinal=2)
    doc = document(timelines=[timeline("beat", name="Measures"), chords])

    assert build.find_timeline(doc, name="Chords") == chords.id


def test_of_two_timelines_with_one_name_the_first_by_ordinal_is_found():
    second = timeline("marker", name="Same", ordinal=2)
    first = timeline("marker", name="Same", ordinal=1)
    doc = document(timelines=[second, first])

    assert build.find_timeline(doc, name="Same") == first.id


def test_a_name_is_compared_in_nfc():
    found = timeline("marker", name="Cadéncias")
    doc = document(timelines=[found])

    assert build.find_timeline(doc, name="Cadéncias") == found.id


def test_a_timeline_is_found_by_ordinal():
    third = timeline("marker", ordinal=3)
    doc = document(timelines=[timeline("marker", ordinal=1), third])

    assert build.find_timeline(doc, ordinal=3) == third.id


def test_an_ordinal_is_used_before_a_name():
    # As TiLiA's command line finds an import's target.
    by_name = timeline("marker", name="A", ordinal=1)
    by_ordinal = timeline("marker", name="B", ordinal=2)
    doc = document(timelines=[by_name, by_ordinal])

    assert build.find_timeline(doc, name="A", ordinal=2) == by_ordinal.id


def test_no_timeline_found():
    doc = document(timelines=[timeline("marker", name="A", ordinal=1)])

    assert refused(build.find_timeline, doc, name="B") == (
        "No timeline found with name='B'"
    )
    assert refused(build.find_timeline, doc, ordinal=2) == (
        "No timeline found with ordinal=2"
    )


def test_find_timeline_needs_a_name_or_an_ordinal():
    with pytest.raises(TypeError):
        build.find_timeline(document())
