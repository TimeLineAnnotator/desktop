"""Expected fingerprints (FR-042, FR-043; SC-006).

A write may state what it expects to find: the fingerprint of the version it
read, or `ABSENT` for no file. When the file on disk is something else (it
changed, was deleted, became unreadable, or was created since), nothing is
written and `FileChanged` says so. A fingerprint is the SHA-256 of the file's
canonical bytes, in lower-case hexadecimal, so line endings, a byte-order
mark or another key order don't change it."""

import codecs
import hashlib
import json
import re
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import reader

EVERY_KIND = Path(__file__).parent / "golden" / "every-kind.tla"


def listing(folder):
    return sorted(p.name for p in Path(folder).iterdir())


def edited(note="edited"):
    # Read from nowhere, so that its relative media paths are written as they
    # are into any folder (FR-033).
    doc = tla.loads(EVERY_KIND.read_bytes())
    doc.metadata["note"] = note
    return doc


@pytest.fixture
def piece(tmp_path):
    """A `.tla` file in a folder of its own, written without `tla.write`."""
    path = tmp_path / "piece.tla"
    path.write_bytes(tla.canonical_bytes(tla.read(EVERY_KIND)))
    return path


# The fingerprint.


def test_write_returns_the_fingerprint_of_what_it_wrote(tmp_path):
    path = tmp_path / "piece.tla"
    doc = edited()
    written = tla.write(path, doc)
    assert re.fullmatch("[0-9a-f]{64}", written)
    assert written == hashlib.sha256(tla.canonical_bytes(doc)).hexdigest()
    assert written == hashlib.sha256(path.read_bytes()).hexdigest()
    assert written == tla.fingerprint(path)
    assert written == tla.fingerprint_of(doc)


def test_the_fingerprint_is_that_of_the_canonical_bytes(piece):
    assert tla.fingerprint(piece) == hashlib.sha256(piece.read_bytes()).hexdigest()
    assert tla.fingerprint(piece) == tla.fingerprint_of(tla.read(piece))


def test_another_edit_gives_another_fingerprint(piece):
    assert tla.fingerprint_of(edited("one")) != tla.fingerprint_of(edited("two"))
    assert tla.fingerprint_of(edited()) != tla.fingerprint(piece)


def with_value(where, key, value):
    """every-kind.tla with `key` set to `value` on its first component of the
    kind `where`, or on its first hierarchy timeline; read from nowhere, as
    `edited` reads it."""
    doc = tla.loads(EVERY_KIND.read_bytes())
    timeline = next(tl for tl in doc.timelines.values() if tl.kind == "hierarchy")
    if where == "timeline":
        setattr(timeline, key, value)
        return doc
    component = next(
        c
        for tl in doc.timelines.values()
        for c in tl.components.values()
        if c.kind == where
    )
    component.attrs[key] = value
    return doc


@pytest.mark.parametrize(
    "where, key, integer",
    [("hierarchy", "level", 2), ("harmony", "step", 0), ("timeline", "ordinal", 2)],
    ids=["a level", "a step, at its default", "an ordinal"],
)
def test_an_integer_given_as_a_float_is_written_and_fingerprinted_as_the_integer(
    tmp_path, where, key, integer
):
    # The reader reads an integer written as 1.0 as the integer 1, so the
    # writer writes 1, left out where it is the default, as reading the file
    # and writing it again would. Otherwise the fingerprint written wouldn't
    # be the file's, and the next write that expects it would be refused.
    path = tmp_path / "piece.tla"
    doc = with_value(where, key, float(integer))
    as_integer = tla.canonical_bytes(with_value(where, key, integer))
    written = tla.write(path, doc)
    assert path.read_bytes() == as_integer
    assert tla.canonical_bytes(doc) == as_integer
    assert written == tla.fingerprint(path)
    assert written == tla.fingerprint_of(doc)
    assert tla.write(path, doc, expect=written) == written


def with_crlf(data):
    return data.replace(b"\n", b"\r\n")


def with_bom(data):
    return codecs.BOM_UTF8 + data


def in_another_key_order(data):
    """Every object's keys reversed, but metadata's: the order of its fields
    is content, which the writer keeps (layout.md, *Order*)."""

    def reordered(value, key=None):
        if isinstance(value, dict):
            items = [(k, reordered(v, k)) for k, v in value.items()]
            return dict(items if key == "metadata" else reversed(items))
        if isinstance(value, list):
            return [reordered(item) for item in value]
        return value

    content = reordered(json.loads(data))
    return json.dumps(content, indent=4, ensure_ascii=True).encode("utf-8")


@pytest.mark.parametrize("variant", [with_crlf, with_bom, in_another_key_order])
def test_line_endings_a_bom_and_key_order_leave_the_fingerprint_unchanged(
    piece, variant
):
    expected = tla.fingerprint(piece)
    data = variant(piece.read_bytes())
    assert data != piece.read_bytes()
    piece.write_bytes(data)
    assert tla.fingerprint(piece) == expected


def files_parsed(monkeypatch):
    """The files the reader parses from now on."""
    parsed = []
    real = reader.parse

    def parse(data, **kwargs):
        parsed.append(data)
        return real(data, **kwargs)

    monkeypatch.setattr(reader, "parse", parse)
    return parsed


def with_bom_and_crlf(data):
    return with_bom(with_crlf(data))


