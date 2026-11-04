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

import dataclasses
import errno
import hashlib
import importlib
import inspect
import itertools
import json
import os
import posixpath
import shutil
import stat
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from tilia_core import tla
from tilia_core.commands import migrate as migrate_command
from tilia_core.tla import folder as folder_module
from tilia_core.tla import writer
from tilia_core.tla.migrate import media as migrate_media

EVERY_KIND = Path(__file__).parent / "golden" / "every-kind.tla"
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
# What an old link without its scheme becomes.
YOUTUBE_LINK = "https://youtu.be/_ORrftU6sGA"
OTHER_SYSTEM_SAVED = POSIX_SAVED if WINDOWS else WINDOWS_SAVED

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


@pytest.fixture
def servers(monkeypatch):
    """Lookups of a Windows server path (`//server/share/…`), which Windows
    would make on the network: each is recorded, with "/", and finds a file
    only where `there`, a set of such paths, says. Other paths are looked up
    as they are."""
    looked_up = []
    there = set()
    real = {"isfile": os.path.isfile, "exists": os.path.exists}

    def stub(name):
        def lookup(path):
            text = os.fspath(path).replace("\\", "/")
            if not text.startswith("//"):
                return real[name](path)
            looked_up.append(text)
            return text in there

        return lookup

    for name in real:
        monkeypatch.setattr(os.path, name, stub(name))
    return SimpleNamespace(looked_up=looked_up, there=there)


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "https://www.youtube.com/watch?v=_ORrftU6sGA",
        "http://youtu.be/_ORrftU6sGA",
        "https://example.com/audio/piece.mp3",
    ],
)
def test_an_empty_path_or_a_url_is_kept(tmp_path, where, stored):
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


@pytest.mark.parametrize(
    "stored",
    [
        "youtu.be/_ORrftU6sGA",
        "www.youtube.com/watch?v=_ORrftU6sGA",
        "youtube.com/embed/_ORrftU6sGA",
    ],
)
def test_an_old_youtube_link_without_a_scheme_gets_https(tmp_path, stored):
    # TiLiA stored a link as it was typed; a media path is a URL only with a
    # scheme (FR-033). TiLiA stored local media as absolute paths,
    # which never match its pattern.
    piece = old_file(tmp_path / "corpus", "media", stored, WINDOWS_SAVED)
    doc = tla.read(piece)
    assert doc.media_path == f"https://{stored}"
    found = tla.media(piece, doc)
    assert (found.kind, found.youtube_id) == ("youtube", "_ORrftU6sGA")


def test_a_pdf_path_like_a_youtube_link_gets_no_scheme(tmp_path):
    # Only the media's path can be a link.
    piece = old_file(tmp_path / "corpus", "pdf", "youtu.be/score.pdf", WINDOWS_SAVED)
    assert stored_in(tla.read(piece), "pdf") == "youtu.be/score.pdf"


def test_an_old_youtube_link_starting_with_two_slashes_gets_https(tmp_path, servers):
    # Only a scheme makes a URL, and a path that starts with "//" is a server
    # path; TiLiA stored this link as it was typed, without its "https:"
    # (FR-033). It is given one before any lookup, so it is never looked for on
    # a server.
    stored = "//www.youtube.com/watch?v=_ORrftU6sGA"
    piece = old_file(tmp_path / "corpus", "media", stored, WINDOWS_SAVED)
    doc = tla.read(piece)
    assert doc.media_path == f"https:{stored}"
    assert servers.looked_up == []
    found = tla.media(piece, doc)
    assert (found.kind, found.youtube_id) == ("youtube", "_ORrftU6sGA")


def test_an_old_pdf_path_starting_with_two_slashes_is_a_server_path(tmp_path, servers):
    # Even one that looks like a link: only the media's path can be one.
    saved = "//www.youtube.com/share/corpus/piece.tla"
    stored = "//www.youtube.com/share/scores/piece.pdf"
    piece = old_file(tmp_path / "corpus", "pdf", stored, saved)
    assert stored_in(tla.read(piece), "pdf") == "../scores/piece.pdf"


@pytest.mark.parametrize(
    "stored, linked",
    [
        ("youtu.be/_ORrftU6sGA", YOUTUBE_LINK),
        (
            "//www.youtube.com/watch?v=_ORrftU6sGA",
            "https://www.youtube.com/watch?v=_ORrftU6sGA",
        ),
    ],
)
def test_the_document_id_is_derived_from_the_link_as_stored(tmp_path, stored, linked):
    # Before the migration gives it its scheme (contracts/migration.md, *Ids*):
    # a file that stored the link with "https://" is another file.
    without = old_file(tmp_path / "without", "media", stored, WINDOWS_SAVED)
    with_scheme = old_file(tmp_path / "with", "media", linked, WINDOWS_SAVED)
    docs = tla.read(without), tla.read(with_scheme)
    assert [doc.media_path for doc in docs] == [linked, linked]
    assert docs[0].document_id != docs[1].document_id


def test_an_old_files_fingerprint_takes_the_link_as_stored(tmp_path):
    # As its other paths, not with the scheme the migration gives it (FR-043).
    piece = old_file(tmp_path / "corpus", "media", "youtu.be/_ORrftU6sGA", "")
    as_stored = tla.read(piece)
    assert as_stored.media_path == YOUTUBE_LINK
    as_stored.media_path = "youtu.be/_ORrftU6sGA"
    assert tla.fingerprint(piece) == tla.fingerprint_of(as_stored)


@pytest.mark.parametrize(
    "stored",
    [
        "piece.mp3",
        "audio/piece.mp3",
        "../audio/piece.mp3",
        # TiLiA and the core write "/" between folders, so a backslash is a
        # hand edit or part of a name on macOS and Linux: kept as written.
        "audio\\x.wav",
        "..\\audio\\piece.mp3",
    ],
)
def test_a_relative_path_written_by_hand_is_kept(tmp_path, where, stored):
    media_file(tmp_path / "audio" / "piece.mp3")
    piece = old_file(tmp_path / "corpus", where, stored, WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


def test_a_backslash_in_an_old_relative_path_is_rebased_as_part_of_a_name(
    tmp_path, where
):
    # Rebased with POSIX semantics, so that the file's bytes are the same on
    # every system (FR-023).
    piece = old_file(tmp_path / "corpus", where, "audio\\x.wav", WINDOWS_SAVED)
    target = tmp_path / "corpus" / "deeper" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, tla.read(piece))
    assert stored_in(tla.read(target), where) == "../audio\\x.wav"


