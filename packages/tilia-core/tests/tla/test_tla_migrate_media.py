"""Media paths (FR-003, FR-021, FR-023, FR-033, FR-110; US2 scenarios 8-9).

An old file's media path, and each PDF timeline's path, becomes relative to
the file's folder, starting from where TiLiA would find the media now: the
stored absolute path if it exists on this computer, else its place relative
to the old `file_path`. `tla.media` resolves a document's media. The writer
stores paths relative to the folder it writes into, wherever a relative path
exists, so that the media is still found.

Whether the stored absolute path exists decides the migration's result, as
intended (FR-023): the tests create the media they need in a temporary
folder. Paths of the other system's form (Windows paths read on macOS or
Linux, and the reverse) are never looked up on this computer, so those
cases run on every system."""

import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla.migrate import media as migrate_media

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WINDOWS, reason="drives are Windows'")
posix_only = pytest.mark.skipif(WINDOWS, reason="a POSIX file name")

# Places on another computer, which don't exist on this one.
WINDOWS_SAVED = "C:/Users/someone-176/corpus/piece.tla"
WINDOWS_MEDIA = "C:/Users/someone-176/audio/piece.mp3"
POSIX_SAVED = "/home/someone-176/corpus/piece.tla"
POSIX_MEDIA = "/home/someone-176/audio/piece.mp3"
# Where a file was saved on another computer of this system's kind.
SAVED_HERE = WINDOWS_SAVED if WINDOWS else POSIX_SAVED
# A media path of the other system's form: no relative path to it exists here.
OTHER_SYSTEM_MEDIA = POSIX_MEDIA if WINDOWS else WINDOWS_MEDIA

MISSING = object()


def old_content(where, stored, file_path=MISSING):
    """An old file whose media path (`where` "media") or PDF timeline's path
    (`where` "pdf") is `stored`."""
    content = {
        "app_name": "TiLiA",
        "version": "0.7.0",
        "media_path": stored if where == "media" else "",
        "media_metadata": {"title": "Piece", "notes": "", "media length": 60},
        "timelines": {
            "1": {
                "kind": "Slider",
                "name": "",
                "ordinal": 1,
                "height": 40,
                "is_visible": True,
                "components": {},
            }
        },
    }
    if where == "pdf":
        content["timelines"]["2"] = {
            "kind": "Pdf",
            "name": "Score",
            "ordinal": 2,
            "height": 30,
            "is_visible": True,
            "path": stored,
            "components": {},
        }
    if file_path is not MISSING:
        content["file_path"] = file_path
    return content


def old_file(folder, where, stored, file_path=MISSING):
    """An old file in `folder` (created), as `old_content` gives it."""
    folder.mkdir(parents=True, exist_ok=True)
    piece = folder / "piece.tla"
    piece.write_text(json.dumps(old_content(where, stored, file_path)), "utf-8")
    return piece


def stored_in(doc, where):
    if where == "media":
        return doc.media_path
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    return pdf.attrs["path"]


def media_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    return path


@pytest.fixture(params=["media", "pdf"])
def where(request):
    return request.param


# The migration: what is kept as it is


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "https://www.youtube.com/watch?v=_ORrftU6sGA",
        "youtu.be/_ORrftU6sGA",
        # Without its scheme, as TiLiA's pattern takes it; not a server's share.
        "//www.youtube.com/watch?v=_ORrftU6sGA",
        "https://example.com/audio/piece.mp3",
    ],
)
def test_an_empty_path_or_a_url_is_kept(tmp_path, where, stored):
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


@pytest.mark.parametrize(
    "stored", ["piece.mp3", "audio/piece.mp3", "../audio/piece.mp3", "audio\\piece.mp3"]
)
def test_a_relative_path_written_by_hand_is_kept(tmp_path, where, stored):
    media_file(tmp_path / "audio" / "piece.mp3")
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


@pytest.mark.parametrize("stored", ["C:piece.mp3", "\\audio\\piece.mp3"])
def test_a_path_relative_to_a_drive_or_its_root_is_kept(tmp_path, where, stored):
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


# An absolute path that exists on this computer (US2 scenario 8)


