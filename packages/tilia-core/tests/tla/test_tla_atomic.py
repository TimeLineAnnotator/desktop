"""Atomic writes (FR-040, FR-041, FR-044, FR-045; SC-005).

A write that fails at any step, or a process killed during one, leaves the
file as it was, and no temporary file but one a crash left, which
`is_temporary` names. On Windows, a file another program holds open is
retried, then reported as `FileInUse`. A link stays a link, and the file
keeps its permission bits.

Failures are injected through `os`, which `tilia_core.state.atomic_write`,
the core's one atomic write, calls: `os.fdopen` for the temporary file's
write and flush, `os.fsync` and `os.replace`."""

import errno
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tilia_core import state, tla

EVERY_KIND = Path(__file__).parent / "golden" / "every-kind.tla"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="only Windows refuses to replace an open file"
)
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root may write any file",
)


def listing(folder):
    return sorted(p.name for p in Path(folder).iterdir())


def edited(note="edited"):
    doc = tla.read(EVERY_KIND)
    doc.metadata["note"] = note
    return doc


@pytest.fixture
def piece(tmp_path):
    """A `.tla` file in a folder of its own, written without `tla.write`."""
    folder = tmp_path / "corpus"
    folder.mkdir()
    path = folder / "piece.tla"
    path.write_bytes(tla.canonical_bytes(tla.read(EVERY_KIND)))
    return path


def test_a_write_replaces_the_file_and_leaves_nothing_else(piece):
    doc = edited()
    tla.write(piece, doc)
    assert piece.read_bytes() == tla.canonical_bytes(doc)
    assert listing(piece.parent) == ["piece.tla"]


# Failures injected at each step.


class FailingFile:
    """The temporary file, failing at one step. At the write, half the data
    reaches the disk first."""

    def __init__(self, file, step, error):
        self.file = file
        self.step = step
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.file.close()

    def write(self, data):
        if self.step == "write":
            self.file.write(data[: len(data) // 2])
            self.file.flush()
            raise self.error
        return self.file.write(data)

    def flush(self):
        if self.step == "flush":
            raise self.error
        self.file.flush()

    def fileno(self):
        return self.file.fileno()


def inject(monkeypatch, step, error):
    if step in ("write", "flush"):
        real = os.fdopen

        def fdopen(fd, *args, **kwargs):
            return FailingFile(real(fd, *args, **kwargs), step, error)

        monkeypatch.setattr(os, "fdopen", fdopen)
    elif step == "sync":

        def fsync(fd):
            raise error

        monkeypatch.setattr(os, "fsync", fsync)
    else:

        def replace(src, dst):
            raise error

        monkeypatch.setattr(os, "replace", replace)


STEPS = ["write", "flush", "sync", "rename"]
ERRORS = {
    "disk-full": lambda: OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)),
    "interrupted": KeyboardInterrupt,
}


# Each failure is injected in a monkeypatch of its own, undone before the
# folder is looked at: undoing the test's `monkeypatch` would also undo what
# fixtures patched with it.


@pytest.mark.parametrize("error", ERRORS.values(), ids=ERRORS.keys())
@pytest.mark.parametrize("step", STEPS)
def test_a_write_that_fails_at_any_step_leaves_the_file_as_it_was(piece, step, error):
    before = piece.read_bytes()
    raised = error()
    with pytest.MonkeyPatch.context() as failing:
        inject(failing, step, raised)
        with pytest.raises(type(raised)):
            tla.write(piece, edited())
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]


@pytest.mark.parametrize("step", STEPS)
def test_a_new_file_whose_write_fails_is_not_there(tmp_path, step):
    with pytest.MonkeyPatch.context() as failing:
        inject(failing, step, OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)))
        with pytest.raises(OSError):
            tla.write(tmp_path / "new.tla", edited())
    assert listing(tmp_path) == []


def test_a_document_the_writer_refuses_leaves_the_file_as_it_was(piece):
    before = piece.read_bytes()
    doc = edited()
    doc.media_length = float("nan")
    with pytest.raises(ValueError, match="/media/length"):
        tla.write(piece, doc)
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]


# Temporary files.


def test_the_temporary_file_is_hidden_beside_the_file_and_named_by_is_temporary(
    piece, monkeypatch
):
    renamed = []
    real = os.replace

    def replace(src, dst):
        renamed.append((Path(src), Path(dst)))
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    tla.write(piece, edited())
    [(src, dst)] = renamed
    assert os.path.samefile(src.parent, piece.parent)
    assert os.path.samefile(dst, piece)
    assert src.name.startswith(".")
    assert not src.name.lower().endswith(".tla")
    assert tla.is_temporary(src.name)


