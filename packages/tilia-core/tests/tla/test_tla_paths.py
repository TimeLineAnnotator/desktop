"""The one path handler (`tla.paths`): every stored path, the media's and a PDF
timeline's alike, read, found, written and rebased the same way (FR-033;
TimeLineAnnotator/project-management#584).

A path the document was read with absolute stays absolute in every write, Save As
included, while the text at its place is the text read, however it got there; any
other text is made relative wherever a relative path exists (#555, option a; #582,
points 1, 3 and 4). So opening and saving changes nothing (SC-002, US1)."""

import copy
import dataclasses
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from tilia_core import tla
from tilia_core.importers import harmony_available
from tilia_core.tla import paths, writer
from tilia_core.tla.problems import cant_check

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WINDOWS, reason="drives are Windows'")
TLA = Path(__file__).parent
EVERY_KIND = TLA / "golden" / "every-kind.tla"
# Where an old file was saved on a computer of the other system: no relative
# path from it to a path of this system's form exists, so reading keeps such a
# path absolute.
OTHER_SYSTEM_SAVED = (
    "/home/someone-584/corpus/piece.tla" if WINDOWS else "C:/someone-584/piece.tla"
)
KINDS = ["media", "pdf"]


def writable(doc):
    """`doc`, without what can't be written without the `harmony` extra, when it
    isn't installed."""
    if harmony_available() or cant_check(doc) is None:
        return doc
    doc.timelines = {
        key: timeline
        for key, timeline in doc.timelines.items()
        if timeline.kind != "harmony"
    }
    return doc


def stored(doc, kind):
    """The path of `kind` that `doc` holds."""
    if kind == "media":
        return doc.media_path
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    return pdf.attrs["path"]


def set_stored(doc, kind, text):
    if kind == "media":
        doc.media_path = text
    else:
        (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
        pdf.attrs["path"] = text


def replaced(doc, kind, text):
    """A copy of `doc` made with `dataclasses.replace`, holding `text` as its
    path of `kind`."""
    if kind == "media":
        return dataclasses.replace(doc, media_path=text)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    timeline = dataclasses.replace(pdf, attrs={**pdf.attrs, "path": text})
    return dataclasses.replace(doc, timelines={**doc.timelines, pdf.id: timeline})


def written_in(path, kind):
    """The path of `kind` the file at `path` stores."""
    content = json.loads(Path(path).read_bytes())
    if kind == "media":
        return content["media"]["path"]
    (pdf,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Pdf"]
    return pdf["path"]


def relative(path, folder):
    return os.path.relpath(path, folder).replace(os.sep, "/")


@pytest.fixture(params=KINDS)
def kind(request):
    return request.param


@pytest.fixture
def current(tmp_path, kind):
    """#584's example: a current file in proj/ that stores the path of `kind`
    absolute, `read`, on the drive of the tests' folder, so that a relative path
    to it exists, written as the core writes a file. The path names no file:
    nothing here looks it up."""
    music = Path(tmp_path.anchor) / "someone-584" / "music"
    name = "x.mp3" if kind == "media" else "x.pdf"
    doc = writable(tla.read(EVERY_KIND))
    set_stored(doc, kind, (music / name).as_posix())
    piece = tmp_path / "proj" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(doc))
    return SimpleNamespace(
        piece=piece, read=(music / name).as_posix(), music=music, name=name
    )


def other(current):
    """Another file beside the one read, as `load-media` gives it, absolute."""
    return (current.music / f"y{Path(current.name).suffix}").as_posix()


# Each case: what is done to the document read from `current`, the file then
# written, and whether that file stores the path as read (None) or another, made
# relative from the file's folder.


def opened_and_saved(doc, current, kind, tmp_path):
    return doc, current.piece, None


def saved_twice(doc, current, kind, tmp_path):
    tla.write(current.piece, doc)
    return doc, current.piece, None


def saved_then_read_and_saved(doc, current, kind, tmp_path):
    tla.write(current.piece, doc)
    return tla.read(current.piece), current.piece, None


def saved_as_into_another_folder(doc, current, kind, tmp_path):
    target = tmp_path / "other" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)
    return doc, target, None


