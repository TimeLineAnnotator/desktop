"""A file another program has locked, so that it can't be read (FR-042;
TimeLineAnnotator/project-management#683, b).

The check before a write can't compare a file it can't open. When that is because
another program holds it, on Windows, the check is retried as briefly as the rename
is, and then raises `FileInUse`, before anything is compared or written: only a file
that can be opened, or that the person has no permission to read, is told apart from
the one expected. The files are really held, by another program, in each of Windows'
sharing modes; the retry is tested on every system too, with the system replaced."""

import errno
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from hold_file import READABLE, UNREADABLE, Held, no_permission_to_read

from tilia_core import state, tla
from tilia_core.commands import migrate as migrate_command
from tilia_core.tla import folder as folder_module
from tilia_core.tla import in_use, writer

TESTS = Path(__file__).parent
EVERY_KIND = TESTS / "golden" / "every-kind.tla"
OLD = TESTS / "old"

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="only Windows has files that can't be opened"
)
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root may read any file"
)


def listing(folder):
    return sorted(p.name for p in Path(folder).iterdir())


def without_harmonies(doc):
    """`doc` without its harmony timeline: writing one needs the `harmony` extra."""
    doc.timelines = {
        key: timeline
        for key, timeline in doc.timelines.items()
        if timeline.kind != "harmony"
    }
    return doc


@pytest.fixture
def piece(tmp_path):
    """A `.tla` file in a folder of its own, written without `tla.write`."""
    folder = tmp_path / "corpus"
    folder.mkdir()
    path = folder / "piece.tla"
    path.write_bytes(tla.canonical_bytes(without_harmonies(tla.read(EVERY_KIND))))
    return path


@pytest.fixture
def theirs(tmp_path):
    """Another version of the file, as the other program would leave it."""
    doc = without_harmonies(tla.read(EVERY_KIND))
    doc.metadata["note"] = "theirs"
    path = tmp_path / "theirs.tla"
    path.write_bytes(tla.canonical_bytes(doc))
    return path


@pytest.fixture
def mine(piece):
    """The document read from `piece`, edited, with the fingerprint it was read with."""
    doc = tla.read(piece)
    read = doc.fingerprint
    doc.metadata["note"] = "mine"
    return doc, read


# The write's check.


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE + READABLE)
def test_a_file_held_open_throughout_is_in_use(piece, mine, mode):
    doc, read = mine
    before = piece.read_bytes()

    with Held(piece, mode), pytest.raises(tla.FileInUse) as caught:
        tla.write(piece, doc, expect=read)

    assert caught.value.path == piece
    assert str(caught.value) == (
        "piece.tla: in use by another program; nothing was written"
    )
    assert isinstance(caught.value, PermissionError)
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]
    assert doc.fingerprint == read  # the document didn't follow it


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE + READABLE)
def test_it_is_written_once_it_is_free(piece, mine, mode):
    doc, read = mine

    with Held(piece, mode) as holder:
        timer = threading.Timer(0.3, holder.release)
        timer.start()
        try:
            tla.write(piece, doc, expect=read)
        finally:
            timer.join()

    assert piece.read_bytes() == tla.canonical_bytes(doc)
    assert listing(piece.parent) == ["piece.tla"]


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE)
def test_a_change_made_while_it_was_locked_is_a_change(piece, theirs, mine, mode):
    # The program changes it just before letting it go, while it is retried.
    doc, read = mine

    with Held(piece, mode, then_write=theirs) as holder:
        timer = threading.Timer(0.3, holder.release)
        timer.start()
        try:
            with pytest.raises(tla.FileChanged) as caught:
                tla.write(piece, doc, expect=read)
        finally:
            timer.join()

    assert caught.value.expected == read
    assert caught.value.found == tla.fingerprint(theirs)
    assert piece.read_bytes() == theirs.read_bytes()
    assert listing(piece.parent) == ["piece.tla"]


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE)
def test_no_check_asks_for_it_when_no_file_is_expected(piece, mine, mode):
    # A file is there where none was expected: that is said at once, held or not.
    doc, _ = mine
    start = time.monotonic()

    with Held(piece, mode), pytest.raises(tla.FileChanged) as caught:
        tla.write(piece, doc, expect=tla.ABSENT)

    assert time.monotonic() - start < 10
    assert caught.value.expected is None
    assert caught.value.found is None