@pytest.mark.parametrize(
    "name",
    [".piece.tla.0123abcd.tmp", ".Op2No1-1.tla.ffffffff.tmp", ". .00000000.tmp"],
)
def test_is_temporary_names_the_writers_temporary_files(name):
    assert tla.is_temporary(name)


@pytest.mark.parametrize(
    "name",
    [
        "piece.tla",
        ".piece.tla",
        "piece.tla.0123abcd.tmp",  # not hidden
        ".piece.tla.0123ABCD.tmp",  # not as written
        ".piece.tla.0123abc.tmp",
        ".piece.tla.0123abcde.tmp",
        ".piece.tla.0123abcd.tmp.tla",
        ".piece.tla.0123abcd.tmp\n",
        "..0123abcd.tmp",
    ],
)
def test_is_temporary_names_nothing_else(name):
    assert not tla.is_temporary(name)


def test_the_temporary_pattern_is_what_is_temporary_uses():
    assert tla.TEMPORARY_PATTERN == r"^\..+\.[0-9a-f]{8}\.tmp$"


# A process killed during a write.

STALL = """
import os, sys, time
from tilia_core import tla

step, target, source = sys.argv[1:]
doc = tla.read(source)


def stall(*args):
    print("stalled", flush=True)
    time.sleep(60)


class HalfWritten:
    def __init__(self, file):
        self.file = file

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.file.close()

    def write(self, data):
        self.file.write(data[: len(data) // 2])
        self.file.flush()
        stall()


if step == "write":
    real_fdopen = os.fdopen
    os.fdopen = lambda fd, *args: HalfWritten(real_fdopen(fd, *args))
elif step == "sync":
    os.fsync = stall
else:
    os.replace = stall
tla.write(target, doc)
"""