def saved_as_and_back(doc, current, kind, tmp_path):
    target = tmp_path / "other" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    return doc, current.piece, None


def set_to_another_path(doc, current, kind, tmp_path):
    set_stored(doc, kind, other(current))
    return doc, current.piece, other(current)


def set_to_another_and_back(doc, current, kind, tmp_path):
    set_stored(doc, kind, other(current))
    set_stored(doc, kind, current.read)
    return doc, current.piece, None


def set_to_the_text_read(doc, current, kind, tmp_path):
    set_stored(doc, kind, current.read)
    return doc, current.piece, None


def set_to_the_same_file_spelled_otherwise(doc, current, kind, tmp_path):
    spelled = current.read.replace("/music/", "/music/../music/")
    set_stored(doc, kind, spelled)
    return doc, current.piece, current.read


def copied_with_replace(doc, current, kind, tmp_path):
    return replaced(doc, kind, current.read), current.piece, None


def copied_with_replace_and_another_path(doc, current, kind, tmp_path):
    return replaced(doc, kind, other(current)), current.piece, other(current)


def copied_deeply(doc, current, kind, tmp_path):
    return copy.deepcopy(doc), current.piece, None


def set_to_another_path_and_saved_as(doc, current, kind, tmp_path):
    set_stored(doc, kind, other(current))
    target = tmp_path / "other" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)
    return doc, target, other(current)


def set_to_another_saved_and_set_back(doc, current, kind, tmp_path):
    # The text read is the document's for its whole life, whatever was saved in
    # between (TimeLineAnnotator/project-management#600, a): as an undo of an
    # edit saved gives it back.
    set_stored(doc, kind, other(current))
    tla.write(current.piece, doc)
    assert written_in(current.piece, kind) == relative(
        other(current), current.piece.parent
    )
    set_stored(doc, kind, current.read)
    return doc, current.piece, None


def set_to_another_saved_as_and_set_back(doc, current, kind, tmp_path):
    set_stored(doc, kind, other(current))
    target = tmp_path / "other" / "piece.tla"
    target.parent.mkdir()
    tla.write(target, doc)
    set_stored(doc, kind, current.read)
    return doc, current.piece, None


def set_to_the_text_read_as_windows_spells_it(doc, current, kind, tmp_path):
    # With a backslash between its folders, as `tla.as_media_path` gives it and
    # TiLiA's bridge stores the media: the text read, as a file stores it.
    set_stored(doc, kind, os.path.normpath(current.read))
    return doc, current.piece, None


CASES = [
    pytest.param(case, id=case.__name__)
    for case in (
        opened_and_saved,
        saved_twice,
        saved_then_read_and_saved,
        saved_as_into_another_folder,
        saved_as_and_back,
        set_to_another_path,
        set_to_another_and_back,
        set_to_the_text_read,
        set_to_the_same_file_spelled_otherwise,
        copied_with_replace,
        copied_with_replace_and_another_path,
        copied_deeply,
        set_to_another_path_and_saved_as,
        set_to_another_saved_and_set_back,
        set_to_another_saved_as_and_set_back,
    )
] + [
    pytest.param(
        set_to_the_text_read_as_windows_spells_it,
        id="set_to_the_text_read_as_windows_spells_it",
        marks=windows_only,
    )
]


@pytest.mark.parametrize("case", CASES)
def test_every_kind_of_path_is_judged_by_its_text(current, kind, tmp_path, case):
    # The media's and a PDF timeline's alike, in every case (#582, point 1).
    before = current.piece.read_bytes()
    doc, target, made_relative = case(tla.read(current.piece), current, kind, tmp_path)

    tla.write(target, doc)

    if made_relative is None:
        assert written_in(target, kind) == current.read
    else:
        assert written_in(target, kind) == relative(made_relative, target.parent)
    if case is opened_and_saved:
        assert current.piece.read_bytes() == before
    # The document follows the file: its next write changes nothing.
    data = target.read_bytes()
    tla.write(target, doc, expect=tla.fingerprint(target))
    assert target.read_bytes() == data


