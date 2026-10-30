"""Migrating a folder: which files it takes, what it reports, and that it
writes only old files, and only with `apply` (FR-100–FR-105)."""

import dataclasses
import json
import logging
import os
import shutil
import stat
import sys
import time
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import folder as folder_module
from tilia_core.tla import reader
from tilia_core.tla.folder import corpus_files, migrate_folder
from tilia_core.tla.model import FileResult, MigrationReport

HERE = Path(__file__).parent
OLD = HERE / "old"
BROKEN = HERE / "broken"
GOLDEN = HERE / "golden"

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="junctions are Windows' links to folders"
)

# The test folder's files a migration takes, in path order: two copies of
# one old file, a current file, one of a newer format, and in subfolders an
# unreadable file and old files of two more versions, one with its
# extension in capitals. Hidden files and folders, a link to a folder, a
# temporary file of the writer's and a file that isn't a `.tla` are there
# too, and left out.
TAKEN = [
    "a copy.tla",
    "a.tla",
    "current.tla",
    "newer.tla",
    "sub/broken.tla",
    "sub/deeper/OLD.TLA",
    "sub/old-0.6.tla",
]
OLD_FILES = ["a copy.tla", "a.tla", "sub/deeper/OLD.TLA", "sub/old-0.6.tla"]


def place(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source, Path):
        shutil.copyfile(source, path)
    else:
        path.write_bytes(source)


def can_symlink_folders(tmp_path):
    try:
        os.symlink(tmp_path, tmp_path / "probe", target_is_directory=True)
    except OSError:  # Windows, without the privilege to make one
        return False
    os.remove(tmp_path / "probe")
    return True


def link_folder(link, target):
    """A link to a folder: a symbolic link where the system lets us make one,
    else, on Windows, a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    place(root / "a.tla", OLD / "0.7.0.tla")
    place(root / "a copy.tla", OLD / "0.7.0.tla")
    place(root / "current.tla", GOLDEN / "every-kind.tla")
    place(root / "newer.tla", BROKEN / "newer-format.tla")
    place(root / "sub" / "broken.tla", BROKEN / "not-json.tla")
    place(root / "sub" / "old-0.6.tla", OLD / "0.6.0-s4-10.tla")
    place(root / "sub" / "deeper" / "OLD.TLA", OLD / "0.0.96.tla")
    place(root / "sub" / "notes.txt", b"not a TiLiA file\n")
    place(root / "sub" / "a.tla.bak", OLD / "0.5.15.tla")
    place(root / "sub" / ".a.tla.1a2b3c4d.tmp", OLD / "0.5.15.tla")
    place(root / ".hidden.tla", OLD / "0.5.15.tla")
    place(root / ".git" / "old.tla", OLD / "0.5.15.tla")
    place(tmp_path / "outside" / "linked.tla", OLD / "0.5.15.tla")
    link_folder(root / "linked", tmp_path / "outside")
    return root


@pytest.fixture
def clean_corpus(tmp_path):
    """Old files, a current one and one of a newer format: nothing that
    can't be read."""
    root = tmp_path / "clean"
    place(root / "a.tla", OLD / "0.7.0.tla")
    place(root / "current.tla", GOLDEN / "every-kind.tla")
    place(root / "newer.tla", BROKEN / "newer-format.tla")
    place(root / "sub" / "old.tla", OLD / "0.5.15.tla")
    return root


def snapshot(top):
    """Every file below `top`, the content and modification time of each."""
    files = {}
    for folder, _, names in os.walk(top):
        for name in names:
            path = Path(folder, name)
            files[path.relative_to(top).as_posix()] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return files


def outcomes(report):
    return [(f.path, f.outcome) for f in report.files]


def by_path(report):
    return {f.path: f for f in report.files}


def without_reading(document):
    """What a document holds, apart from what reading gave it: the version it
    was read from and the warnings."""
    return dataclasses.replace(document, format_version=tla.FORMAT_VERSION, warnings=[])


# The walk


def test_the_walk_takes_every_tla_below_the_folder_in_path_order(corpus):
    found = corpus_files(corpus)

    assert [relative for relative, _ in found] == TAKEN
    for relative, path in found:
        assert path == corpus / relative