@pytest.mark.parametrize("spelling", [str, Path.as_posix], ids=["system", "slashes"])
@pytest.mark.parametrize(
    "place, expected",
    [
        ("audio/piece.wav", "../audio/piece.wav"),
        ("corpus/piece.wav", "piece.wav"),
        ("corpus/audio/piece.wav", "audio/piece.wav"),
    ],
)
def test_an_absolute_path_that_exists_is_made_relative_from_the_files_folder(
    tmp_path, where, spelling, place, expected
):
    # The file moved without its media, which is still where it was: the old
    # file_path, which names another place, isn't used.
    media = media_file(tmp_path / place)
    piece = old_file(tmp_path / "corpus", where, spelling(media), SAVED_HERE)
    doc = tla.read(piece)
    assert stored_in(doc, where) == expected
    if where == "media":
        assert os.path.samefile(tla.media(piece, doc).path, media)


def test_the_media_is_looked_up_on_every_read(tmp_path, where):
    # The same file gives another document once its media is there (FR-023).
    media = tmp_path / "audio" / "piece.wav"
    piece = old_file(tmp_path / "corpus", where, str(media), SAVED_HERE)
    before = tla.read(piece)
    media_file(media)
    after = tla.read(piece)
    assert stored_in(after, where) == "../audio/piece.wav"
    assert stored_in(before, where) != stored_in(after, where)
    assert before.document_id == after.document_id


@windows_only
def test_media_that_exists_on_another_drive_stays_absolute(tmp_path):
    # The file in a folder on another drive than its media: the folder needn't
    # exist, since only its name is used.
    media = media_file(tmp_path / "audio" / "piece.wav")
    kept = migrate_media.migrated_path(
        str(media), file_path=SAVED_HERE, folder="Z:\\corpus-176"
    )
    assert kept == media.as_posix()


# An absolute path that doesn't exist here: from the old file_path


@pytest.mark.parametrize(
    "file_path, stored, expected",
    [
        (WINDOWS_SAVED, WINDOWS_MEDIA, "../audio/piece.mp3"),
        (
            "C:\\Users\\someone-176\\corpus\\piece.tla",
            "C:\\Users\\someone-176\\audio\\piece.mp3",
            "../audio/piece.mp3",
        ),
        (WINDOWS_SAVED, "C:/Users/someone-176/corpus/piece.mp3", "piece.mp3"),
        (WINDOWS_SAVED, "C:/Users/someone-176/corpus/a/b.mp3", "a/b.mp3"),
        # Windows paths differ in letter case only where they name the same place.
        ("c:/users/SOMEONE-176/Corpus/piece.tla", WINDOWS_MEDIA, "../audio/piece.mp3"),
        (POSIX_SAVED, POSIX_MEDIA, "../audio/piece.mp3"),
        (POSIX_SAVED, "/home/someone-176/corpus/piece.mp3", "piece.mp3"),
        ("/home/someone-176/a/b/c/piece.tla", POSIX_MEDIA, "../../../audio/piece.mp3"),
    ],
)
def test_an_absolute_path_that_doesnt_exist_is_made_relative_from_the_old_file_path(
    tmp_path, where, file_path, stored, expected
):
    piece = old_file(tmp_path / "corpus", where, stored, file_path)
    assert stored_in(tla.read(piece), where) == expected


@pytest.mark.skipif(WINDOWS, reason="Windows would look the server up on the network")
@pytest.mark.parametrize(
    "file_path, stored",
    [
        ("//server-176/share/corpus/piece.tla", "//server-176/share/audio/piece.mp3"),
        (
            "\\\\server-176\\share\\corpus\\piece.tla",
            "\\\\server-176\\share\\audio\\piece.mp3",
        ),
    ],
)
def test_a_path_on_a_windows_server(tmp_path, where, file_path, stored):
    piece = old_file(tmp_path / "corpus", where, stored, file_path)
    assert stored_in(tla.read(piece), where) == "../audio/piece.mp3"


@pytest.mark.parametrize(
    "file_path, stored",
    [(WINDOWS_SAVED, WINDOWS_MEDIA), (POSIX_SAVED, POSIX_MEDIA)],
    ids=["windows", "posix"],
)
def test_a_file_cloned_with_its_media_folder_finds_its_media(
    tmp_path, where, file_path, stored
):
    # US2 scenario 9: on another computer, the stored absolute path doesn't
    # exist, and the file and its media moved together.
    media = media_file(tmp_path / "clone" / "audio" / "piece.mp3")
    piece = old_file(tmp_path / "clone" / "corpus", where, stored, file_path)
    doc = tla.read(piece)
    assert stored_in(doc, where) == "../audio/piece.mp3"
    if where == "media":
        assert os.path.samefile(tla.media(piece, doc).path, media)