def test_the_text_read_in_another_normal_form_is_the_text_read(tmp_path, kind):
    # NFC and NFD spell the same text: a file stores it in NFC (FR-023).
    name = "Ständchen.mp3" if kind == "media" else "Ständchen.pdf"
    read = (Path(tmp_path.anchor) / "someone-584" / "music" / name).as_posix()
    read = unicodedata.normalize("NFC", read)
    doc = writable(tla.read(EVERY_KIND))
    set_stored(doc, kind, read)
    piece = tmp_path / "proj" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(doc))
    before = piece.read_bytes()
    doc = tla.read(piece)

    set_stored(doc, kind, unicodedata.normalize("NFD", read))
    tla.write(piece, doc)

    assert written_in(piece, kind) == read
    assert piece.read_bytes() == before


# Onto another drive, on Windows: no relative path exists there. The tests can't
# write to a drive of their own, so the core's one atomic write keeps the bytes it
# is given instead, for the drive it is given.


@pytest.fixture
def onto_another_drive(tmp_path, monkeypatch):
    """`write(doc, folder)`: `tla.write` of `doc` to `write.target(folder)`, a
    file in `folder` on another drive; it returns the content written."""
    drive = "Y:" if tmp_path.drive.upper() == "Z:" else "Z:"
    written = {}
    real = writer.atomic_write

    def atomic_write(path, data):
        if Path(path).drive.upper() == drive:
            written[os.path.normcase(str(path))] = data
        else:
            real(path, data)

    monkeypatch.setattr(writer, "atomic_write", atomic_write)

    def target(folder):
        return f"{drive}\\{folder}\\piece.tla"

    def write(doc, folder):
        tla.write(target(folder), doc)
        return json.loads(written[os.path.normcase(target(folder))])

    write.target = target
    return write


def stored_in_content(content, kind):
    if kind == "media":
        return content["media"]["path"]
    (pdf,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Pdf"]
    return pdf["path"]


@windows_only
def test_a_path_read_absolute_stays_so_onto_another_drive_and_back(
    current, kind, tmp_path, onto_another_drive
):
    doc = tla.read(current.piece)

    content = onto_another_drive(doc, "other-584")

    assert stored_in_content(content, kind) == current.read
    back = tmp_path / "back" / "piece.tla"
    back.parent.mkdir()
    tla.write(back, doc)
    assert written_in(back, kind) == current.read


@windows_only
def test_a_path_written_absolute_onto_another_drive_stays_so_back_on_this_one(
    tmp_path, kind, onto_another_drive
):
    # A relative path, written onto another drive, becomes absolute, as no
    # relative one exists there; that document's later writes keep it so, a
    # Save As back onto the drive of its media included (#555, option a).
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(writable(tla.read(EVERY_KIND))))
    doc = tla.read(piece)
    absolute = os.path.normpath(piece.parent / stored(doc, kind))
    absolute = absolute.replace("\\", "/")

    content = onto_another_drive(doc, "other-584")

    assert stored_in_content(content, kind) == absolute
    assert stored(doc, kind) == absolute
    back = tmp_path / "back" / "piece.tla"
    back.parent.mkdir()
    tla.write(back, doc)
    assert written_in(back, kind) == absolute


def a_relative_one(tmp_path, kind):
    """every-kind's document, read from corpus/, where its paths are relative,
    and the path of `kind` it holds, absolute, with "/"."""
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(writable(tla.read(EVERY_KIND))))
    doc = tla.read(piece)
    absolute = os.path.normpath(piece.parent / stored(doc, kind))
    return doc, absolute.replace("\\", "/")


