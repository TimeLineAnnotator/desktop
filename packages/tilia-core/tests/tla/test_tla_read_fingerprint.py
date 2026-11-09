"""A document carries the fingerprint it was read with
(TimeLineAnnotator/project-management#415): `read` and `loads` set it from the
bytes they read, and `write` to what it wrote, so that a write can state the
version it read with no second read, on an old file too, whose
`fingerprint_of(doc)` isn't the file's (FR-043). It is never written to the file."""

import builtins
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import folder as folder_module
from tilia_core.tla import reader, writer

HERE = Path(__file__).parent
EVERY_KIND = HERE / "golden" / "every-kind.tla"
GOLDEN = sorted((HERE / "golden").glob("*.tla"))
OLD = sorted((HERE / "old").glob("*.tla"))
EVERY_FILE = GOLDEN + OLD
# An old file with no harmonies, which can be written without the `harmony` extra.
OLD_WITHOUT_HARMONIES = HERE / "old" / "0.7.0-osmd.tla"
# Where an old file stores a path as the migration doesn't.
OLD_WITH_PATHS = HERE / "old" / "0.6.0-s4-10.tla"


def file_id(path):
    return path.name


def without_harmonies(doc):
    """`doc` without its harmony timeline: writing one needs the `harmony` extra."""
    doc.timelines = {
        key: timeline
        for key, timeline in doc.timelines.items()
        if timeline.kind != "harmony"
    }
    return doc


@pytest.fixture(params=["current", "old"])
def piece(request, tmp_path):
    """A file of the current format and an old one, each writable."""
    path = tmp_path / "piece.tla"
    if request.param == "old":
        shutil.copyfile(OLD_WITHOUT_HARMONIES, path)
    else:
        doc = without_harmonies(tla.read(EVERY_KIND))
        path.write_bytes(tla.canonical_bytes(doc))
    return path


def changed_on_disk(path):
    """Change the file as another program would: a value that its fingerprint
    covers, in a file left in its own format."""
    content = json.loads(path.read_bytes())
    if content["version"].startswith("0."):
        content["media_metadata"]["title"] = "changed by another program"
    else:
        content["metadata"]["title"] = "changed by another program"
    path.write_text(json.dumps(content), "utf-8")


# What `read` and `loads` give


@pytest.mark.parametrize("path", EVERY_FILE, ids=file_id)
def test_read_gives_the_fingerprint_of_the_file(path):
    assert tla.read(path).fingerprint == tla.fingerprint(path)


@pytest.mark.parametrize("path", EVERY_FILE, ids=file_id)
def test_loads_gives_the_fingerprint_of_the_bytes(path):
    data = path.read_bytes()
    assert tla.loads(data).fingerprint == tla.fingerprint(path)
    assert tla.loads(data, path=path).fingerprint == tla.fingerprint(path)


def test_the_fingerprint_doesnt_change_with_where_the_file_is_read_from(tmp_path):
    # An old file's: its media and PDF paths as it stores them (FR-043).
    copy = tmp_path / "somewhere" / "else.tla"
    copy.parent.mkdir()
    shutil.copyfile(OLD_WITH_PATHS, copy)
    assert tla.read(copy).fingerprint == tla.read(OLD_WITH_PATHS).fingerprint


def old_file_with_media(folder, media):
    """An old file in `folder`, with `media` stored as an absolute path, which
    the migration makes relative."""
    piece = folder / "piece.tla"
    content = {
        "app_name": "TiLiA",
        "version": "0.7.0",
        "file_path": str(piece),
        "media_path": str(media),
        "media_metadata": {"title": "Piece", "media length": 60},
        "timelines": {},
    }
    piece.write_text(json.dumps(content), "utf-8")
    return piece


def test_an_old_files_fingerprint_is_the_files_not_its_migrations(tmp_path):
    media = tmp_path / "piece.wav"
    media.write_bytes(b"RIFF")
    piece = old_file_with_media(tmp_path, media)
    doc = tla.read(piece)
    assert doc.media_path == "piece.wav"  # made relative
    assert doc.fingerprint == tla.fingerprint(piece)
    assert doc.fingerprint != tla.fingerprint_of(doc)