@windows_only
def test_a_lock_is_retried_for_as_long_as_the_rename_is(piece, mine, monkeypatch):
    doc, read = mine
    monkeypatch.setattr(state, "_REPLACE_RETRY_TIMEOUT", 0.4)
    start = time.monotonic()

    with Held(piece, "none"), pytest.raises(tla.FileInUse):
        tla.write(piece, doc, expect=read)

    assert 0.4 <= time.monotonic() - start < 10


@windows_only
def test_a_write_with_no_expectation_isn_t_checked(piece, mine):
    # As before: the rename is refused, and retried, and the file is in use.
    doc, _ = mine
    before = piece.read_bytes()

    with Held(piece, "none"), pytest.raises(tla.FileInUse):
        tla.write(piece, doc)

    assert piece.read_bytes() == before


# Telling a lock from a refusal of permissions.


@pytest.fixture
def denied(piece):
    """`piece`, which this person may not read (Windows)."""
    with no_permission_to_read(piece):
        yield piece


@windows_only
def test_a_file_one_may_not_read_is_a_change_as_before(mine, denied):
    doc, read = mine
    start = time.monotonic()

    with pytest.raises(tla.FileChanged) as caught:
        tla.write(denied, doc, expect=read)

    assert caught.value.found is None
    assert time.monotonic() - start < 10


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE)
def test_windows_says_a_lock_is_one(piece, mode):
    with Held(piece, mode):
        assert in_use.held_by_another(piece)
    assert not in_use.held_by_another(piece)


@windows_only
@pytest.mark.parametrize("mode", READABLE)
def test_a_file_one_may_read_isnt_locked(piece, mode):
    with Held(piece, mode):
        assert not in_use.held_by_another(piece)


@windows_only
def test_bytes_locked_anywhere_in_a_file_make_it_locked(tmp_path):
    # Longer than is read at a time, the bytes at its end locked.
    path = tmp_path / "long.tla"
    path.write_bytes(b"x" * 300_000)

    with Held(path, "read+write+delete", lock_from=200_000):
        assert in_use.held_by_another(path)
        with pytest.raises(tla.FileInUse):
            in_use.read_bytes(path)
    assert not in_use.held_by_another(path)


@windows_only
def test_a_refusal_of_permissions_isnt_a_lock(denied):
    assert not in_use.held_by_another(denied)


@windows_only
@pytest.mark.parametrize("what", ["missing", "folder"])
def test_nothing_there_and_a_folder_arent_locked(tmp_path, what):
    path = tmp_path / "missing.tla" if what == "missing" else tmp_path
    assert not in_use.held_by_another(path)


@posix_only
@not_root
def test_on_other_systems_a_file_one_may_not_read_is_a_change_as_before(piece, mine):
    doc, read = mine
    os.chmod(piece, 0)
    try:
        with pytest.raises(tla.FileChanged) as caught:
            tla.write(piece, doc, expect=read)
        assert not in_use.held_by_another(piece)
    finally:
        os.chmod(piece, stat.S_IREAD | stat.S_IWRITE)
    assert caught.value.found is None


# The retry, on every system, with the system replaced.


class Opening:
    """`open` refused `refusals` times, then `content`'s bytes; and how it was asked."""

    def __init__(self, refusals, content=b"content"):
        self.refusals, self.content, self.calls = refusals, content, 0

    def __call__(self, path, mode):
        self.calls += 1
        if self.refusals:
            self.refusals -= 1
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
        return _Reader(self.content)


class _Reader:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def read(self):
        return self.content


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(state, "_IS_WINDOWS", True)
    monkeypatch.setattr(in_use, "held_by_another", lambda path: True)