@windows_only
def test_a_path_last_written_absolute_is_held_until_written_otherwise(
    tmp_path, kind, onto_another_drive
):
    # What a write wrote absolute is held by the document until a write writes
    # that place otherwise: it isn't a text the document was read with.
    doc, absolute = a_relative_one(tmp_path, kind)
    onto_another_drive(doc, "other-584")
    assert stored(doc, kind) == absolute
    another = absolute.replace("Ständchen", "Another")
    set_stored(doc, kind, another)
    back = tmp_path / "back" / "piece.tla"
    back.parent.mkdir()
    tla.write(back, doc)
    assert written_in(back, kind) == relative(another, back.parent)

    set_stored(doc, kind, absolute)
    tla.write(back, doc)

    assert written_in(back, kind) == relative(absolute, back.parent)


@windows_only
def test_a_timeline_taken_out_over_a_write_keeps_its_path_last_written_absolute(
    tmp_path, onto_another_drive
):
    # Its place wasn't written: it keeps what it held, for the timeline put back.
    doc, absolute = a_relative_one(tmp_path, "pdf")
    onto_another_drive(doc, "other-584")
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    del doc.timelines[pdf.id]
    onto_another_drive(doc, "other-585")

    doc.timelines[pdf.id] = pdf
    back = tmp_path / "back" / "piece.tla"
    back.parent.mkdir()
    tla.write(back, doc)

    assert written_in(back, "pdf") == absolute


# `loads` with no place: what reading keeps absolute is written so, in every
# write, as for any old file (#582, point 3, a).


def old_content(kind, path):
    content = {
        "app_name": "TiLiA",
        "version": "0.7.0",
        "file_path": OTHER_SYSTEM_SAVED,
        "media_path": path if kind == "media" else "",
        "media_metadata": {"title": "Piece", "media length": 60},
        "timelines": {
            "1": {"kind": "Slider", "ordinal": 1, "height": 40, "components": {}}
        },
    }
    if kind == "pdf":
        content["timelines"]["2"] = {
            "kind": "Pdf",
            "ordinal": 2,
            "height": 30,
            "path": path,
            "components": {},
        }
    return content


@pytest.mark.parametrize("exists", [True, False], ids=["here", "missing"])
def test_loads_with_no_place_keeps_an_absolute_path_in_every_write(
    tmp_path, kind, exists
):
    media = tmp_path / "audio" / "piece.wav"
    if exists:
        media.parent.mkdir()
        media.write_bytes(b"RIFF")
    data = json.dumps(old_content(kind, str(media))).encode()
    doc = tla.loads(data)
    assert stored(doc, kind) == media.as_posix()
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()

    for target in (piece, piece, tmp_path / "piece.tla"):
        tla.write(target, doc)
        assert written_in(target, kind) == media.as_posix()


# Finding a file and writing it use the same folder: for the document's own
# origin, the one kept from its read, whatever a link to the file names since
# (#584; TimeLineAnnotator/project-management#431, #433).


@pytest.fixture
def read_then_moved(tmp_path, monkeypatch):
    """A file in corpus/ with its media and PDF beside it, read; then its path
    names a file in another folder, as a link to a file changed since would:
    the folder found for it now is that one."""
    corpus = tmp_path / "corpus"
    (corpus / "audio").mkdir(parents=True)
    (corpus / "scores").mkdir()
    (corpus / "audio" / "a.wav").write_bytes(b"RIFF")
    (corpus / "scores" / "a.pdf").write_bytes(b"%PDF")
    doc = writable(tla.read(EVERY_KIND))
    doc.media_path = (corpus / "audio" / "a.wav").as_posix()
    set_stored(doc, "pdf", (corpus / "scores" / "a.pdf").as_posix())
    piece = corpus / "piece.tla"
    tla.write(piece, doc)
    doc = tla.read(piece)
    assert (doc.media_path, stored(doc, "pdf")) == ("audio/a.wav", "scores/a.pdf")
    elsewhere = tmp_path / "elsewhere" / "deep"
    elsewhere.mkdir(parents=True)
    now = paths.paths_folder

    def paths_folder(path):
        if Path(os.path.abspath(path)) == piece:
            return str(elsewhere)
        return now(path)

    monkeypatch.setattr(paths, "paths_folder", paths_folder)
    return piece, doc, corpus