@pytest.mark.parametrize(
    "file_path, stored, expected",
    [
        # Another drive than the one the file was saved on.
        (WINDOWS_SAVED, "D:/audio-176/piece.mp3", "D:/audio-176/piece.mp3"),
        (WINDOWS_SAVED, "D:\\audio-176\\piece.mp3", "D:/audio-176/piece.mp3"),
        (
            WINDOWS_SAVED,
            "\\\\server-176\\share\\piece.mp3",
            "//server-176/share/piece.mp3",
        ),
        # A file_path of the other system's form than the media's.
        (POSIX_SAVED, WINDOWS_MEDIA, WINDOWS_MEDIA),
        (WINDOWS_SAVED, POSIX_MEDIA, POSIX_MEDIA),
    ],
)
def test_without_a_relative_path_the_path_stays_absolute_with_slashes(
    tmp_path, where, file_path, stored, expected
):
    if WINDOWS and stored.startswith("\\\\"):
        pytest.skip("Windows would look the server up on the network")
    piece = old_file(tmp_path / "corpus", where, stored, file_path)
    assert stored_in(tla.read(piece), where) == expected


# An old file without a file_path


@pytest.mark.parametrize("file_path", [MISSING, "", None, "piece.tla"])
@pytest.mark.parametrize("exists", [True, False])
def test_without_a_file_path_the_path_is_made_relative_from_the_files_folder(
    tmp_path, where, file_path, exists
):
    # Never saved under that name, or an autosave: whether or not the media
    # is there. A file_path that isn't absolute doesn't say where the file was.
    media = tmp_path / "audio" / "piece.wav"
    if exists:
        media_file(media)
    piece = old_file(tmp_path / "corpus", where, str(media), file_path)
    assert stored_in(tla.read(piece), where) == "../audio/piece.wav"


@posix_only
def test_a_windows_path_isnt_looked_up_on_posix_when_migrated(
    tmp_path, monkeypatch, where
):
    # On macOS and Linux, "C:/…" is a relative path: below the working folder.
    monkeypatch.chdir(tmp_path)
    media_file(tmp_path / WINDOWS_MEDIA)
    piece = old_file(tmp_path / "corpus", where, WINDOWS_MEDIA, POSIX_SAVED)
    assert stored_in(tla.read(piece), where) == WINDOWS_MEDIA


def test_without_a_file_path_a_path_of_the_other_system_stays_absolute(tmp_path, where):
    piece = old_file(tmp_path / "corpus", where, OTHER_SYSTEM_MEDIA, "")
    assert stored_in(tla.read(piece), where) == OTHER_SYSTEM_MEDIA


# Bytes read without the file's place


def test_bytes_without_a_place_keep_media_that_exists_absolute(tmp_path, where):
    # Where TiLiA would find it, and nothing to make it relative from.
    media = media_file(tmp_path / "audio" / "piece.wav")
    data = json.dumps(old_content(where, str(media), SAVED_HERE)).encode()
    assert stored_in(tla.loads(data), where) == media.as_posix()


def test_bytes_without_a_place_make_the_path_relative_from_the_old_file_path(where):
    data = json.dumps(old_content(where, WINDOWS_MEDIA, WINDOWS_SAVED)).encode()
    assert stored_in(tla.loads(data), where) == "../audio/piece.mp3"


def test_bytes_without_a_place_or_a_file_path_keep_the_path(where):
    data = json.dumps(old_content(where, WINDOWS_MEDIA, "")).encode()
    assert stored_in(tla.loads(data), where) == WINDOWS_MEDIA


# The rest of the file


def test_the_relative_path_is_in_nfc(tmp_path, where):
    stored = unicodedata.normalize(
        "NFD", "C:/Users/someone-176/Ständchen/Ständchen.mp3"
    )
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == "../Ständchen/Ständchen.mp3"


def test_the_ids_dont_depend_on_the_path_made_relative(tmp_path, where):
    # The document id is derived before the paths are made relative, which
    # depend on where the file is (contracts/migration.md, *Ids*).
    stored = WINDOWS_MEDIA if WINDOWS else POSIX_MEDIA
    data = json.dumps(old_content(where, stored, "")).encode()
    here = tmp_path / "here" / "piece.tla"
    elsewhere = tmp_path / "elsewhere" / "deeper" / "piece.tla"
    docs = [
        tla.loads(data, path=here),
        tla.loads(data, path=elsewhere),
        tla.loads(data),
    ]
    assert len({stored_in(doc, where) for doc in docs}) == 3
    assert len({doc.document_id for doc in docs}) == 1