def opens_as(monkeypatch, opening):
    monkeypatch.setattr(in_use, "open", opening, raising=False)
    return opening


def test_a_lock_is_tried_again_until_it_is_let_go(on_windows, monkeypatch):
    opening = opens_as(monkeypatch, Opening(refusals=3))

    assert in_use.read_bytes("piece.tla") == b"content"

    assert opening.calls == 4


def test_a_lock_that_lasts_is_in_use_once_the_retry_is_over(on_windows, monkeypatch):
    monkeypatch.setattr(state, "_REPLACE_RETRY_TIMEOUT", 0.3)
    opening = opens_as(monkeypatch, Opening(refusals=10**6))
    start = time.monotonic()

    with pytest.raises(tla.FileInUse) as caught:
        in_use.read_bytes(Path("corpus") / "piece.tla")

    assert 0.3 <= time.monotonic() - start < 10
    assert 1 < opening.calls < 10
    assert caught.value.path == Path("corpus") / "piece.tla"


def test_a_lock_let_go_between_the_refusal_and_the_look_is_read_again(
    on_windows, monkeypatch
):
    opening = opens_as(monkeypatch, Opening(refusals=1))
    monkeypatch.setattr(in_use, "held_by_another", lambda path: False)

    assert in_use.read_bytes("piece.tla") == b"content"

    assert opening.calls == 2


def test_a_lock_that_comes_back_is_tried_again(on_windows, monkeypatch):
    # Locked, let go and locked again, one look apart from the other.
    opening = opens_as(monkeypatch, Opening(refusals=4))
    answers = iter([True, False, True, False])
    monkeypatch.setattr(in_use, "held_by_another", lambda path: next(answers))

    assert in_use.read_bytes("piece.tla") == b"content"

    assert opening.calls == 5


def test_a_refusal_that_isnt_a_lock_is_the_systems(on_windows, monkeypatch):
    opening = opens_as(monkeypatch, Opening(refusals=10**6))
    monkeypatch.setattr(in_use, "held_by_another", lambda path: False)

    with pytest.raises(PermissionError) as caught:
        in_use.read_bytes("piece.tla")

    assert not isinstance(caught.value, tla.FileInUse)
    assert opening.calls == 2


def test_on_other_systems_the_systems_error_comes_at_once(monkeypatch):
    opening = opens_as(monkeypatch, Opening(refusals=10**6))
    monkeypatch.setattr(state, "_IS_WINDOWS", False)

    def never(path):
        raise AssertionError("asked whether it is locked")

    monkeypatch.setattr(in_use, "held_by_another", never)

    with pytest.raises(PermissionError) as caught:
        in_use.read_bytes("piece.tla")

    assert not isinstance(caught.value, tla.FileInUse)
    assert opening.calls == 1


def test_another_error_than_a_refusal_is_the_systems(on_windows, monkeypatch):
    def missing(path, mode):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    monkeypatch.setattr(in_use, "open", missing, raising=False)

    with pytest.raises(FileNotFoundError):
        in_use.read_bytes("piece.tla")


def test_the_error_names_the_path_given(piece, mine, monkeypatch):
    # Not the one the links and ".." in it lead to, which the check opens.
    doc, read = mine
    given = piece.parent / "x" / ".." / "piece.tla"

    def locked(path):
        raise tla.FileInUse(path)

    monkeypatch.setattr(writer, "read_bytes", locked)

    with pytest.raises(tla.FileInUse) as caught:
        tla.write(given, doc, expect=read)

    assert caught.value.path == given
    assert caught.value.__cause__.path == Path(os.path.realpath(piece))


def test_a_file_is_read_whole(tmp_path):
    path = tmp_path / "piece.tla"
    path.write_bytes(b"\x00\r\n" * 100_000)

    assert in_use.read_bytes(path) == b"\x00\r\n" * 100_000


# `tilia migrate`'s *in use* list.