def test_the_walk_leaves_out_hidden_files_and_folders(tmp_path):
    place(tmp_path / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / ".piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / ".hidden" / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / "sub" / ".hidden" / "piece.tla", OLD / "0.7.0.tla")

    assert [relative for relative, _ in corpus_files(tmp_path)] == ["piece.tla"]


def test_the_walk_takes_any_letter_case_of_the_extension(tmp_path):
    for name in ("a.tla", "b.TLA", "c.Tla", "d.tla.txt", "e.tl", "tla"):
        place(tmp_path / name, OLD / "0.7.0.tla")

    found = [relative for relative, _ in corpus_files(tmp_path)]

    assert found == ["a.tla", "b.TLA", "c.Tla"]


def test_the_walk_does_not_follow_a_symbolic_link_to_a_folder(tmp_path):
    if not can_symlink_folders(tmp_path):
        pytest.skip("this system doesn't let the tests make symbolic links")
    place(tmp_path / "outside" / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / "corpus" / "own.tla", OLD / "0.7.0.tla")
    os.symlink(
        tmp_path / "outside", tmp_path / "corpus" / "linked", target_is_directory=True
    )

    found = [relative for relative, _ in corpus_files(tmp_path / "corpus")]

    assert found == ["own.tla"]


@windows_only
def test_the_walk_does_not_follow_a_junction(tmp_path):
    import _winapi

    place(tmp_path / "outside" / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / "corpus" / "own.tla", OLD / "0.7.0.tla")
    _winapi.CreateJunction(
        str(tmp_path / "outside"), str(tmp_path / "corpus" / "linked")
    )

    found = [relative for relative, _ in corpus_files(tmp_path / "corpus")]

    assert found == ["own.tla"]


def test_the_walk_takes_a_link_to_a_file(tmp_path):
    place(tmp_path / "outside" / "piece.tla", OLD / "0.7.0.tla")
    (tmp_path / "corpus").mkdir()
    try:
        os.symlink(tmp_path / "outside" / "piece.tla", tmp_path / "corpus" / "link.tla")
    except OSError:
        pytest.skip("this system doesn't let the tests make symbolic links")

    found = [relative for relative, _ in corpus_files(tmp_path / "corpus")]

    assert found == ["link.tla"]


def test_the_walk_gives_paths_as_found_with_slashes(tmp_path):
    decomposed = unicodedata.normalize("NFD", "Bartók")
    place(tmp_path / decomposed / f"{decomposed}.tla", OLD / "0.7.0.tla")
    # As the system names them: on a file system that normalises names,
    # in its form.
    [folder] = os.listdir(tmp_path)
    [name] = os.listdir(tmp_path / folder)

    [(relative, path)] = corpus_files(tmp_path)

    assert relative == f"{folder}/{name}"
    assert (tmp_path / relative).exists()
    assert path == tmp_path / folder / name


def test_the_walk_sorts_paths_by_their_nfc_form(tmp_path):
    # "e" and a combining accent sorts before "f"; "é" composed after it.
    place(tmp_path / "f.tla", OLD / "0.7.0.tla")
    place(tmp_path / unicodedata.normalize("NFD", "éz.tla"), OLD / "0.7.0.tla")
    [accented] = [name for name in os.listdir(tmp_path) if name != "f.tla"]

    found = [relative for relative, _ in corpus_files(tmp_path)]

    assert found == ["f.tla", accented]


def test_the_report_gives_each_path_as_found(tmp_path):
    decomposed = unicodedata.normalize("NFD", "Bartók.tla")
    place(tmp_path / decomposed, OLD / "0.7.0.tla")
    place(tmp_path / "copy.tla", OLD / "0.7.0.tla")
    [name] = [name for name in os.listdir(tmp_path) if name != "copy.tla"]

    report = migrate_folder(tmp_path)

    assert [f.path for f in report.files] == [name, "copy.tla"]
    assert report.shared_ids == [[name, "copy.tla"]]
    for result in report.files:
        tla.read(tmp_path / result.path)


def test_the_walk_reports_a_subfolder_it_cant_list_and_goes_on(tmp_path, monkeypatch):
    place(tmp_path / "locked" / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / "open" / "piece.tla", OLD / "0.7.0.tla")
    scandir = os.scandir

    def refusing(path):
        if Path(path).name == "locked":
            raise PermissionError(13, "Permission denied", str(path))
        return scandir(path)

    monkeypatch.setattr(os, "scandir", refusing)
    errors = []

    found = corpus_files(tmp_path, on_error=lambda *args: errors.append(args))

    assert [relative for relative, _ in found] == ["open/piece.tla"]
    [(relative, error)] = errors
    assert relative == "locked/"
    assert isinstance(error, PermissionError)
    with pytest.raises(PermissionError):
        corpus_files(tmp_path)


# Without apply: a list, and nothing written


def test_without_apply_no_file_changes(corpus):
    top = corpus.parent
    before = snapshot(top)

    migrate_folder(corpus)

    assert snapshot(top) == before


def test_without_apply_each_file_is_reported_in_path_order(corpus):
    report = migrate_folder(corpus)

    assert outcomes(report) == [
        ("a copy.tla", "would_migrate"),
        ("a.tla", "would_migrate"),
        ("current.tla", "current"),
        ("newer.tla", "newer"),
        ("sub/broken.tla", "unreadable"),
        ("sub/deeper/OLD.TLA", "would_migrate"),
        ("sub/old-0.6.tla", "would_migrate"),
    ]
    files = by_path(report)
    assert files["a.tla"].from_version == "0.7.0"
    assert files["sub/deeper/OLD.TLA"].from_version == "0.0.96"
    assert files["sub/old-0.6.tla"].from_version == "0.6.0"
    assert files["current.tla"].from_version == tla.FORMAT_VERSION
    assert files["newer.tla"].reason == "written by a newer TiLiA (format 2.0.0)"
    assert files["sub/broken.tla"].reason == (
        "can't read (line 6): not valid JSON (Expecting ',' delimiter)"
    )
    for name in OLD_FILES + ["current.tla"]:
        assert files[name].reason is None


def test_the_report_counts_what_the_migration_dropped(corpus):
    files = by_path(migrate_folder(corpus))

    assert files["a.tla"].changes == {
        "formal_values_dropped": 2,
        "amplitude_bars_dropped": 3,
    }
    assert files["sub/old-0.6.tla"].changes == {"formal_values_dropped": 5}
    assert files["current.tla"].changes == {}
    # The migration's own warnings are what the counts sum up.
    assert files["a.tla"].warnings == []


def test_the_report_lists_the_rules_a_migrated_file_breaks(tmp_path):
    old = json.loads((OLD / "0.7.0.tla").read_text(encoding="utf-8"))
    old["timelines"]["1"]["components"]["999"] = {
        "kind": "MARKER",
        "time": 1.0,
        "label": "",
        "color": "#999999",
        "comments": "",
    }
    place(tmp_path / "piece.tla", json.dumps(old).encode())

    [result] = migrate_folder(tmp_path).files

    assert result.outcome == "would_migrate"
    assert result.changes == {"formal_values_dropped": 2, "amplitude_bars_dropped": 3}
    [warning] = result.warnings
    assert 'holds a component of kind "MARKER"' in warning.message


def test_copies_are_listed_as_sharing_a_document_id(corpus):
    assert migrate_folder(corpus).shared_ids == [["a copy.tla", "a.tla"]]


def test_files_that_share_no_id_are_not_listed(clean_corpus):
    assert migrate_folder(clean_corpus).shared_ids == []


def test_a_folder_that_doesnt_exist_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        migrate_folder(tmp_path / "nowhere")


def test_a_file_is_refused_as_a_folder(tmp_path):
    place(tmp_path / "piece.tla", OLD / "0.7.0.tla")

    with pytest.raises(NotADirectoryError):
        migrate_folder(tmp_path / "piece.tla")


def test_a_subfolder_that_cant_be_listed_is_reported(tmp_path, monkeypatch):
    place(tmp_path / "locked" / "piece.tla", OLD / "0.7.0.tla")
    place(tmp_path / "piece.tla", OLD / "0.7.0.tla")
    scandir = os.scandir

    def refusing(path):
        if Path(path).name == "locked":
            raise PermissionError(13, "Permission denied", str(path))
        return scandir(path)

    monkeypatch.setattr(os, "scandir", refusing)

    report = migrate_folder(tmp_path)

    # One result per file; the folder apart.
    assert outcomes(report) == [("piece.tla", "would_migrate")]
    from tilia_core.tla.model import FolderNotListed

    assert report.folders_not_listed == [
        FolderNotListed(path="locked/", reason="can't read: Permission denied")
    ]
    assert report.status == 1


# With apply


def test_apply_writes_only_the_old_files(corpus):
    top = corpus.parent
    before = snapshot(top)
    expected = {
        name: tla.canonical_bytes(tla.read(corpus / name)) for name in OLD_FILES
    }

    migrate_folder(corpus, apply=True)

    after = snapshot(top)
    assert after.keys() == before.keys()  # no file left behind
    written = {name for name in after if after[name] != before[name]}
    assert written == {f"corpus/{name}" for name in OLD_FILES}
    for name in OLD_FILES:
        assert (corpus / name).read_bytes() == expected[name]


def test_apply_reports_each_old_file_as_migrated(corpus):
    report = migrate_folder(corpus, apply=True)

    assert outcomes(report) == [
        ("a copy.tla", "migrated"),
        ("a.tla", "migrated"),
        ("current.tla", "current"),
        ("newer.tla", "newer"),
        ("sub/broken.tla", "unreadable"),
        ("sub/deeper/OLD.TLA", "migrated"),
        ("sub/old-0.6.tla", "migrated"),
    ]
    files = by_path(report)
    assert files["sub/deeper/OLD.TLA"].from_version == "0.0.96"
    assert files["a.tla"].changes == {
        "formal_values_dropped": 2,
        "amplitude_bars_dropped": 3,
    }
    assert report.shared_ids == [["a copy.tla", "a.tla"]]


def test_a_migrated_file_reads_as_the_document_read_before(corpus):
    before = {name: tla.read(corpus / name) for name in OLD_FILES}

    migrate_folder(corpus, apply=True)

    for name in OLD_FILES:
        after = tla.read(corpus / name)
        assert after.format_version == tla.FORMAT_VERSION
        assert after.document_id == before[name].document_id
        assert after.timelines.keys() == before[name].timelines.keys()
        assert without_reading(after) == without_reading(before[name])


def test_a_second_run_writes_nothing(corpus):
    migrate_folder(corpus, apply=True)
    top = corpus.parent
    before = snapshot(top)

    report = migrate_folder(corpus, apply=True)

    assert snapshot(top) == before
    assert outcomes(report) == [
        ("a copy.tla", "current"),
        ("a.tla", "current"),
        ("current.tla", "current"),
        ("newer.tla", "newer"),
        ("sub/broken.tla", "unreadable"),
        ("sub/deeper/OLD.TLA", "current"),
        ("sub/old-0.6.tla", "current"),
    ]
    assert report.shared_ids == [["a copy.tla", "a.tla"]]


def test_a_second_run_on_a_folder_without_problems_says_every_file_is_current(
    clean_corpus,
):
    assert migrate_folder(clean_corpus, apply=True).status == 0

    report = migrate_folder(clean_corpus, apply=True)

    assert outcomes(report) == [
        ("a.tla", "current"),
        ("current.tla", "current"),
        ("newer.tla", "newer"),
        ("sub/old.tla", "current"),
    ]
    assert report.status == 0


# A file that can't be read is read again


def record(monkeypatch, then=None):
    """What `migrate_folder` does, in order: ("read", name) for each read of
    a file, and ("pause", seconds) for each pause, which doesn't pause.
    `then(path, error)` runs after a read that failed."""
    events = []
    read = folder_module.read_with_migration

    def recorded(path):
        events.append(("read", Path(path).name))
        try:
            return read(path)
        except (OSError, ValueError) as error:
            if then is not None:
                then(Path(path), error)
            raise

    monkeypatch.setattr(folder_module, "read_with_migration", recorded)
    monkeypatch.setattr(
        time, "sleep", lambda seconds: events.append(("pause", seconds))
    )
    return events


def test_a_file_that_cant_be_read_is_read_again_after_a_pause(
    clean_corpus, monkeypatch
):
    place(clean_corpus / "broken.tla", BROKEN / "cut-short.tla")
    events = record(monkeypatch)

    report = migrate_folder(clean_corpus)

    pause = events.index(("pause", 0.2))
    assert events[:pause].count(("read", "broken.tla")) == 1
    assert events[pause:].count(("read", "broken.tla")) == 1
    assert by_path(report)["broken.tla"].outcome == "unreadable"
    assert by_path(report)["broken.tla"].reason == (
        "can't read (line 49): not valid JSON (Unterminated string)"
    )
    assert events.count(("read", "a.tla")) == 1  # a file that reads, once


def test_files_that_cant_be_read_are_read_again_after_one_pause(
    clean_corpus, monkeypatch
):
    broken = ["broken-1.tla", "broken-2.tla", "sub/broken-3.tla"]
    for name in broken:
        place(clean_corpus / name, BROKEN / "cut-short.tla")
    events = record(monkeypatch)

    report = migrate_folder(clean_corpus)

    [pause] = [event for event in events if event[0] == "pause"]
    assert pause == ("pause", 0.2)
    before, after = events[: events.index(pause)], events[events.index(pause) + 1 :]
    names = [Path(name).name for name in broken]
    assert [name for _, name in before if name in names] == names
    assert after == [("read", name) for name in names]
    for name in broken:
        assert by_path(report)[name].outcome == "unreadable"


def test_a_folder_whose_files_all_read_has_no_pause(clean_corpus, monkeypatch):
    events = record(monkeypatch)

    migrate_folder(clean_corpus)

    assert not [event for event in events if event[0] == "pause"]


def test_a_file_that_reads_the_second_time_is_migrated(tmp_path, monkeypatch):
    # Another program was still writing it the first time.
    place(tmp_path / "piece.tla", (OLD / "0.7.0.tla").read_bytes()[:500])

    def finished(path, error):
        shutil.copyfile(OLD / "0.7.0.tla", path)

    events = record(monkeypatch, then=finished)

    report = migrate_folder(tmp_path, apply=True)

    assert events.count(("read", "piece.tla")) == 2
    assert outcomes(report) == [("piece.tla", "migrated")]
    assert report.status == 0


def test_a_file_that_cant_be_opened_is_read_again_then_reported(tmp_path, monkeypatch):
    place(tmp_path / "piece.tla", OLD / "0.7.0.tla")

    def refusing(path):
        raise PermissionError(13, "Permission denied", str(path))

    reads = []
    monkeypatch.setattr(
        folder_module,
        "read_with_migration",
        lambda path: reads.append(path) or refusing(path),
    )
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    report = migrate_folder(tmp_path)

    assert len(reads) == 2
    assert outcomes(report) == [("piece.tla", "unreadable")]
    assert report.files[0].reason == "can't read: Permission denied"


def test_a_file_of_a_newer_format_is_read_once(clean_corpus, monkeypatch):
    events = record(monkeypatch)

    migrate_folder(clean_corpus)

    assert events.count(("read", "newer.tla")) == 1


def test_a_newer_format_is_refused_as_one():
    with pytest.raises(tla.NewerFormat) as caught:
        tla.read(BROKEN / "newer-format.tla")
    assert caught.value.version == "2.0.0"
    assert caught.value.message == "written by a newer TiLiA (format 2.0.0)"
    assert caught.value.place == "/version"
    assert caught.value.line == 3
    with pytest.raises(tla.UnreadableFile) as caught:
        tla.read(BROKEN / "older-draft.tla")
    assert not isinstance(caught.value, tla.NewerFormat)


def test_a_newer_format_is_told_by_its_error_not_by_its_words(tmp_path, monkeypatch):
    place(tmp_path / "piece.tla", BROKEN / "newer-format.tla")

    def newer(path):
        error = tla.NewerFormat("3.0.0", path=path)
        error.message = "worded otherwise"
        raise error

    monkeypatch.setattr(folder_module, "read_with_migration", newer)

    report = migrate_folder(tmp_path)

    assert outcomes(report) == [("piece.tla", "newer")]
    assert report.files[0].reason == "worded otherwise"
    assert report.status == 0


# An error in one file doesn't stop the others


@pytest.mark.parametrize(
    "error",
    [
        TypeError("unsupported operand type(s) for +: 'int' and 'str'"),
        RecursionError("maximum recursion depth exceeded"),
        MemoryError(),
        KeyError("ordinal"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_an_error_reading_one_file_doesnt_stop_the_others(
    clean_corpus, monkeypatch, caplog, error
):
    read = folder_module.read_with_migration

    def failing(path):
        if Path(path).name == "a.tla":
            raise error
        return read(path)

    monkeypatch.setattr(folder_module, "read_with_migration", failing)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    with caplog.at_level(logging.ERROR, logger="tilia_core"):
        report = migrate_folder(clean_corpus, apply=True)

    result = by_path(report)["a.tla"]
    assert result.outcome == "unreadable"
    text = str(error)
    assert result.reason == (
        f"can't read: {type(error).__name__}: {text}"
        if text
        else f"can't read: {type(error).__name__}"
    )
    assert by_path(report)["sub/old.tla"].outcome == "migrated"
    assert report.status == 1
    [logged] = [r for r in caplog.records if r.exc_info]
    assert logged.exc_info[1] is error


def test_an_error_writing_one_file_doesnt_stop_the_others(
    clean_corpus, monkeypatch, caplog
):
    write = folder_module.write
    error = TypeError("an unexpected value")

    def failing(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise error
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", failing)

    with caplog.at_level(logging.ERROR, logger="tilia_core"):
        report = migrate_folder(clean_corpus, apply=True)

    result = by_path(report)["a.tla"]
    assert result.outcome == "write_failed"
    assert result.reason == "can't write: TypeError: an unexpected value"
    assert by_path(report)["sub/old.tla"].outcome == "migrated"
    [logged] = [r for r in caplog.records if r.exc_info]
    assert logged.exc_info[1] is error


def test_a_document_the_writer_refuses_is_reported_without_its_path(
    clean_corpus, monkeypatch
):
    write = folder_module.write

    def refusing(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise tla.UnreadableFile('"level" is missing', path=target, line=44)
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", refusing)

    report = migrate_folder(clean_corpus, apply=True)

    assert by_path(report)["a.tla"].reason == (
        'can\'t write (line 44): "level" is missing'
    )


# The folder, as given


@pytest.mark.parametrize("name", ["~", "~drafts"])
def test_a_folder_named_with_a_tilde_is_the_folder_of_that_name(
    tmp_path, monkeypatch, name
):
    home = tmp_path / "home"
    place(home / "elsewhere.tla", OLD / "0.5.15.tla")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    place(tmp_path / "work" / name / "piece.tla", OLD / "0.7.0.tla")
    monkeypatch.chdir(tmp_path / "work")

    report = migrate_folder(name)

    assert outcomes(report) == [("piece.tla", "would_migrate")]


# What the reader gives the folder


def test_a_document_carries_nothing_of_the_migration():
    names = {field.name for field in dataclasses.fields(tla.Document)}

    assert not {name for name in names if name.startswith("_migration")}


def test_the_reader_gives_the_migration_with_an_old_files_document():
    document, migrated = reader.read_with_migration(OLD / "0.7.0.tla")

    assert document == tla.read(OLD / "0.7.0.tla")
    assert migrated.changes == {
        "formal_values_dropped": 2,
        "amplitude_bars_dropped": 3,
    }
    assert migrated.warnings == document.warnings
    assert reader.read_with_migration(GOLDEN / "every-kind.tla")[1] is None


# What can go wrong between reading and writing


def change_after_reading(monkeypatch, name, change):
    """`change(path)` runs once `migrate_folder` has read the file `name`, as
    another program would change it before the migration writes it."""
    read = folder_module.read_with_migration

    def then_changed(path):
        read_result = read(path)
        if Path(path).name == name:
            change(Path(path))
        return read_result

    monkeypatch.setattr(folder_module, "read_with_migration", then_changed)


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(
            lambda path: shutil.copyfile(OLD / "0.5.15.tla", path), id="edited"
        ),
        pytest.param(lambda path: path.unlink(), id="removed"),
    ],
)
def test_a_file_changed_between_reading_and_writing_is_left_alone(
    clean_corpus, monkeypatch, change
):
    change_after_reading(monkeypatch, "a.tla", change)
    path = clean_corpus / "a.tla"

    report = migrate_folder(clean_corpus, apply=True)

    result = by_path(report)["a.tla"]
    assert result.outcome == "changed_since_read"
    assert result.reason == "changed since it was read"
    if path.exists():
        assert path.read_bytes() == (OLD / "0.5.15.tla").read_bytes()
    assert by_path(report)["sub/old.tla"].outcome == "migrated"
    assert report.status == 1


def test_a_file_another_program_holds_open_is_reported_as_in_use(
    clean_corpus, monkeypatch
):
    write = folder_module.write
    path = clean_corpus / "a.tla"
    before = path.read_bytes()

    def held_open(target, doc, **kwargs):
        if Path(target).name == "a.tla":
            raise tla.FileInUse(target)
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", held_open)

    report = migrate_folder(clean_corpus, apply=True)

    result = by_path(report)["a.tla"]
    assert result.outcome == "in_use"
    assert result.reason == "in use by another program"
    assert path.read_bytes() == before
    assert by_path(report)["sub/old.tla"].outcome == "migrated"
    assert report.status == 1


@pytest.fixture
def read_only(clean_corpus):
    path = clean_corpus / "a.tla"
    os.chmod(path, stat.S_IREAD)
    yield path
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def test_a_file_that_cant_be_written_is_reported(clean_corpus, read_only):
    before = read_only.read_bytes()

    report = migrate_folder(clean_corpus, apply=True)

    result = by_path(report)["a.tla"]
    assert result.outcome == "write_failed"
    assert result.reason == f"can't write: {os.strerror(13)}"
    assert read_only.read_bytes() == before
    assert by_path(report)["sub/old.tla"].outcome == "migrated"
    assert report.status == 1


def test_the_writes_state_the_fingerprint_read(clean_corpus, monkeypatch):
    stated = []
    write = folder_module.write

    def recorded(target, doc, **kwargs):
        stated.append((Path(target).name, kwargs.get("expect")))
        return write(target, doc, **kwargs)

    monkeypatch.setattr(folder_module, "write", recorded)

    migrate_folder(clean_corpus, apply=True)

    assert dict(stated) == {
        "a.tla": tla.fingerprint(clean_corpus / "a.tla"),
        "old.tla": tla.fingerprint(clean_corpus / "sub" / "old.tla"),
    }


# The exit status


@pytest.mark.parametrize(
    "outcome, status",
    [
        ("would_migrate", 0),
        ("migrated", 0),
        ("current", 0),
        ("newer", 0),
        ("unreadable", 1),
        ("changed_since_read", 1),
        ("in_use", 1),
        ("write_failed", 1),
    ],
)
def test_status(outcome, status):
    report = MigrationReport(
        files=[
            FileResult(path="a.tla", outcome="migrated"),
            FileResult(path="b.tla", outcome=outcome),
        ]
    )

    assert report.status == status


def test_status_of_an_empty_folder(tmp_path):
    report = migrate_folder(tmp_path, apply=True)

    assert report.files == []
    assert report.status == 0


def test_status_of_a_folder_with_a_file_that_cant_be_read(corpus):
    assert migrate_folder(corpus).status == 1
    assert migrate_folder(corpus, apply=True).status == 1


def test_status_of_a_folder_whose_files_all_migrate(clean_corpus):
    assert migrate_folder(clean_corpus).status == 0
    assert migrate_folder(clean_corpus, apply=True).status == 0