def test_a_timeline_of_a_kind_the_core_doesnt_know_keeps_its_path(tmp_path):
    content = old_content("media", "", WINDOWS_SAVED)
    content["timelines"]["2"] = {
        "kind": "Pdfs",
        "name": "Other",
        "ordinal": 2,
        "path": WINDOWS_MEDIA,
        "components": {},
    }
    piece = tmp_path / "piece.tla"
    piece.write_text(json.dumps(content), "utf-8")
    (unknown,) = [tl for tl in tla.read(piece).timelines.values() if tl.raw]
    assert unknown.raw["path"] == WINDOWS_MEDIA


# tla.media


def test_no_media(tmp_path):
    found = tla.media(tmp_path / "piece.tla", tla.new_document())
    assert found == tla.Media(
        kind="none", stored="", path=None, youtube_id=None, length=None
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=_ORrftU6sGA",
        "https://youtu.be/_ORrftU6sGA",
        "youtube.com/embed/_ORrftU6sGA",
        "https://m.youtube.com/watch?v=_ORrftU6sGA&t=10s",
    ],
)
def test_a_youtube_link(tmp_path, url):
    doc = tla.new_document()
    doc.media_path, doc.media_length = url, 245.5
    found = tla.media(tmp_path / "piece.tla", doc)
    assert found == tla.Media(
        kind="youtube", stored=url, path=None, youtube_id="_ORrftU6sGA", length=245.5
    )


@pytest.mark.parametrize(
    "stored, place",
    [
        ("piece.wav", "corpus/piece.wav"),
        ("audio/piece.wav", "corpus/audio/piece.wav"),
        ("../audio/piece.wav", "audio/piece.wav"),
    ],
)
def test_a_relative_path_is_resolved_against_the_files_folder(
    tmp_path, monkeypatch, stored, place
):
    monkeypatch.chdir(tmp_path)  # not against the working folder
    media = media_file(tmp_path / place)
    doc = tla.new_document()
    doc.media_path, doc.media_length = stored, 12.0
    found = tla.media(tmp_path / "corpus" / "piece.tla", doc)
    assert (found.kind, found.stored, found.youtube_id, found.length) == (
        "local",
        stored,
        None,
        12.0,
    )
    assert found.path.is_absolute()
    assert os.path.samefile(found.path, media)


def test_an_absolute_path_is_taken_as_it_is(tmp_path):
    media = media_file(tmp_path / "audio" / "piece.wav")
    doc = tla.new_document()
    doc.media_path = media.as_posix()
    found = tla.media(tmp_path / "elsewhere" / "piece.tla", doc)
    assert found.kind == "local"
    assert os.path.samefile(found.path, media)


@pytest.mark.parametrize("stored", ["audio/piece.wav", "audio", WINDOWS_MEDIA])
def test_local_media_not_found(tmp_path, stored):
    (tmp_path / "corpus" / "audio").mkdir(parents=True)  # a folder isn't media
    doc = tla.new_document()
    doc.media_path = stored
    found = tla.media(tmp_path / "corpus" / "piece.tla", doc)
    assert (found.kind, found.stored, found.path) == ("local", stored, None)


@posix_only
def test_a_windows_path_isnt_looked_up_on_posix(tmp_path):
    # On macOS and Linux, "C:/…" is a relative path: below the file's folder.
    media_file(tmp_path / "corpus" / "C:" / "audio" / "piece.wav")
    doc = tla.new_document()
    doc.media_path = "C:/audio/piece.wav"
    assert tla.media(tmp_path / "corpus" / "piece.tla", doc).path is None


NAME = "Ständchen"


@pytest.mark.parametrize(
    "on_disk",
    [
        f"audio/{unicodedata.normalize('NFD', NAME)}.wav",
        unicodedata.normalize("NFD", f"{NAME}/{NAME}.wav"),
    ],
    ids=["name", "folder and name"],
)
def test_a_name_in_decomposed_form_is_found(tmp_path, on_disk):
    # Named on macOS's older file system, then copied elsewhere; the file
    # stores text in NFC.
    media = media_file(tmp_path / on_disk)
    stored = unicodedata.normalize("NFC", on_disk)
    doc = tla.new_document()
    doc.media_path = stored
    found = tla.media(tmp_path / "piece.tla", doc)
    assert found.stored == stored
    assert os.path.samefile(found.path, media)