def test_the_media_of_the_documents_origin_is_found_from_the_folder_read(
    read_then_moved,
):
    piece, doc, corpus = read_then_moved
    assert os.path.samefile(tla.media(piece, doc).path, corpus / "audio" / "a.wav")
    assert os.path.samefile(tla.media(doc.origin, doc).path, corpus / "audio" / "a.wav")


def test_a_stored_file_of_the_documents_origin_is_found_from_the_folder_read(
    read_then_moved,
):
    piece, doc, corpus = read_then_moved
    pdf = stored(doc, "pdf")
    assert os.path.samefile(
        tla.stored_file(doc.origin, pdf, doc=doc), corpus / "scores" / "a.pdf"
    )
    assert os.path.samefile(paths.stored_file_of(doc, pdf), corpus / "scores" / "a.pdf")
    # Without the document, the path names the file it names now.
    assert tla.stored_file(piece, pdf) is None


def test_a_stored_file_of_another_file_is_found_from_that_files_folder(tmp_path):
    # Given the document, only its own origin is looked up from the folder kept
    # from its read: another file's stored path is that file's.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "x.pdf").write_bytes(b"%PDF")
    doc = writable(tla.read(EVERY_KIND))
    set_stored(doc, "pdf", "x.pdf")
    piece = tmp_path / "proj" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(doc))
    doc = tla.read(piece)

    found = tla.stored_file(tmp_path / "b" / "f.tla", "x.pdf", doc=doc)

    assert found is not None and found.samefile(tmp_path / "b" / "x.pdf")
    assert tla.stored_file(tmp_path / "a" / "f.tla", "x.pdf", doc=doc) is None


def test_written_where_it_was_read_its_paths_are_rebased_from_the_folder_read(
    read_then_moved, tmp_path
):
    # The write and the lookup agree: the file written is the one the path
    # names now, in the other folder, so the paths, relative to the folder read,
    # are rebased from it to that one.
    piece, doc, corpus = read_then_moved
    rebased = paths.rebase_paths(doc, paths.paths_folder(piece))
    assert rebased.media_path == relative(
        corpus / "audio" / "a.wav", tmp_path / "elsewhere" / "deep"
    )


# The kinds of path, listed once


def test_every_kind_of_path_is_listed_with_its_place():
    doc = tla.read(EVERY_KIND)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    assert paths.stored_paths(doc) == [
        ("/media/path", "../audio/Ständchen.flac"),
        (f"/timelines/{pdf.id}/path", "../scores/Ständchen.pdf"),
    ]


def test_the_migration_takes_the_same_kinds():
    content = old_content("pdf", "x.pdf")
    content["media"] = {"path": "x.wav"}
    content["timelines"]["2"]["kind"] = "Pdf"
    assert [
        (place, holder[key]) for place, holder, key in paths.places_in(content)
    ] == [("/media/path", "x.wav"), ("/timelines/2/path", "x.pdf")]


# Timelines held outside the document follow its writes, as TiLiA's undo holds a
# deleted one (`paths.following`).


def test_a_held_timeline_follows_a_save_as(tmp_path):
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(writable(tla.read(EVERY_KIND))))
    doc = tla.read(piece)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    del doc.timelines[pdf.id]
    target = tmp_path / "other" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)

    with paths.following(doc, [pdf], target):
        tla.write(target, doc)

    assert pdf.attrs["path"] == "../../scores/Ständchen.pdf"


@pytest.mark.parametrize("kind", ["pdf"])
def test_a_held_timeline_read_absolute_stays_so_once_put_back(current, kind):
    doc = tla.read(current.piece)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    del doc.timelines[pdf.id]
    other_folder = current.piece.parent.parent / "other"
    other_folder.mkdir()
    target = other_folder / "piece.tla"

    with paths.following(doc, [pdf], target):
        tla.write(target, doc)
    doc.timelines[pdf.id] = pdf
    tla.write(target, doc)

    assert written_in(target, "pdf") == current.read