@posix_only
def test_a_name_holding_a_backslash_keeps_its_media(tmp_path):
    # A legal name on macOS and Linux: kept when made relative, found, and
    # kept through a Save As.
    media = media_file(tmp_path / "corpus" / "a\\b.wav")
    piece = old_file(tmp_path / "corpus", "media", str(media), POSIX_SAVED)
    doc = tla.read(piece)
    assert doc.media_path == "a\\b.wav"
    assert os.path.samefile(tla.media(piece, doc).path, media)
    target = tmp_path / "corpus" / "deeper" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    assert json.loads(target.read_bytes())["media"]["path"] == "../a\\b.wav"
    assert os.path.samefile(tla.media(target, tla.read(target)).path, media)


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


def test_a_folder_at_the_stored_path_isnt_the_media(tmp_path, where):
    # Whether the media exists is asked as tla.media asks it: a folder isn't
    # media, so the path is made relative from the old file_path's folder.
    stored = tmp_path / "audio" / "piece.wav"
    stored.mkdir(parents=True)
    saved = str(tmp_path / "elsewhere" / "piece.tla")
    piece = old_file(tmp_path / "a" / "b", where, str(stored), saved)
    assert stored_in(tla.read(piece), where) == "../audio/piece.wav"


def test_media_named_in_decomposed_form_exists(tmp_path, where):
    # Found as tla.media finds it, so made relative from the file's folder,
    # not from the old file_path's.
    name = "Ständchen"
    media_file(tmp_path / "audio" / f"{unicodedata.normalize('NFD', name)}.wav")
    stored = str(tmp_path / "audio" / f"{name}.wav")
    saved = str(tmp_path / "elsewhere" / "piece.tla")
    piece = old_file(tmp_path / "a" / "b", where, stored, saved)
    assert stored_in(tla.read(piece), where) == f"../../audio/{name}.wav"


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
def test_a_path_on_a_windows_server(tmp_path, servers, where, file_path, stored):
    # As TiLiA saves one, with "/": a path, not a URL (FR-033).
    piece = old_file(tmp_path / "corpus", where, stored, file_path)
    assert stored_in(tla.read(piece), where) == "../audio/piece.mp3"
    if WINDOWS:  # looked for, as any absolute path of this system is
        assert servers.looked_up == ["//server-176/share/audio/piece.mp3"]


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
    tmp_path, servers, where, file_path, stored, expected
):
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


@pytest.mark.parametrize(
    "stored, file_path, expected",
    [(OTHER_SYSTEM_MEDIA, OTHER_SYSTEM_SAVED, "../audio/piece.mp3")],
    ids=["another system's path"],
)
def test_another_systems_path_is_never_looked_up_here(
    tmp_path, monkeypatch, where, stored, file_path, expected
):
    # Looked up, it would name another file: below the working folder on
    # macOS and Linux, or on the current drive on Windows.
    piece = old_file(tmp_path / "corpus", where, stored, file_path)
    looked_up = []

    def found(path):
        looked_up.append(os.fspath(path))
        return True

    # Whichever the migration asks, each says the path is there.
    monkeypatch.setattr(os.path, "exists", found)
    monkeypatch.setattr(os.path, "isfile", found)
    doc = tla.read(piece)
    monkeypatch.undo()
    assert [
        path for path in looked_up if "someone-176" in path or "youtube" in path
    ] == []
    assert stored_in(doc, where) == expected


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


# An old file's fingerprint: from its paths as stored (FR-043)


def link_folder(link, target):
    """A link to a folder: a junction on Windows, which needs no privilege, a
    symbolic link elsewhere."""
    if WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def remove_link_to_folder(link):
    if WINDOWS:
        os.rmdir(link)  # the junction, not what it names
    else:
        link.unlink()