@pytest.mark.parametrize("path", GOLDEN, ids=file_id)
def test_a_canonical_files_fingerprint_is_that_of_its_bytes(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert tla.read(path).fingerprint == digest


def test_a_file_in_another_form_has_the_fingerprint_of_its_canonical_bytes(tmp_path):
    # Line endings and a byte-order mark don't change a fingerprint (FR-043).
    canonical = EVERY_KIND.read_bytes()
    other = tmp_path / "other.tla"
    other.write_bytes(b"\xef\xbb\xbf" + canonical.replace(b"\n", b"\r\n"))
    assert tla.read(other).fingerprint == hashlib.sha256(canonical).hexdigest()


def test_the_rules_dont_stop_a_document_being_given_its_fingerprint(tmp_path):
    # A file that breaks a rule is read, with a warning, and written back.
    piece = tmp_path / "piece.tla"
    doc = without_harmonies(tla.read(EVERY_KIND))
    doc.media_length = -1
    content = tla.canonical_bytes(doc)
    piece.write_bytes(content)
    read = tla.read(piece)
    assert read.warnings
    assert read.fingerprint == hashlib.sha256(content).hexdigest()


def test_a_document_built_in_memory_has_none():
    assert tla.new_document().fingerprint is None
    built = tla.Document(document_id=tla.new_id(), format_version=tla.FORMAT_VERSION)
    assert built.fingerprint is None


# It stays out of the file


@pytest.mark.parametrize("path", EVERY_FILE, ids=file_id)
def test_it_is_never_written_to_the_file(path):
    doc = tla.read(path)
    written = tla.canonical_bytes(doc)
    assert b'"fingerprint"' not in written
    assert doc.fingerprint.encode() not in written


def test_it_changes_nothing_in_what_is_written():
    doc = tla.read(EVERY_KIND)
    before = tla.canonical_bytes(doc)
    doc.fingerprint = "something else"
    assert tla.canonical_bytes(doc) == before
    assert tla.fingerprint_of(doc) == hashlib.sha256(before).hexdigest()


# What `write` makes of it


def test_write_sets_it_to_what_it_wrote(piece):
    doc = tla.read(piece)
    doc.metadata["note"] = "edited"
    written = tla.write(piece, doc)
    assert doc.fingerprint == written == tla.fingerprint(piece)
    assert doc.fingerprint == hashlib.sha256(piece.read_bytes()).hexdigest()


def test_a_document_built_in_memory_has_it_once_written(tmp_path):
    doc = tla.new_document()
    written = tla.write(tmp_path / "new.tla", doc)
    assert doc.fingerprint == written


def test_a_save_as_gives_it_the_new_files(piece, tmp_path):
    doc = tla.read(piece)
    before = doc.fingerprint
    target = tmp_path / "elsewhere.tla"
    doc.metadata["note"] = "saved as"
    written = tla.write(target, doc, expect=tla.ABSENT)
    assert doc.fingerprint == written == tla.fingerprint(target)
    assert doc.fingerprint != before


def test_a_failed_write_leaves_it_as_it_was(piece):
    doc = tla.read(piece)
    before = doc.fingerprint
    changed_on_disk(piece)
    with pytest.raises(tla.FileChanged):
        tla.write(piece, doc, expect=doc.fingerprint)
    assert doc.fingerprint == before


def test_a_write_refused_for_its_content_leaves_it_as_it_was(piece):
    doc = tla.read(piece)
    before = doc.fingerprint
    doc.metadata["note"] = float("nan")
    with pytest.raises(ValueError):
        tla.write(piece, doc)
    assert doc.fingerprint == before


# A write that states it


def test_a_file_unchanged_since_it_was_read_is_written(piece):
    doc = tla.read(piece)
    doc.metadata["note"] = "edited"
    tla.write(piece, doc, expect=doc.fingerprint)
    assert tla.read(piece).metadata["note"] == "edited"


def test_a_file_changed_since_it_was_read_isnt_overwritten(piece):
    doc = tla.read(piece)
    doc.metadata["note"] = "edited"
    changed_on_disk(piece)
    theirs = piece.read_bytes()
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, doc, expect=doc.fingerprint)
    assert piece.read_bytes() == theirs
    assert caught.value.expected == doc.fingerprint
    assert caught.value.found == tla.fingerprint(piece)


def test_a_file_changed_since_it_was_written_isnt_overwritten(piece):
    doc = tla.read(piece)
    doc.metadata["note"] = "first"
    tla.write(piece, doc, expect=doc.fingerprint)
    changed_on_disk(piece)
    theirs = piece.read_bytes()
    doc.metadata["note"] = "second"
    with pytest.raises(tla.FileChanged):
        tla.write(piece, doc, expect=doc.fingerprint)
    assert piece.read_bytes() == theirs


def test_two_writes_in_a_row_each_state_the_one_before(piece):
    doc = tla.read(piece)
    for note in ("first", "second", "third"):
        doc.metadata["note"] = note
        tla.write(piece, doc, expect=doc.fingerprint)
    assert tla.read(piece).metadata["note"] == "third"


def test_a_file_removed_since_it_was_read_isnt_written(piece):
    doc = tla.read(piece)
    piece.unlink()
    with pytest.raises(tla.FileChanged):
        tla.write(piece, doc, expect=doc.fingerprint)
    assert not piece.exists()


def test_an_old_file_whose_media_came_since_it_was_read_is_still_the_one_read(tmp_path):
    # Its fingerprint takes the paths as the file stores them (FR-043).
    media = tmp_path / "piece.wav"
    piece = old_file_with_media(tmp_path, media)
    doc = tla.read(piece)
    media.write_bytes(b"RIFF")
    tla.write(piece, doc, expect=doc.fingerprint)
    assert json.loads(piece.read_bytes())["version"] == tla.FORMAT_VERSION