@windows_only
def test_a_held_timeline_written_absolute_onto_another_drive_stays_so_once_put_back(
    tmp_path, onto_another_drive
):
    # Its relative path has no relative one from there; once it is put back, the
    # document's later writes keep it absolute, as they keep its own (#555, a).
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(writable(tla.read(EVERY_KIND))))
    doc = tla.read(piece)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    absolute = os.path.normpath(piece.parent / pdf.attrs["path"]).replace("\\", "/")
    del doc.timelines[pdf.id]

    with paths.following(doc, [pdf], onto_another_drive.target("other-584")):
        onto_another_drive(doc, "other-584")
    doc.timelines[pdf.id] = pdf
    back = tmp_path / "back" / "piece.tla"
    back.parent.mkdir()
    tla.write(back, doc)

    assert pdf.attrs["path"] == absolute
    assert written_in(back, "pdf") == absolute


def test_a_held_timeline_doesnt_follow_a_write_that_fails(tmp_path):
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    piece.write_bytes(tla.canonical_bytes(writable(tla.read(EVERY_KIND))))
    doc = tla.read(piece)
    (pdf,) = [tl for tl in doc.timelines.values() if tl.kind == "pdf"]
    del doc.timelines[pdf.id]
    # Deeper, so that a write there would rebase its path.
    target = tmp_path / "other" / "deeper" / "piece.tla"
    target.parent.mkdir(parents=True)

    with pytest.raises(tla.FileChanged):
        with paths.following(doc, [pdf], target):
            tla.write(target, doc, expect="0" * 64)

    assert pdf.attrs["path"] == "../scores/Ständchen.pdf"
    assert doc._absolute_as_written == ()


# SC-002: a file read and written twice keeps its bytes, every golden file and
# every old one, once migrated, and an old one whose paths reading keeps absolute.

GOLDEN = sorted((TLA / "golden").glob("*.tla"))
OLD = sorted((TLA / "old").glob("*.tla"))


def needs_harmony(doc):
    if cant_check(doc) is not None:
        pytest.importorskip("music21", reason="writes harmonies: the harmony extra")


def written_twice(piece):
    """The bytes of the file at `piece`, once read and written, then read and
    written again, and written again by the document that followed it; the three
    must be one."""
    doc = tla.read(piece)
    needs_harmony(doc)
    tla.write(piece, doc, expect=doc.fingerprint)
    first = piece.read_bytes()
    tla.write(piece, tla.read(piece), expect=tla.fingerprint(piece))
    assert piece.read_bytes() == first
    tla.write(piece, doc, expect=tla.fingerprint(piece))
    assert piece.read_bytes() == first
    return first


@pytest.mark.parametrize("source", GOLDEN + OLD, ids=lambda path: path.name)
def test_a_file_read_and_written_twice_keeps_its_bytes(tmp_path, source):
    piece = tmp_path / "corpus" / source.name
    piece.parent.mkdir()
    shutil.copyfile(source, piece)

    first = written_twice(piece)

    if source in GOLDEN:
        assert first == source.read_bytes()


@pytest.mark.parametrize("source", OLD, ids=lambda path: path.name)
def test_an_old_file_whose_paths_reading_keeps_absolute_keeps_its_bytes(
    tmp_path, source
):
    # Its paths are of Windows form, which a `file_path` of POSIX form can't be
    # related to: they stay absolute (#530).
    content = json.loads(source.read_bytes())
    content["file_path"] = "/home/someone-584/corpus/piece.tla"
    piece = tmp_path / "corpus" / source.name
    piece.parent.mkdir()
    piece.write_text(json.dumps(content), encoding="utf-8")

    written_twice(piece)

    if content.get("media_path", "").startswith("C:/"):
        kept = dict(paths.absolute_paths(tla.read(piece)))
        assert kept["/media/path"] == content["media_path"]