@pytest.fixture
def linked_folder(tmp_path):
    """A folder, and a link to it."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link_folder(link, real)
    yield real, link
    remove_link_to_folder(link)


def test_an_old_file_read_through_a_link_is_written_as_expected(linked_folder, where):
    # write reads the file again at its real path, where its media path is
    # made relative from another folder than the one it was read through.
    real, link = linked_folder
    media = media_file(real / "audio" / "piece.wav")
    old_file(real / "corpus", where, str(media), SAVED_HERE)
    piece = link / "corpus" / "piece.tla"
    expected = tla.fingerprint(piece)
    assert tla.fingerprint(real / "corpus" / "piece.tla") == expected
    doc = tla.read(piece)
    assert tla.write(piece, doc, expect=expected) == tla.fingerprint(piece)
    assert json.loads((real / "corpus" / "piece.tla").read_bytes())["version"] == (
        tla.FORMAT_VERSION
    )


@pytest.mark.parametrize("appears", [True, False], ids=["appears", "goes"])
def test_an_old_files_media_that_comes_or_goes_doesnt_refuse_its_write(
    tmp_path, where, appears
):
    # The drive is plugged in or out between the fingerprint and the write:
    # the media path is made relative by rule 3, then rule 2, or the reverse.
    media = tmp_path / "audio" / "piece.wav"
    if not appears:
        media_file(media)
    piece = old_file(tmp_path / "corpus", where, str(media), SAVED_HERE)
    expected = tla.fingerprint(piece)
    doc = tla.read(piece)
    if appears:
        media_file(media)
    else:
        media.unlink()
    assert tla.fingerprint(piece) == expected
    tla.write(piece, doc, expect=expected)
    assert tla.read(piece).format_version == tla.FORMAT_VERSION


def test_copies_of_an_old_file_in_two_folders_have_one_fingerprint(tmp_path, where):
    # Their media paths are made relative from each one's folder.
    stored = WINDOWS_MEDIA if WINDOWS else POSIX_MEDIA
    here = old_file(tmp_path / "here", where, stored, "")
    elsewhere = old_file(tmp_path / "elsewhere" / "deeper", where, stored, "")
    assert stored_in(tla.read(here), where) != stored_in(tla.read(elsewhere), where)
    assert tla.fingerprint(here) == tla.fingerprint(elsewhere)


def test_an_old_files_fingerprint_is_that_of_its_paths_as_stored(tmp_path, where):
    # Not that of the document read from it, whose paths are made relative:
    # a write states the fingerprint the file gave (contracts/python-api.md).
    media = media_file(tmp_path / "audio" / "piece.wav")
    piece = old_file(tmp_path / "corpus", where, str(media), SAVED_HERE)
    doc = tla.read(piece)
    as_stored = tla.loads(piece.read_bytes(), path=piece)
    if where == "media":
        as_stored.media_path = str(media)
    else:
        (pdf,) = [tl for tl in as_stored.timelines.values() if tl.kind == "pdf"]
        pdf.attrs["path"] = str(media)
    assert tla.fingerprint(piece) == tla.fingerprint_of(as_stored)
    assert tla.fingerprint(piece) != tla.fingerprint_of(doc)


def test_an_old_file_whose_media_path_is_edited_changes_fingerprint(tmp_path, where):
    piece = old_file(tmp_path / "corpus", where, WINDOWS_MEDIA, WINDOWS_SAVED)
    expected = tla.fingerprint(piece)
    doc = tla.read(piece)
    old_file(tmp_path / "corpus", where, WINDOWS_MEDIA.replace("piece", "other"))
    assert tla.fingerprint(piece) != expected
    with pytest.raises(tla.FileChanged):
        tla.write(piece, doc, expect=expected)


def test_a_current_files_fingerprint_is_that_of_its_bytes_through_a_link(
    linked_folder,
):
    real, link = linked_folder
    shutil.copyfile(EVERY_KIND, real / "piece.tla")
    data = (real / "piece.tla").read_bytes()
    expected = hashlib.sha256(data).hexdigest()
    assert tla.fingerprint(link / "piece.tla") == expected
    assert tla.fingerprint(real / "piece.tla") == expected
    doc = tla.read(link / "piece.tla")
    doc.metadata["note"] = "edited"
    tla.write(link / "piece.tla", doc, expect=expected)


# `tilia migrate --apply` states an old file's fingerprint (FR-043, FR-104)


@pytest.mark.parametrize(
    "present, reached, relative",
    [
        (True, "directly", "../audio/piece.wav"),
        (False, "directly", "../audio/piece.mp3"),
        # From the folder it is reached through, which the media is outside.
        (True, "through a linked folder", "../../real/audio/piece.wav"),
        (False, "through a linked folder", "../audio/piece.mp3"),
        (True, "through a link to the file", "../audio/piece.wav"),
        (False, "through a link to the file", "../audio/piece.mp3"),
    ],
)
def test_tilia_migrate_writes_an_old_file_whose_path_it_makes_relative(
    linked_folder, capsys, where, present, reached, relative
):
    # The fingerprint it states is the old file's, with the path as stored,
    # which isn't the migrated document's: without it, every such file would
    # read as changed since it was read.
    real, link = linked_folder
    if present:
        stored = str(media_file(real / "audio" / "piece.wav"))
    else:  # where it was saved, on another computer of this system's kind
        stored = WINDOWS_MEDIA if WINDOWS else POSIX_MEDIA
    piece = old_file(real / "corpus", where, stored, SAVED_HERE)
    folder = real / "corpus"
    if reached == "through a linked folder":
        folder = link / "corpus"
    elif reached == "through a link to the file":
        folder = real / "links"
        folder.mkdir()
        try:
            os.symlink(piece, folder / "piece.tla")
        except OSError:
            pytest.skip("this system doesn't let the tests make symbolic links")

    status = migrate_command.main([str(folder), "--apply"])

    out = capsys.readouterr().out
    assert status == 0, out
    assert "changed since" not in out
    assert "Wrote 1 file." in out
    written = tla.read(piece)
    assert (written.format_version, stored_in(written, where)) == (
        tla.FORMAT_VERSION,
        relative,
    )


def test_tilia_migrate_leaves_alone_a_file_changed_after_it_read_it(
    tmp_path, monkeypatch, where
):
    # The fingerprint it states is of the bytes it read and migrated, not of
    # the file as it is by the time it writes.
    media = media_file(tmp_path / "audio" / "piece.wav")
    piece = old_file(tmp_path / "corpus", where, str(media), SAVED_HERE)
    read = folder_module.read_with_migration
    other = str(media.with_name("other.wav"))
    edited = json.dumps(old_content(where, other, SAVED_HERE)).encode()

    def then_edited(path):
        read_result = read(path)
        Path(path).write_bytes(edited)
        return read_result

    monkeypatch.setattr(folder_module, "read_with_migration", then_edited)

    report = tla.migrate_folder(tmp_path / "corpus", apply=True)

    assert [f.outcome for f in report.files] == [tla.Outcome.CHANGED_SINCE_READ]
    assert piece.read_bytes() == edited


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
        "http://youtube.com/embed/_ORrftU6sGA",
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
    "stored",
    [
        "youtu_be/clip.mp4",
        "youtuxbe/clip.mp4",
        # Without a scheme, a path like a link is a file's (FR-033).
        "youtube.com/clip.mp4",
        "youtu.be/clip.mp4",
        "www.youtube.com/embed/clip",
    ],
)
def test_a_relative_path_isnt_taken_for_a_youtube_link(tmp_path, stored):
    # Nor is one that differs from the pattern by the dot in "youtu.be",
    # which TiLiA's own pattern leaves to match any character.
    media = media_file(tmp_path / stored)
    doc = tla.new_document()
    doc.media_path = stored
    found = tla.media(tmp_path / "piece.tla", doc)
    assert (found.kind, found.youtube_id) == ("local", None)
    assert os.path.samefile(found.path, media)


@pytest.mark.parametrize(
    "stored",
    ["//server-176/share/audio/piece.wav", "//www.youtube.com/watch?v=_ORrftU6sGA"],
    ids=["a server's", "like a link"],
)
def test_a_path_starting_with_two_slashes_is_a_server_path(tmp_path, servers, stored):
    # In a file of the current format, even one like a link, which only a
    # hand could have stored (FR-033).
    servers.there.add(stored)
    doc = tla.new_document()
    doc.media_path = stored
    found = tla.media(tmp_path / "piece.tla", doc)
    assert (found.kind, found.youtube_id) == ("local", None)
    if WINDOWS:
        assert found.path == Path(stored)
    else:  # another system's path, never looked up here
        assert (found.path, servers.looked_up) == (None, [])


@pytest.mark.parametrize("given", ["youtube.com/clip.mp4", "youtu.be/_ORrftU6sGA"])
def test_a_given_path_like_a_youtube_link_is_a_file_when_there_is_one(
    tmp_path, monkeypatch, given
):
    # As TiLiA's load-media and build.load_media are given it (FR-033):
    # returned absolute, from the working folder, so that the writer can
    # store it relative to the file.
    monkeypatch.chdir(tmp_path)
    media_file(tmp_path / given)
    assert Path(tla.as_media_path(given)) == tmp_path / given
    assert os.path.isabs(tla.as_media_path(given))


@pytest.mark.parametrize(
    "given",
    [
        "youtube.com/clip.mp4",
        "youtu.be/_ORrftU6sGA",
        "www.youtube.com/watch?v=_ORrftU6sGA",
        "m.youtube.com/watch?v=_ORrftU6sGA&t=10s",
    ],
)
def test_a_given_path_like_a_youtube_link_is_a_link_otherwise(
    tmp_path, monkeypatch, given
):
    monkeypatch.chdir(tmp_path)
    assert tla.as_media_path(given) == f"https://{given}"


@pytest.mark.parametrize(
    "given",
    [
        "https://www.youtube.com/watch?v=_ORrftU6sGA",
        "http://youtu.be/_ORrftU6sGA",
        "https://example.com/audio/piece.mp3",
        "",
    ],
)
def test_a_given_url_or_no_path_is_kept(tmp_path, monkeypatch, given):
    monkeypatch.chdir(tmp_path)
    assert tla.as_media_path(given) == given


@pytest.mark.parametrize(
    "given",
    [
        "audio/piece.wav",
        "youtu_be/clip.mp4",
        "../piece.wav",
        "//server-176/share/audio/piece.wav",
    ],
)
def test_a_given_path_is_made_absolute_from_the_working_folder(
    tmp_path, monkeypatch, servers, given
):
    # As the reader resolves a relative path against the file's folder, a
    # relative one given would otherwise be lost when written (FR-033).
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    found = tla.as_media_path(given)
    assert os.path.isabs(found)
    assert Path(found) == Path(os.path.normpath(os.path.join(work, given)))


def test_a_given_absolute_path_is_kept(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    given = str(tmp_path / "audio" / "piece.wav")
    assert tla.as_media_path(given) == given


class GivenPath:
    """A path object whose text is the same on every system."""

    def __init__(self, text):
        self.text = text

    def __fspath__(self):
        return self.text


@pytest.mark.parametrize("make", [Path, GivenPath], ids=["Path", "with slashes"])
@pytest.mark.parametrize(
    "given", ["youtu.be/_ORrftU6sGA", "www.youtube.com/watch?v=_ORrftU6sGA"]
)
def test_a_given_path_object_is_never_a_link(tmp_path, monkeypatch, make, given):
    # A PathLike is a path: its text differs by system ("\\" in a Path on
    # Windows), so it is never matched against the pattern.
    monkeypatch.chdir(tmp_path)
    found = tla.as_media_path(make(given))
    assert Path(found) == tmp_path / given


@pytest.mark.parametrize("there", [False, True], ids=["nothing there", "a file there"])
def test_a_given_link_starting_with_two_slashes_is_a_link(
    tmp_path, monkeypatch, servers, there
):
    # A link without its "https:", as the migration takes an old one: never
    # looked for on a server, which on Windows could block for seconds and
    # reach the host the link names (FR-033).
    monkeypatch.chdir(tmp_path)
    given = "//www.youtube.com/watch?v=_ORrftU6sGA"
    if there:
        servers.there.add(given)
    assert tla.as_media_path(given) == f"https:{given}"
    assert servers.looked_up == []


@pytest.mark.parametrize("given", ["youtube.com/clip.mp4", "audio/x.wav"])
@pytest.mark.parametrize("read", [False, True], ids=["new", "read elsewhere"])
def test_a_given_path_is_stored_so_that_its_media_is_found(
    tmp_path, monkeypatch, given, read
):
    # A script in work/ records media beside it, then saves into out/.
    media = media_file(tmp_path / "work" / given)
    if read:
        source = tmp_path / "corpus" / "piece.tla"
        source.parent.mkdir()
        tla.write(source, tla.new_document())
        doc = tla.read(source)
    else:
        doc = tla.new_document()
    monkeypatch.chdir(tmp_path / "work")
    doc.media_path, doc.media_length = tla.as_media_path(given), 10.0
    target = tmp_path / "out" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    assert json.loads(target.read_bytes())["media"]["path"] == f"../work/{given}"
    assert os.path.samefile(tla.media(target, tla.read(target)).path, media)


@pytest.fixture
def linked_audio(tmp_path):
    """A corpus whose `audio` folder is a link to another disk's, which holds
    `rec.wav`."""
    (tmp_path / "corpus").mkdir()
    media_file(tmp_path / "ext" / "audio" / "rec.wav")
    link = tmp_path / "corpus" / "audio"
    link_folder(link, tmp_path / "ext" / "audio")
    yield link
    remove_link_to_folder(link)


def test_a_given_path_through_a_link_stays_through_it(linked_audio):
    # The writer takes the folder it writes into without following links.
    # Through the link's target, the path it stores would go out of the corpus
    # and back in (FR-033).
    given = str(linked_audio / "rec.wav")
    assert tla.as_media_path(given) == given


def test_a_given_relative_path_stays_through_a_link(linked_audio, monkeypatch):
    # The link comes after the "..", so the two ways of reading it agree.
    scripts = linked_audio.parent / "scripts"
    scripts.mkdir()
    monkeypatch.chdir(scripts)
    assert tla.as_media_path("../audio/rec.wav") == str(linked_audio / "rec.wav")


@posix_only
@pytest.mark.parametrize(
    "in_the_target, beside_the_link",
    [(True, False), (True, True), (False, True)],
    ids=["no file by name", "another file by name", "only another file by name"],
)
def test_a_given_parent_after_a_link_is_the_one_the_system_reads(
    tmp_path, linked_audio, in_the_target, beside_the_link
):
    # The system goes up from the link's target, and `os.path.abspath`, by
    # name, from the link: to no file, or to another one. Windows reads the
    # name as `os.path.abspath` does.
    expected = tmp_path / "ext" / "rec.wav"
    if in_the_target:
        media_file(expected)
    if beside_the_link:
        media_file(tmp_path / "corpus" / "rec.wav")
    assert tla.as_media_path(f"{linked_audio}/../rec.wav") == str(expected)


@posix_only
def test_a_given_relative_parent_after_a_link_is_the_one_the_system_reads(
    tmp_path, linked_audio, monkeypatch
):
    media_file(tmp_path / "ext" / "rec.wav")
    monkeypatch.chdir(linked_audio.parent)
    assert tla.as_media_path("audio/../rec.wav") == str(tmp_path / "ext" / "rec.wav")


@posix_only
@pytest.mark.parametrize("make", [str, Path, GivenPath], ids=["text", "Path", "object"])
def test_two_slashes_before_a_given_file_are_the_one_root(tmp_path, make):
    # `os.path.abspath` keeps them, as POSIX lets it; the core reads a path that
    # starts with them as a server's, of Windows form, which isn't looked for
    # here and which the writer doesn't make relative.
    media = media_file(tmp_path / "rec.wav")
    assert tla.as_media_path(make(f"/{media}")) == str(media)


@posix_only
def test_a_given_file_with_two_slashes_is_written_relative(tmp_path):
    media = media_file(tmp_path / "rec.wav")
    doc = tla.new_document()
    doc.media_path, doc.media_length = tla.as_media_path(f"/{media}"), 10.0
    target = tmp_path / "piece.tla"
    tla.write(target, doc)
    assert json.loads(target.read_bytes())["media"]["path"] == "rec.wav"


@windows_only
def test_a_given_server_path_isnt_looked_up_on_windows(servers):
    # It would go to the network, and nothing here needs what it would find.
    given = "//server-176/share/rec.wav"
    assert Path(tla.as_media_path(given)) == Path(given)
    assert servers.looked_up == []


def test_the_lookup_doesnt_hide_its_module():
    # tla.media is the function the contract names; the module it comes from
    # has a name of its own, so importing the module gives the module.
    module = importlib.import_module("tilia_core.tla.media_files")
    assert inspect.ismodule(module)
    assert tla.media is module.media


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


@pytest.mark.parametrize(
    "stored",
    [OTHER_SYSTEM_MEDIA, "https://example.com/audio/piece.mp3"],
    ids=["another system's path", "a link"],
)
def test_a_url_or_another_systems_media_is_never_looked_up_here(
    tmp_path, monkeypatch, stored
):
    looked_up = []

    def isfile(path):
        looked_up.append(os.fspath(path))
        return True

    doc = tla.new_document()
    doc.media_path = stored
    monkeypatch.setattr(os.path, "isfile", isfile)
    found = tla.media(tmp_path / "piece.tla", doc)
    monkeypatch.undo()
    assert (found.kind, found.path, looked_up) == ("local", None, [])


@windows_only
def test_on_windows_a_backslash_in_a_relative_path_separates_folders(tmp_path):
    # tla.media joins the path to the file's folder as it is, and lets the
    # system read it: Windows reads a backslash as a separator.
    media = media_file(tmp_path / "audio" / "x.wav")
    doc = tla.new_document()
    doc.media_path = "audio\\x.wav"
    assert os.path.samefile(tla.media(tmp_path / "piece.tla", doc).path, media)


NAME = "Ständchen"


@pytest.mark.parametrize(
    "on_disk",
    [
        # In a folder whose name is in NFC, as a file copied into it is.
        f"{NAME}/{unicodedata.normalize('NFD', NAME)}.wav",
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


# Writing: paths relative to the folder written into (FR-003, FR-033)


@pytest.fixture
def corpus(tmp_path):
    """A file of the current format in corpus/, with its media in audio/ and
    its PDF in scores/: every-kind.tla, whose paths are relative."""
    media_file(tmp_path / "audio" / f"{NAME}.flac")
    media_file(tmp_path / "scores" / f"{NAME}.pdf")
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    shutil.copyfile(EVERY_KIND, piece)
    return piece


def pdf_path(doc):
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    return pdf.attrs["path"]


def set_pdf_path(doc, value):
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    pdf.attrs["path"] = value


def written(path):
    content = json.loads(Path(path).read_bytes())
    (pdf,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Pdf"]
    return content["media"]["path"], pdf["path"]


def found(path):
    """Where the file at `path` finds its media and its PDF."""
    doc = tla.read(path)
    pdf = os.path.join(os.path.dirname(path), pdf_path(doc))
    return tla.media(path, doc).path, Path(os.path.normpath(pdf))


@pytest.mark.parametrize(
    "place, expected",
    [
        ("elsewhere/deeper", ("../../audio/", "../../scores/")),
        ("", ("audio/", "scores/")),
        ("corpus/sub", ("../../audio/", "../../scores/")),
        ("audio", ("", "../scores/")),
    ],
)
def test_written_into_another_folder_the_media_is_still_found(
    corpus, tmp_path, place, expected
):
    doc = tla.read(corpus)
    assert written(corpus) == (f"../audio/{NAME}.flac", f"../scores/{NAME}.pdf")
    target = tmp_path / place / "copy.tla"
    target.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = tla.write(target, doc)
    media_folder, pdf_folder = expected
    assert written(target) == (f"{media_folder}{NAME}.flac", f"{pdf_folder}{NAME}.pdf")
    media_found, pdf_found = found(target)
    assert os.path.samefile(media_found, tmp_path / "audio" / f"{NAME}.flac")
    assert os.path.samefile(pdf_found, tmp_path / "scores" / f"{NAME}.pdf")
    # The fingerprint is that of the bytes written (FR-043).
    assert fingerprint == tla.fingerprint(target)


def test_after_a_save_as_the_document_finds_its_media(corpus, tmp_path):
    # The document follows the file written: its origin, and its paths as
    # written (FR-033).
    doc = tla.read(corpus)
    target = tmp_path / "elsewhere" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)
    tla.write(target, doc)
    assert doc.origin == target
    assert (doc.media_path, pdf_path(doc)) == written(target)
    assert os.path.samefile(
        tla.media(target, doc).path, tmp_path / "audio" / f"{NAME}.flac"
    )
    pdf = os.path.normpath(os.path.join(target.parent, pdf_path(doc)))
    assert os.path.samefile(pdf, tmp_path / "scores" / f"{NAME}.pdf")
    # So writing it back where it was read from changes nothing.
    tla.write(corpus, doc)
    assert corpus.read_bytes() == EVERY_KIND.read_bytes()


def test_after_a_write_the_document_keeps_its_timelines(corpus, tmp_path):
    # Only a rebased PDF timeline's path changes: code that holds a timeline,
    # or its attributes, still holds the document's.
    doc = tla.read(corpus)
    timelines = dict(doc.timelines)
    attrs = {key: timeline.attrs for key, timeline in timelines.items()}
    target = tmp_path / "elsewhere" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)
    tla.write(target, doc)
    assert pdf_path(doc) == f"../../scores/{NAME}.pdf"  # rebased
    assert all(doc.timelines[key] is timeline for key, timeline in timelines.items())
    assert all(doc.timelines[key].attrs is attrs[key] for key in timelines)


def test_after_each_write_the_document_is_what_is_on_disk(corpus, tmp_path):
    doc = tla.read(corpus)
    doc.media_path = (tmp_path / "audio" / f"{NAME}.flac").as_posix()  # absolute
    targets = [
        tmp_path / "one" / "piece.tla",
        tmp_path / "two" / "three" / "piece.tla",
        tmp_path / "two" / "three" / "piece.tla",
        corpus,
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = tla.write(target, doc)
        assert tla.canonical_bytes(doc) == target.read_bytes()
        assert tla.fingerprint_of(doc) == fingerprint == tla.fingerprint(target)
    assert corpus.read_bytes() == EVERY_KIND.read_bytes()


@pytest.mark.parametrize("failure", ["changed", "read-only", "rename"])
def test_a_write_that_fails_leaves_the_document_as_it_was(
    corpus, tmp_path, monkeypatch, failure
):
    if failure == "read-only" and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root may write any file")
    doc = tla.read(corpus)
    doc.media_path = (tmp_path / "audio" / f"{NAME}.flac").as_posix()  # absolute
    before = (doc.origin, doc.media_path, pdf_path(doc), tla.canonical_bytes(doc))
    target = tmp_path / "elsewhere" / "piece.tla"
    target.parent.mkdir()
    shutil.copyfile(EVERY_KIND, target)
    try:
        if failure == "changed":
            with pytest.raises(tla.FileChanged):
                tla.write(target, doc, expect="0" * 64)
        elif failure == "read-only":
            os.chmod(target, stat.S_IREAD)
            with pytest.raises(PermissionError):
                tla.write(target, doc)
        else:
            # The last step: the temporary file can't replace the file.
            error = OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

            def replace(src, dst):
                raise error

            monkeypatch.setattr(os, "replace", replace)
            with pytest.raises(OSError):
                tla.write(target, doc)
            monkeypatch.undo()
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
    after = (doc.origin, doc.media_path, pdf_path(doc), tla.canonical_bytes(doc))
    assert after == before


def test_a_copy_of_a_copy_still_finds_its_media(corpus, tmp_path):
    first = tmp_path / "one" / "piece.tla"
    second = tmp_path / "two" / "three" / "piece.tla"
    for path in (first, second):
        path.parent.mkdir(parents=True)
    tla.write(first, tla.read(corpus))
    tla.write(second, tla.read(first))
    media_found, pdf_found = found(second)
    assert os.path.samefile(media_found, tmp_path / "audio" / f"{NAME}.flac")
    assert os.path.samefile(pdf_found, tmp_path / "scores" / f"{NAME}.pdf")


@pytest.mark.parametrize(
    "spelling",
    [
        lambda path: path,
        lambda path: path.parent / ".." / path.parent.name / path.name,
        pytest.param(
            lambda path: Path(str(path).upper()),
            marks=windows_only,
        ),
    ],
    ids=["same", "through ..", "in capitals"],
)
def test_written_where_it_was_read_its_paths_are_kept_as_they_are(corpus, spelling):
    # Even spelled otherwise than the writer would compute them.
    doc = tla.read(corpus)
    doc.media_path = f"./../audio/./{NAME}.flac"
    set_pdf_path(doc, f"../corpus/../scores/{NAME}.pdf")
    tla.write(spelling(corpus), doc)
    assert written(corpus) == (
        f"./../audio/./{NAME}.flac",
        f"../corpus/../scores/{NAME}.pdf",
    )


def test_an_absolute_path_is_written_relative_where_the_document_was_read(
    corpus, tmp_path
):
    # A script opens a file, records media as `build` does, absolute, and
    # saves it where it was.
    doc = tla.read(corpus)
    doc.media_path = (tmp_path / "audio" / f"{NAME}.flac").resolve().as_posix()
    set_pdf_path(doc, str(tmp_path / "scores" / f"{NAME}.pdf"))
    tla.write(corpus, doc)
    assert written(corpus) == (f"../audio/{NAME}.flac", f"../scores/{NAME}.pdf")
    assert corpus.read_bytes() == EVERY_KIND.read_bytes()


def test_an_absolute_path_is_written_relative_from_a_new_document(tmp_path):
    media = media_file(tmp_path / "audio" / "piece.wav")
    doc = tla.new_document()
    doc.media_path, doc.media_length = media.resolve().as_posix(), 10.0
    target = tmp_path / "corpus" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    assert json.loads(target.read_bytes())["media"]["path"] == "../audio/piece.wav"
    assert os.path.samefile(tla.media(target, tla.read(target)).path, media)
    # The document follows the file, so its fingerprint is the file's, and a
    # second write that states it isn't refused (FR-033).
    assert doc.media_path == "../audio/piece.wav"
    expected = tla.fingerprint_of(doc)
    doc.metadata["note"] = "edited"
    tla.write(target, doc, expect=expected)


def test_a_relative_path_of_a_document_read_from_nowhere_is_kept(tmp_path):
    # Nothing tells what it is relative to.
    doc = tla.new_document()
    doc.media_path = "audio/piece.wav"
    tla.write(tmp_path / "piece.tla", doc)
    assert json.loads((tmp_path / "piece.tla").read_bytes())["media"]["path"] == (
        "audio/piece.wav"
    )


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "https://www.youtube.com/watch?v=_ORrftU6sGA",
        "https://example.com/audio/piece.mp3",
        OTHER_SYSTEM_MEDIA,
        "C:piece.wav",
        "\\audio\\piece.wav",
    ],
)
def test_written_elsewhere_an_empty_path_a_url_or_another_systems_path_is_kept(
    corpus, tmp_path, stored
):
    doc = tla.read(corpus)
    doc.media_path = stored
    set_pdf_path(doc, stored)
    tla.write(tmp_path / "copy.tla", doc)
    assert written(tmp_path / "copy.tla") == (stored, stored)


@pytest.mark.parametrize(
    "stored",
    ["//server-176/share/audio/piece.wav", "//server-176/share/audio/watch?v=x"],
    ids=["a server's", "like a link"],
)
def test_a_path_starting_with_two_slashes_is_rebased_as_a_path(stored):
    # A server path, not a URL (FR-033): relative to a folder on its share on
    # Windows; another system's path, kept as it is, on macOS and Linux.
    doc = tla.new_document()
    doc.media_path = stored
    rebased = writer.rebase_paths(doc, "//server-176/share/corpus")
    name = stored.rsplit("/", 1)[1]
    assert rebased.media_path == (f"../audio/{name}" if WINDOWS else stored)


def test_an_absolute_path_without_a_relative_one_is_written_with_slashes(corpus):
    # On another drive on Windows, of the other system's form on macOS and
    # Linux: written as the migration writes it, so that the same document
    # gives the same bytes.
    doc = tla.read(corpus)
    doc.media_path = "Z:\\audio-176\\piece.wav"
    set_pdf_path(doc, "Z:\\scores-176\\piece.pdf")
    tla.write(corpus, doc)
    assert written(corpus) == ("Z:/audio-176/piece.wav", "Z:/scores-176/piece.pdf")


@pytest.mark.parametrize(
    "place, expected",
    [("corpus", ""), ("elsewhere/deeper", "../../corpus/")],
    ids=["where it was read", "elsewhere"],
)
def test_a_backslash_in_a_relative_path_is_written_as_part_of_a_name(
    corpus, tmp_path, place, expected
):
    # Never converted, and rebased with POSIX semantics, so that the same
    # document gives the same bytes on every system (FR-023). Windows still
    # reads the backslash as a separator, and finds the media.
    doc = tla.read(corpus)
    doc.media_path = f"..\\audio\\{NAME}.flac"
    set_pdf_path(doc, f"..\\scores\\{NAME}.pdf")
    target = tmp_path / place / "piece.tla"
    target.parent.mkdir(parents=True, exist_ok=True)
    tla.write(target, doc)
    assert written(target) == (
        f"{expected}..\\audio\\{NAME}.flac",
        f"{expected}..\\scores\\{NAME}.pdf",
    )
    if WINDOWS:
        media_found, pdf_found = found(target)
        assert os.path.samefile(media_found, tmp_path / "audio" / f"{NAME}.flac")
        assert os.path.samefile(pdf_found, tmp_path / "scores" / f"{NAME}.pdf")


@pytest.mark.parametrize(
    "stored", ["youtu_be/clip.mp4", "youtube.com/clip.mp4", "youtu.be/clip.mp4"]
)
def test_written_elsewhere_a_path_like_a_youtube_link_is_rebased(
    corpus, tmp_path, stored
):
    # Without a scheme, it is a file's path (FR-033).
    media = media_file(corpus.parent / stored)
    doc = tla.read(corpus)
    doc.media_path = stored
    tla.write(tmp_path / "copy.tla", doc)
    assert written(tmp_path / "copy.tla")[0] == f"corpus/{stored}"
    assert os.path.samefile(tla.media(tmp_path / "copy.tla", doc).path, media)


@windows_only
def test_a_relative_path_written_onto_another_drive_becomes_absolute(corpus, tmp_path):
    doc = tla.read(corpus)
    rebased = writer.rebase_paths(doc, "Z:\\elsewhere-176")
    assert rebased.media_path == (tmp_path / "audio" / f"{NAME}.flac").as_posix()
    assert pdf_path(rebased) == (tmp_path / "scores" / f"{NAME}.pdf").as_posix()
    assert doc.media_path == f"../audio/{NAME}.flac"


# Writing: a stored path's names, and what its form makes of a backslash

# The file system's root, where a folder's depth is known. `rebase_paths` only
# computes with folders: none of these is looked up.
ROOT = Path(os.path.abspath(os.sep))


def rebased_from(origin, stored, folder):
    """`stored`, in a document read from a file in the folder `origin`, as a
    file in `folder` stores it."""
    doc = tla.new_document()
    doc.media_path = stored
    doc.origin = Path(origin) / "piece.tla"
    return writer.rebase_paths(doc, folder).media_path


@pytest.mark.parametrize(
    "stored, on_windows, on_posix",
    [
        ("a\\b/../c.wav", "corpus/a/c.wav", "corpus/c.wav"),
        ("a\\b/../../c.wav", "corpus/c.wav", "c.wav"),
    ],
)
def test_a_save_as_keeps_the_file_a_path_with_a_backslash_names(
    corpus, tmp_path, stored, on_windows, on_posix
):
    # What a ".." after a name holding a backslash goes back over differs by
    # system, so it isn't collapsed: the same bytes name the same file as
    # before on each system (FR-023).
    media = media_file(tmp_path / (on_windows if WINDOWS else on_posix))
    doc = tla.read(corpus)
    doc.media_path = stored
    assert os.path.samefile(tla.media(corpus, doc).path, media)
    target = tmp_path / "out" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    assert written(target)[0] == f"../corpus/{stored}"
    assert os.path.samefile(tla.media(target, tla.read(target)).path, media)


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("x/../a\\b/../c.wav", "../corpus/a\\b/../c.wav"),
        ("a\\b/c/../d.wav", "../corpus/a\\b/d.wav"),
        ("a\\b/./../c.wav", "../corpus/a\\b/../c.wav"),
        ("../a\\b/../c.wav", "../a\\b/../c.wav"),
        ("a\\b/.", "../corpus/a\\b"),
        ("a\\b/..", "../corpus/a\\b/.."),
    ],
)
def test_only_a_dotdot_after_a_name_with_a_backslash_is_kept(stored, expected):
    assert rebased_from(ROOT / "corpus", stored, ROOT / "out") == expected


@windows_only
@pytest.mark.parametrize(
    "stored, place",
    [
        ("..\\audio\\x.wav", "audio/x.wav"),
        ("audio\\x.wav", "corpus/audio/x.wav"),
        ("../audio\\x.wav", "audio/x.wav"),
        ("a\\b/../c.wav", "corpus/a/c.wav"),
    ],
)
def test_a_path_written_onto_another_drive_is_stable_from_the_first_write(
    corpus, tmp_path, stored, place
):
    # It is of Windows form now, where a backslash separates folders: written
    # with "/" and normalised, so that the next write gives the same bytes.
    expected = (tmp_path / place).as_posix()
    doc = tla.read(corpus)
    doc.media_path = stored
    set_pdf_path(doc, stored)
    once = writer.rebase_paths(doc, "Z:\\elsewhere-176")
    assert (once.media_path, pdf_path(once)) == (expected, expected)
    # Once the document has followed the file onto that drive, as `write` has
    # it do.
    followed = dataclasses.replace(once, origin=Path("Z:\\elsewhere-176\\piece.tla"))
    twice = writer.rebase_paths(followed, "Z:\\elsewhere-176")
    assert tla.canonical_bytes(twice) == tla.canonical_bytes(once)


@posix_only
@pytest.mark.parametrize(
    "origin, folder",
    [
        ("//home/me/a", "/home/me/b"),
        ("/home/me/a", "//home/me/b"),
        ("//home/me/a", "//home/me/b"),
    ],
)
def test_on_posix_two_slashes_in_a_folder_are_still_the_one_root(origin, folder):
    # On macOS and Linux they name the same folders as one slash does: not a
    # server of their own, as a stored path that starts with "//" is.
    assert rebased_from(origin, "x.wav", folder) == "../a/x.wav"


@posix_only
def test_on_posix_two_slashes_in_a_folder_are_still_the_same_folder():
    stored = "./x.wav"
    assert rebased_from("//home/me/a", stored, "/home/me/a") == stored


@pytest.mark.parametrize(
    "origin, stored, folder, expected",
    [
        ("r", "CORPUS/x.wav", "r/corpus", "../CORPUS/x.wav"),
        ("r", "corpus/x.wav", "r/corpus", "x.wav"),
        ("r/a", "../CORPUS/x.wav", "r/corpus/deeper", "../../CORPUS/x.wav"),
    ],
)
def test_a_stored_name_is_compared_exactly_with_the_folders(
    origin, stored, folder, expected
):
    # On every system, so that a document gives the same bytes (FR-023); the
    # longer path is right on Windows too.
    assert rebased_from(ROOT / origin, stored, ROOT / folder) == expected


@windows_only
@pytest.mark.parametrize(
    "origin, folder, expected",
    [
        ("c:\\r-176\\corpus", "C:\\r-176\\out", "../corpus/x.wav"),
        ("C:\\r-176\\Corpus", "c:\\R-176\\CORPUS\\out", "../x.wav"),
        (
            "\\\\SERVER-176\\share\\corpus",
            "\\\\server-176\\SHARE\\out",
            "../corpus/x.wav",
        ),
    ],
    ids=["a drive", "a folder", "a share"],
)
def test_on_windows_the_folders_are_compared_in_any_case(origin, folder, expected):
    # The system gave them, and reads them so.
    assert rebased_from(origin, "x.wav", folder) == expected


@pytest.mark.parametrize(
    "origin, stored, folder, expected",
    [
        ("a", "..", "", "."),
        ("a/b", "../..", "", "."),
        ("a", ".", "out", "../a"),
        ("a", "a/..", "out", "../a"),
        ("a", "./", "out", "../a"),
        ("a", ".", "a/b", ".."),
    ],
)
def test_a_path_that_names_a_folder_stays_a_path(origin, stored, folder, expected):
    # An empty path would mean no media.
    assert rebased_from(ROOT / origin, stored, ROOT / folder) == expected


def test_a_path_never_goes_above_the_root():
    assert rebased_from(ROOT / "corpus", "../../../../x.wav", ROOT / "out") == (
        "../x.wav"
    )


@windows_only
def test_a_path_written_onto_another_drive_from_a_drives_root():
    assert rebased_from("D:\\", "x.wav", "Z:\\elsewhere-176") == "D:/x.wav"


@pytest.mark.parametrize("stored", ["./x.wav", "a/../x.wav", "a//..//x.wav"])
def test_a_save_as_writes_a_path_normalised(corpus, tmp_path, stored):
    media = media_file(corpus.parent / "x.wav")
    doc = tla.read(corpus)
    doc.media_path = stored
    target = tmp_path / "out" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    assert written(target)[0] == "../corpus/x.wav"
    assert os.path.samefile(tla.media(target, tla.read(target)).path, media)


def test_the_migration_keeps_the_backslash_of_a_posix_path_that_stays_absolute(
    tmp_path, where
):
    # Part of a name, on every system: no relative path exists from a file
    # saved on Windows.
    stored = "/home/someone-176/a\\b.wav"
    piece = old_file(tmp_path, where, stored, file_path=WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored


def test_the_writer_keeps_the_backslash_of_a_posix_path():
    # Absolute on Windows, where it is another system's; relative on macOS and
    # Linux. Part of a name either way.
    stored = "/home/someone-176/a\\b.wav"
    assert rebased_from(ROOT / "corpus", stored, "/home/someone-176/out") == (
        stored if WINDOWS else "../a\\b.wav"
    )


@pytest.mark.parametrize(
    "stored",
    [
        "x.wav",
        "./x.wav",
        "a/x.wav",
        "a/b/x.wav",
        "a//b/./x.wav",
        "a/../x.wav",
        "../x.wav",
        "../a/x.wav",
        "../../x.wav",
        "../../../../x.wav",
        "a/b/../../../x.wav",
        ".",
        "..",
        "a/..",
        "a/",
        "../..",
    ],
)
def test_on_paths_with_slashes_only_moved_is_posixpaths_relpath(stored):
    folders = ["", "a", "a/b", "a/b/c", "x", "x/y", "a/x"]
    for origin, folder in itertools.product(folders, repeat=2):
        resolved = posixpath.normpath(posixpath.join("/", origin, stored))
        expected = posixpath.relpath(resolved, posixpath.join("/", folder))
        moved = writer._moved(stored, str(ROOT / origin), str(ROOT / folder))
        assert moved == expected, (origin, folder)


# Paths given or stored in the other system's form, and what starts a share

OTHER_SYSTEMS_FORMS = (
    ["/m-176/x.wav"]
    if WINDOWS
    else [
        "C:\\m-176\\x.wav",
        "C:/m-176/x.wav",
        "\\\\server-176\\share\\x.wav",
        "//server-176/share/x.wav",
    ]
)
# A slash and a backslash: Windows would read them as a share's two slashes.
SLASH_AND_BACKSLASH = ["/\\a-176\\b.wav", "\\/a-176/b.wav"]


@pytest.mark.parametrize("given", OTHER_SYSTEMS_FORMS)
def test_a_given_path_of_the_other_systems_form_is_kept(tmp_path, monkeypatch, given):
    # It is absolute already, in its own form: not below the working folder,
    # and not on this drive.
    monkeypatch.chdir(tmp_path)
    assert tla.as_media_path(given) == given
    assert tla.as_media_path(GivenPath(given)) == given


@pytest.mark.parametrize("stored", SLASH_AND_BACKSLASH)
def test_the_migration_doesnt_read_a_share_in_a_slash_and_a_backslash(
    tmp_path, where, servers, stored
):
    # Only two slashes of one kind start a share. `/\…` is a POSIX path, and
    # `\/…` relative to a root, as `\…` is.
    piece = old_file(tmp_path, where, stored, file_path=WINDOWS_SAVED)
    assert stored_in(tla.read(piece), where) == stored
    if WINDOWS:
        assert servers.looked_up == []


@pytest.mark.parametrize(
    "stored, on_posix",
    [("/\\a-176\\b.wav", "../\\a-176\\b.wav"), ("\\/a-176/b.wav", "\\/a-176/b.wav")],
)
def test_the_writer_doesnt_read_a_share_in_a_slash_and_a_backslash(stored, on_posix):
    assert rebased_from(ROOT / "corpus", stored, ROOT / "out") == (
        stored if WINDOWS else on_posix
    )


@pytest.mark.parametrize("given", SLASH_AND_BACKSLASH)
def test_a_given_slash_and_backslash_doesnt_start_a_share(tmp_path, monkeypatch, given):
    monkeypatch.chdir(tmp_path)
    expected = given if WINDOWS or given[0] == "/" else os.path.join(os.getcwd(), given)
    assert tla.as_media_path(given) == expected


@pytest.mark.parametrize("stored", SLASH_AND_BACKSLASH)
def test_tla_media_doesnt_read_a_share_in_a_slash_and_a_backslash(
    tmp_path, servers, stored
):
    doc = tla.new_document()
    doc.media_path = stored
    assert tla.media(tmp_path / "piece.tla", doc).path is None
    if WINDOWS:
        assert servers.looked_up == []