@pytest.mark.parametrize(
    "variant", [with_crlf, with_bom, in_another_key_order, with_bom_and_crlf]
)
def test_a_file_whose_bytes_differ_only_in_form_is_still_the_one_expected(
    piece, variant, monkeypatch
):
    # Its bytes aren't its canonical bytes, so it is read to be compared.
    expected = tla.fingerprint(piece)
    piece.write_bytes(variant(piece.read_bytes()))
    doc = edited()
    parsed = files_parsed(monkeypatch)
    assert tla.write(piece, doc, expect=expected) == tla.fingerprint_of(doc)
    assert len(parsed) == 1
    assert piece.read_bytes() == tla.canonical_bytes(doc)


def test_a_file_the_core_wrote_is_compared_without_reading_it(piece, monkeypatch):
    # Its bytes are its canonical bytes, whose SHA-256 is its fingerprint.
    expected = tla.fingerprint(piece)
    doc = edited()
    parsed = files_parsed(monkeypatch)
    assert tla.write(piece, doc, expect=expected) == tla.fingerprint_of(doc)
    assert parsed == []
    assert piece.read_bytes() == tla.canonical_bytes(doc)


# Expecting a version.


def test_a_write_that_expects_the_version_on_disk_writes(piece):
    expected = tla.fingerprint(piece)
    doc = edited()
    written = tla.write(piece, doc, expect=expected)
    assert piece.read_bytes() == tla.canonical_bytes(doc)
    assert written == tla.fingerprint(piece)
    # The fingerprint written is the one the next write expects.
    tla.write(piece, edited("again"), expect=written)
    with pytest.raises(tla.FileChanged):
        tla.write(piece, edited("once more"), expect=written)


def test_a_file_changed_since_it_was_read_is_left_as_it_is(piece):
    doc = tla.read(piece)
    expected = tla.fingerprint(piece)
    other = tla.read(piece)
    other.metadata["note"] = "someone else's edit"
    tla.write(piece, other)
    before = piece.read_bytes()
    doc.metadata["note"] = "mine"
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, doc, expect=expected)
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]
    assert caught.value.path == piece
    assert caught.value.expected == expected
    assert caught.value.found == tla.fingerprint(piece)
    assert "changed since it was read" in str(caught.value)


def test_a_file_deleted_since_it_was_read_is_not_written_again(piece):
    expected = tla.fingerprint(piece)
    piece.unlink()
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, edited(), expect=expected)
    assert listing(piece.parent) == []
    assert caught.value.expected == expected
    assert caught.value.found is None


@pytest.mark.parametrize(
    "content", [b"", b"{not json", b'{"app_name": "something else"}\n']
)
def test_a_file_that_became_unreadable_is_left_as_it_is(piece, content):
    expected = tla.fingerprint(piece)
    piece.write_bytes(content)
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, edited(), expect=expected)
    assert piece.read_bytes() == content
    assert listing(piece.parent) == ["piece.tla"]
    assert caught.value.found is None


def test_a_link_is_checked_through_to_its_target(tmp_path, piece):
    link = tmp_path / "link.tla"
    try:
        link.symlink_to(piece)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"can't make a symbolic link here: {error}")
    expected = tla.fingerprint(link)
    tla.write(piece, edited("changed"))
    before = piece.read_bytes()
    with pytest.raises(tla.FileChanged):
        tla.write(link, edited(), expect=expected)
    assert piece.read_bytes() == before
    assert link.is_symlink()


# Expecting no file.


def test_a_write_that_expects_no_file_creates_one(tmp_path):
    path = tmp_path / "new.tla"
    doc = edited()
    written = tla.write(path, doc, expect=tla.ABSENT)
    assert path.read_bytes() == tla.canonical_bytes(doc)
    assert written == tla.fingerprint(path)


def test_a_file_created_since_is_left_as_it_is(piece):
    before = piece.read_bytes()
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, edited(), expect=tla.ABSENT)
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]
    assert caught.value.expected is None
    assert caught.value.found == tla.fingerprint(piece)
    assert "already exists" in str(caught.value)


def test_an_unreadable_file_there_is_left_as_it_is_too(tmp_path):
    path = tmp_path / "notes.tla"
    path.write_bytes(b"my notes, not a TiLiA file")
    with pytest.raises(tla.FileChanged) as caught:
        tla.write(path, edited(), expect=tla.ABSENT)
    assert path.read_bytes() == b"my notes, not a TiLiA file"
    assert caught.value.found is None


def test_a_write_that_expects_nothing_checks_nothing(piece):
    piece.write_bytes(b"{not json")
    doc = edited()
    tla.write(piece, doc)
    assert piece.read_bytes() == tla.canonical_bytes(doc)


# A document the reader would refuse.


@pytest.mark.parametrize("expect", ["0" * 64, tla.ABSENT], ids=["other", "ABSENT"])
def test_a_document_the_reader_would_refuse_is_refused_before_the_file_is_compared(
    piece, expect
):
    # Whatever the file on disk holds, the caller learns what is wrong with
    # the document, with the path it gave, and nothing is written.
    before = piece.read_bytes()
    doc = edited()
    doc.document_id = "piece-1"
    with pytest.raises(tla.UnreadableFile) as caught:
        tla.write(piece, doc, expect=expect)
    assert caught.value.place == "/document_id"
    assert caught.value.path == piece
    assert str(caught.value).startswith("piece.tla, line ")
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]