def test_a_file_in_another_form_can_be_written_stating_it(tmp_path):
    other = tmp_path / "other.tla"
    doc = without_harmonies(tla.read(EVERY_KIND))
    other.write_bytes(tla.canonical_bytes(doc).replace(b"\n", b"\r\n"))
    read = tla.read(other)
    tla.write(other, read, expect=read.fingerprint)
    assert b"\r\n" not in other.read_bytes()


# No second read


def test_read_opens_the_file_once(piece, monkeypatch):
    opened = []
    real = builtins.open

    def counting(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and Path(file) == piece:
            opened.append(file)
        return real(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting)
    assert tla.read(piece).fingerprint is not None
    assert len(opened) == 1


@pytest.mark.parametrize("path", OLD, ids=file_id)
def test_an_old_file_is_parsed_and_migrated_once(path, monkeypatch):
    parsed, migrated = [], []
    parse, migrate = reader.parse, reader.migrate

    def counting_parse(*args, **kwargs):
        parsed.append(args)
        return parse(*args, **kwargs)

    def counting_migrate(*args, **kwargs):
        migrated.append(args)
        return migrate(*args, **kwargs)

    monkeypatch.setattr(reader, "parse", counting_parse)
    monkeypatch.setattr(reader, "migrate", counting_migrate)
    assert tla.read(path).fingerprint is not None
    assert (len(parsed), len(migrated)) == (1, 1)


@pytest.mark.parametrize("path", EVERY_FILE, ids=file_id)
def test_a_file_is_checked_once_when_it_is_read(path, monkeypatch):
    # The fingerprint takes no second check: a read is what SC-004 counts.
    expected = tla.fingerprint(path)

    def refuse(*args, **kwargs):
        raise AssertionError("checked again")

    monkeypatch.setattr(writer, "check", refuse)
    assert tla.read(path).fingerprint == expected


def test_a_fingerprint_taken_while_reading_is_of_the_bytes_read(piece, monkeypatch):
    # What the check before saving is for: a change right after the one read
    # isn't taken for the version read, as a second read would take it.
    before = tla.fingerprint(piece)
    parse = reader.parse

    def then_changed(*args, **kwargs):
        content = parse(*args, **kwargs)
        changed_on_disk(piece)
        return content

    monkeypatch.setattr(reader, "parse", then_changed)
    doc = tla.read(piece)
    monkeypatch.setattr(reader, "parse", parse)
    assert doc.fingerprint == before
    assert tla.fingerprint(piece) != before


# `tilia migrate --apply`


def test_migrate_states_the_fingerprint_the_document_was_read_with(
    tmp_path, monkeypatch
):
    piece = tmp_path / "piece.tla"
    shutil.copyfile(OLD_WITHOUT_HARMONIES, piece)
    expected = tla.fingerprint(piece)
    stated = []
    write = folder_module.write

    def recorded(path, doc, *, expect=None):
        stated.append(expect)
        return write(path, doc, expect=expect)

    monkeypatch.setattr(folder_module, "write", recorded)
    report = tla.migrate_folder(tmp_path, apply=True)
    assert [file.outcome for file in report.files] == [tla.Outcome.MIGRATED]
    assert stated == [expected]


def test_migrate_has_no_fingerprint_of_its_own(tmp_path, monkeypatch):
    # An old file is migrated twice: when it is read, and by the write's own
    # check of what is on disk, since an old file's bytes aren't its canonical
    # bytes. Not a third time to compute what to state.
    piece = tmp_path / "piece.tla"
    shutil.copyfile(OLD_WITHOUT_HARMONIES, piece)
    migrated = []
    migrate = reader.migrate

    def counting(*args, **kwargs):
        migrated.append(args)
        return migrate(*args, **kwargs)

    monkeypatch.setattr(reader, "migrate", counting)
    report = tla.migrate_folder(tmp_path, apply=True)
    assert [file.outcome for file in report.files] == [tla.Outcome.MIGRATED]
    assert len(migrated) == 2


def test_migrate_leaves_alone_a_file_changed_after_it_was_read(tmp_path, monkeypatch):
    piece = tmp_path / "piece.tla"
    shutil.copyfile(OLD_WITHOUT_HARMONIES, piece)
    read = folder_module.read_with_migration

    def then_changed(path):
        result = read(path)
        changed_on_disk(Path(path))
        return result

    monkeypatch.setattr(folder_module, "read_with_migration", then_changed)
    report = tla.migrate_folder(tmp_path, apply=True)
    assert [file.outcome for file in report.files] == [tla.Outcome.CHANGED_SINCE_READ]
    assert json.loads(piece.read_bytes())["version"].startswith("0.")