@pytest.mark.parametrize("step", ["write", "sync", "rename"])
def test_a_process_killed_during_a_write_leaves_the_file_whole(tmp_path, piece, step):
    before = piece.read_bytes()
    source = tmp_path / "source"
    source.mkdir()
    edited_file = source / "edited.tla"
    edited_file.write_bytes(tla.canonical_bytes(edited()))
    process = subprocess.Popen(
        [sys.executable, "-c", STALL, step, str(piece), str(edited_file)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = process.stdout.readline()
    finally:
        process.kill()
        _, err = process.communicate()
    assert line == "stalled\n", err
    assert piece.read_bytes() == before
    [left] = [name for name in listing(piece.parent) if name != piece.name]
    assert tla.is_temporary(left)
    assert not left.lower().endswith(".tla")


# A file another program holds open (Windows).

HOLD_OPEN = """
import sys

with open(sys.argv[1], "rb"):
    print("open", flush=True)
    sys.stdin.read()
"""


class HeldOpen:
    """Another process with the file open, as a sync client or a virus
    scanner may have it, until `release`."""

    def __init__(self, path):
        self.process = subprocess.Popen(
            [sys.executable, "-c", HOLD_OPEN, str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        assert self.process.stdout.readline() == "open\n"

    def release(self):
        self.process.stdin.close()
        self.process.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if self.process.poll() is None:
            self.release()


def count_renames(monkeypatch):
    calls = []
    real = os.replace

    def replace(src, dst):
        calls.append(dst)
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    return calls


@windows_only
def test_a_file_held_open_is_written_once_it_is_free(piece, monkeypatch):
    doc = edited()
    renames = count_renames(monkeypatch)
    with HeldOpen(piece) as holder:
        timer = threading.Timer(0.2, holder.release)
        timer.start()
        try:
            tla.write(piece, doc)
        finally:
            timer.join()
    assert piece.read_bytes() == tla.canonical_bytes(doc)
    assert len(renames) > 1
    assert listing(piece.parent) == ["piece.tla"]


@windows_only
def test_a_file_held_open_throughout_the_retry_is_reported_as_in_use(
    piece, monkeypatch
):
    before = piece.read_bytes()
    renames = count_renames(monkeypatch)
    with HeldOpen(piece), pytest.raises(tla.FileInUse) as caught:
        tla.write(piece, edited())
    assert isinstance(caught.value, PermissionError)
    assert caught.value.path == piece
    assert str(caught.value) == (
        "piece.tla: in use by another program; nothing was written"
    )
    assert len(renames) > 1
    assert piece.read_bytes() == before
    assert listing(piece.parent) == ["piece.tla"]


@windows_only
def test_a_temporary_file_held_open_throughout_the_retry_is_reported_as_in_use(
    piece, monkeypatch
):
    # A virus scanner or an indexer may open the new temporary file as soon
    # as it is written. Windows then refuses the rename with another error
    # than for a target held open: a sharing violation.
    before = piece.read_bytes()
    holders = []
    real = os.replace

    def replace(src, dst):
        if not holders:
            holders.append(HeldOpen(src))
        real(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    try:
        with pytest.raises(tla.FileInUse) as caught:
            tla.write(piece, edited())
    finally:
        for holder in holders:
            holder.release()
    assert caught.value.path == piece
    assert str(caught.value) == (
        "piece.tla: in use by another program; nothing was written"
    )
    assert caught.value.__cause__.winerror == 32
    assert piece.read_bytes() == before
    # A temporary file held open can't be removed either: it stays, as one a
    # crash leaves, and is_temporary names it.
    others = [name for name in listing(piece.parent) if name != "piece.tla"]
    assert all(tla.is_temporary(name) for name in others)


def test_a_rename_refused_for_another_reason_raises_the_systems_error(
    piece, monkeypatch
):
    refused = PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    def replace(src, dst):
        raise refused

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(state, "_IS_WINDOWS", False)  # no retry
    with pytest.raises(PermissionError) as caught:
        tla.write(piece, edited())
    assert caught.value is refused


# Links and permissions.


def symlink_or_skip(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"can't make a symbolic link here: {error}")


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_a_link_stays_a_link_and_its_target_gets_the_content(tmp_path, relative):
    store = tmp_path / "store"
    store.mkdir()
    target = store / "piece.tla"
    target.write_bytes(tla.canonical_bytes(tla.read(EVERY_KIND)))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    link = corpus / "piece.tla"
    symlink_or_skip(Path("..", "store", "piece.tla") if relative else target, link)
    pointed_at = os.readlink(link)
    doc = edited()
    written = tla.write(link, doc)
    assert link.is_symlink()
    assert os.readlink(link) == pointed_at
    assert target.read_bytes() == tla.canonical_bytes(doc)
    assert listing(corpus) == ["piece.tla"]
    assert listing(store) == ["piece.tla"]
    assert tla.fingerprint(link) == written


@posix_only
@pytest.mark.parametrize("mode", [0o600, 0o640, 0o664, 0o755])
def test_a_write_keeps_the_files_permission_bits(piece, mode):
    piece.chmod(mode)
    tla.write(piece, edited())
    assert stat.S_IMODE(piece.stat().st_mode) == mode


@posix_only
def test_a_new_file_gets_the_permissions_the_umask_gives(tmp_path):
    old = os.umask(0o027)
    try:
        tla.write(tmp_path / "new.tla", edited())
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "new.tla").stat().st_mode) == 0o640


@posix_only
def test_a_link_keeps_its_targets_permission_bits(tmp_path):
    target = tmp_path / "piece.tla"
    target.write_bytes(tla.canonical_bytes(tla.read(EVERY_KIND)))
    target.chmod(0o600)
    link = tmp_path / "link.tla"
    symlink_or_skip(target, link)
    tla.write(link, edited())
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@not_root
def test_a_read_only_file_is_refused_with_the_systems_reason(piece):
    before = piece.read_bytes()
    piece.chmod(stat.S_IREAD)  # on Windows, the read-only attribute
    try:
        with pytest.raises(PermissionError) as caught:
            tla.write(piece, edited())
        assert piece.read_bytes() == before
    finally:
        piece.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert caught.value.errno == errno.EACCES
    assert caught.value.filename == str(piece)
    assert listing(piece.parent) == ["piece.tla"]


@not_root
def test_a_read_only_file_is_refused_before_the_rename_not_as_in_use(
    piece, monkeypatch
):
    renames = count_renames(monkeypatch)
    piece.chmod(stat.S_IREAD)
    try:
        with pytest.raises(PermissionError) as caught:
            tla.write(piece, edited())
    finally:
        piece.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert not isinstance(caught.value, tla.FileInUse)
    assert caught.value.errno == errno.EACCES
    assert renames == []


def test_a_folder_at_the_path_is_refused_before_anything_is_written(
    tmp_path, monkeypatch
):
    # As macOS and Linux refuse to open a folder for writing. On Windows,
    # the rename would be refused, retried and reported as if the file were
    # held open.
    folder = tmp_path / "piece.tla"
    folder.mkdir()
    renames = count_renames(monkeypatch)
    with pytest.raises(IsADirectoryError) as caught:
        tla.write(folder, edited())
    assert caught.value.errno == errno.EISDIR
    assert caught.value.filename == str(folder)
    assert renames == []
    assert listing(tmp_path) == ["piece.tla"]
    assert listing(folder) == []


@posix_only
@not_root
def test_a_folder_that_cant_be_written_to_is_refused_with_the_systems_reason(piece):
    before = piece.read_bytes()
    folder = piece.parent
    folder.chmod(0o500)
    try:
        with pytest.raises(PermissionError):
            tla.write(piece, edited())
        assert piece.read_bytes() == before
        assert listing(folder) == ["piece.tla"]
    finally:
        folder.chmod(0o700)
