"""The package's "Done when", second half (SC-002): after User Story 2's script
of changes, a rescan holds the same rows as a fresh build of the folder, apart
from the files listed as unavailable."""

import dataclasses
import os

import corpus_docs
import fake_timemap
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus
from tilia_core.corpus import scan

HOUR_NS = 3600 * 10**9

# Every table, with each key written as the (path, uuid) of what it names: a
# file by its path, a timeline or component by its file's path and its uuid.
DUMP = {
    "files": "SELECT path, document_id, format_version, state, reason, fingerprint, "
    "media_length, time_unit, (SELECT uuid FROM timelines t WHERE t.id = f.time_map), "
    "time_map_guessed FROM files f",
    "timelines": "SELECT f.path, t.uuid, t.kind, t.name, t.name_folded, t.ordinal, "
    "t.role, t.author FROM timelines t JOIN files f ON f.id = t.file_id",
    "components": 'SELECT f.path, t.uuid, c.uuid, c.kind, c.start, c."end", c.label, '
    "c.color, c.comments FROM components c JOIN files f ON f.id = c.file_id "
    "JOIN timelines t ON t.id = c.timeline_id",
    "hierarchies": "SELECT f.path, c.uuid, h.level, p.uuid, h.depth FROM hierarchies h "
    "JOIN components c ON c.id = h.component_id JOIN files f ON f.id = c.file_id "
    "LEFT JOIN components p ON p.id = h.parent_id",
    "ranges": "SELECT f.path, c.uuid, r.row_id, r.row, r.row_folded FROM ranges r "
    "JOIN components c ON c.id = r.component_id JOIN files f ON f.id = c.file_id",
    "chords": "SELECT f.path, c.uuid, x.step, x.accidental, x.quality, x.inversion, "
    "x.applied_to, x.custom_text, k.uuid, x.root, x.roman, x.symbol, x.key "
    "FROM chords x JOIN components c ON c.id = x.component_id "
    "JOIN files f ON f.id = c.file_id LEFT JOIN components k ON k.id = x.key_id",
    "keys": "SELECT f.path, c.uuid, k.step, k.accidental, k.mode, k.tonic, k.key "
    "FROM keys k JOIN components c ON c.id = k.component_id "
    "JOIN files f ON f.id = c.file_id",
    "categories": "SELECT f.path, c.uuid, x.category, x.supertype FROM categories x "
    "JOIN components c ON c.id = x.component_id JOIN files f ON f.id = c.file_id",
    "positions": "SELECT f.path, c.uuid, p.bar, p.end_bar, p.beat, p.pass, "
    "p.bar_count, p.bar_label, p.bar_beat_count, p.downbeat FROM positions p "
    "JOIN components c ON c.id = p.component_id JOIN files f ON f.id = c.file_id",
    "measures": 'SELECT f.path, m.count, m.number, m.label, m.start, m."end", '
    "m.beats, m.pass FROM measures m JOIN files f ON f.id = m.file_id",
    "fields": "SELECT x.scope, CASE x.scope "
    "WHEN 'file' THEN (SELECT path FROM files WHERE id = x.owner_id) "
    "WHEN 'timeline' THEN (SELECT f.path || ':' || t.uuid FROM timelines t "
    "JOIN files f ON f.id = t.file_id WHERE t.id = x.owner_id) "
    "ELSE (SELECT f.path || ':' || c.uuid FROM components c "
    "JOIN files f ON f.id = c.file_id WHERE c.id = x.owner_id) END, "
    "x.name, x.value FROM fields x",
}


def dump(corpus):
    def order(row):
        return [(v is None, "" if v is None else str(v)) for v in row]

    with corpus.reading() as r:
        return {
            table: sorted(r.connection.execute(sql).fetchall(), key=order)
            for table, sql in DUMP.items()
        }


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


def doc(n, label="A"):
    """A document of every kind, with its own id and title."""
    base = corpus_docs.every_kind(document_id=f"doc-{n}")
    form = base.timelines[0]
    first = form.components[0]
    form = dataclasses.replace(
        form,
        components=(
            dataclasses.replace(first, attrs={**first.attrs, "label": label}),
            *form.components[1:],
        ),
    )
    return dataclasses.replace(
        base,
        timelines=(form, *base.timelines[1:]),
        fields={"title": f"Piece {n}"},
    )


def dated(path, ns):
    os.utime(path, ns=(ns, ns))


def test_a_rescan_after_the_script_of_changes_equals_a_fresh_build(tmp_path):
    folder = tmp_path / "corpus"
    paths = {
        1: "1.tla",
        2: "2.tla",
        3: "3.tla",
        4: "4.tla",
        5: "first/5.tla",
        6: "first/6.tla",
        7: "first/7.tla",
        8: "first/8.tla",
        9: "second/9.tla",
        10: "second/10.tla",
        11: "second/11.tla",
        12: "second/12.tla",
    }
    now = os.stat(tmp_path).st_mtime_ns
    old_version_at = now - 2 * HOUR_NS
    # 6.tla has an old version, which a backup keeps with its date
    old_six = corpus_docs.write_doc(folder / paths[6], doc(6, "B"))  # the same size
    dated(old_six, old_version_at)
    old_six_bytes = old_six.read_bytes()
    # 1. twelve files across two subfolders, settled an hour back, opened
    for n, path in paths.items():
        dated(corpus_docs.write_doc(folder / path, doc(n)), now - HOUR_NS)
    options = dict(reader=JsonDocumentReader(), time_map_of=fake_timemap.time_map_of)
    corpus = open_corpus(folder, **options)
    assert corpus.open_report.added == tuple(sorted(paths.values()))
    generation = corpus.generation
    # 2. User Story 2's script
    corpus_docs.write_doc(folder / paths[1], doc(1, "edited"))  # canonical form
    corpus_docs.write_doc(folder / paths[2], doc(2, "edited too"), crlf=True)
    os.rename(folder / paths[3], folder / "3 renamed.tla")
    os.rename(folder / paths[4], folder / "first" / "4.tla")
    os.remove(folder / paths[5])
    corpus_docs.write_doc(folder / "second" / "new.tla", doc(13))
    assert (folder / paths[6]).stat().st_size == len(old_six_bytes)
    (folder / paths[6]).write_bytes(old_six_bytes)
    dated(folder / paths[6], old_version_at)  # restored with its older date
    os.utime(folder / paths[7])  # touched
    corpus_docs.write_doc(folder / paths[9], doc(9), crlf=True)  # line endings
    # 3. rescan, then open the folder afresh
    report = corpus.scan()
    fresh = open_corpus(folder, **options)
    try:
        assert report.changed == ("1.tla", "2.tla", "first/6.tla")
        assert report.moved == (
            ("3.tla", "3 renamed.tla"),
            ("4.tla", "first/4.tla"),
        )
        assert report.unavailable == ("first/5.tla",)
        assert report.added == ("second/new.tla",)
        assert (report.back, report.unreadable, report.shared_ids) == ((), (), ())
        assert report.error is None
        assert report.generation_after == report.generation_before + 1
        assert corpus.generation == generation + 1
        scanned, built = dump(corpus), dump(fresh)
        for table in DUMP:
            if table != "files":
                assert scanned[table] == built[table], table
        unavailable = [r for r in scanned["files"] if r[3] == "unavailable"]
        assert [r[0] for r in unavailable] == ["first/5.tla"]
        assert [r for r in scanned["files"] if r[3] != "unavailable"] == built["files"]
    finally:
        corpus.close()
        fresh.close()