@pytest.fixture
def corpus(tmp_path):
    """Two old files, `held.tla` and `other.tla`."""
    folder = tmp_path / "corpus"
    folder.mkdir()
    for name in ("held.tla", "other.tla"):
        (folder / name).write_bytes((OLD / "0.0.96.tla").read_bytes())
    return folder


def by_path(report):
    return {result.path: result for result in report.files}


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE)
@pytest.mark.parametrize("apply", [False, True], ids=["listing", "apply"])
def test_migrate_lists_a_file_locked_before_it_is_read(corpus, mode, apply):
    held = corpus / "held.tla"
    before = held.read_bytes()

    with Held(held, mode):
        report = tla.migrate_folder(corpus, apply=apply)

    result = by_path(report)["held.tla"]
    assert result.outcome == "in_use"
    assert result.reason == "in use by another program"
    assert held.read_bytes() == before
    assert by_path(report)["other.tla"].outcome == (
        "migrated" if apply else "would_migrate"
    )
    assert report.status == 1


@windows_only
@pytest.mark.parametrize("mode", UNREADABLE)
def test_migrate_lists_a_file_locked_between_its_read_and_its_write(
    corpus, mode, monkeypatch
):
    held = corpus / "held.tla"
    before = held.read_bytes()
    write = folder_module.write
    holders = []

    def locked_now(target, doc, **kwargs):
        if Path(target).name == "held.tla" and not holders:
            holders.append(Held(target, mode))
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", locked_now)
    try:
        report = tla.migrate_folder(corpus, apply=True)
    finally:
        for holder in holders:
            holder.__exit__()

    result = by_path(report)["held.tla"]
    assert result.outcome == "in_use"
    assert result.reason == "in use by another program"
    assert held.read_bytes() == before
    assert by_path(report)["other.tla"].outcome == "migrated"
    assert listing(corpus) == ["held.tla", "other.tla"]


@windows_only
def test_migrate_migrates_a_file_let_go_while_it_waits(corpus):
    # Another read comes after a pause, as for any file that couldn't be read.
    held = corpus / "held.tla"

    with Held(held, "none") as holder:
        timer = threading.Timer(0.1, holder.release)
        timer.start()
        try:
            report = tla.migrate_folder(corpus, apply=True)
        finally:
            timer.join()

    assert by_path(report)["held.tla"].outcome == "migrated"


@windows_only
def test_migrate_says_so_in_its_in_use_list(corpus, capsys):
    with Held(corpus / "held.tla", "none"):
        status = migrate_command.main([str(corpus), "--apply"])

    out = capsys.readouterr().out
    assert status == 1
    assert "In use by another program: 1 file\n  held.tla\n" in out
    assert "Left alone: 0 files\n" in out


@windows_only
def test_migrate_still_says_a_file_one_may_not_read_can_t_be_read(
    corpus, capsys, tmp_path
):
    with no_permission_to_read(corpus / "held.tla"):
        status = migrate_command.main([str(corpus), "--apply"])

    out = capsys.readouterr().out
    assert status == 1
    assert "In use by another program" not in out
    assert "held.tla" in out and "can't read: Permission denied" in out


def test_migrate_lists_a_locked_file_by_the_systems_word_only_on_windows(
    corpus, monkeypatch
):
    # On every system: what Windows says of the file decides, after the last try.
    real = folder_module.read_with_migration

    def refused(path):
        if Path(path).name == "held.tla":
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
        return real(path)

    monkeypatch.setattr(folder_module, "read_with_migration", refused)
    monkeypatch.setattr(folder_module, "held_by_another", lambda path: True)
    locked = by_path(tla.migrate_folder(corpus))["held.tla"]
    monkeypatch.setattr(folder_module, "held_by_another", lambda path: False)
    refused_ = by_path(tla.migrate_folder(corpus))["held.tla"]

    assert locked.outcome == "in_use"
    assert refused_.outcome == "unreadable"
    assert refused_.reason == "can't read: Permission denied"
