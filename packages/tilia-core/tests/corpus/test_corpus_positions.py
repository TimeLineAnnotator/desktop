"""Positions and measures from WP9's time map (contracts/time-map.md;
TimeLineAnnotator/project-management#157).

``open_corpus`` gives each ``.tla`` file the time map WP9's ``find_time_map``
chooses, with the roles the index resolved. The index stores what that time
map gives, and nothing of its own: the rows here are compared with WP9's,
computed from the file as ``tla`` reads it. It also stores why a file has no
time map and WP9's warnings (WP9's FR-082): ``files.time_map_reason`` and
``file_warnings``."""

import corpus_docs
from tla_files import as_tla

from docs import beat_timeline
from tilia_core import open_corpus, timemap, tla

# A one-beat pickup (bar 0), then bars 1 and 2 of 2/4 played twice, then bar 3:
# a beat every second from 1 s, the last at 11 s.
MARKS = {1: {"number": 0}, 2: {"number": 1}, 4: {}, 6: {"number": 1}, 8: {}, 10: {}}
NUMBERS = [0, 1, 2, 1, 2, 3]


def tapped(role=None, ordinal=3):
    return beat_timeline(
        [{"time": float(t), "measure": MARKS.get(t)} for t in range(1, 12)],
        role=role,
        ordinal=ordinal,
    )


def piece(*beat_timelines):
    """A hierarchy and markers, some on the map and some off it, and
    ``beat_timelines``."""
    doc = as_tla(
        corpus_docs.document(
            corpus_docs.hierarchy(
                [
                    ("pickup", 1, 1.0, 2.0),
                    ("A", 1, 2.0, 6.0),
                    ("A'", 1, 6.0, 10.0),
                    ("coda", 1, 10.0, 12.0),
                ]
            ),
            corpus_docs.markers(
                [("before", 0.5), ("half", 4.5), ("PAC", 9.0), ("after", 30.0)]
            ),
            media_length=40.0,
        )
    )
    for tl in beat_timelines:
        doc.timelines[tl.id] = tl
    return doc


def written(tmp_path, doc, name="piece.tla"):
    folder = tmp_path / "corpus"
    folder.mkdir(exist_ok=True)
    tla.write(folder / name, doc)
    return folder


def wp9_map(path):
    time_map = timemap.time_map_of(tla.read(path))
    assert time_map is not None
    return time_map


def test_measures_are_wp9s_rows_with_a_repeat_and_a_pickup(tmp_path):
    folder = written(tmp_path, piece(tapped()))
    expected = [
        (
            m.count,
            m.number,
            m.label,
            m.start,
            m.end,
            m.beats,
            m.pass_,
            int(m.cadenza),
            m.movement,
            m.time_signature,
        )
        for m in wp9_map(folder / "piece.tla").measure_rows()
    ]

    with open_corpus(folder) as corpus, corpus.reading() as r:
        rows = r.connection.execute(
            'SELECT count, number, label, start, "end", beats, pass, cadenza, '
            "movement, time_signature FROM measures ORDER BY count"
        ).fetchall()

    assert [row[1] for row in rows] == NUMBERS
    assert [row[6] for row in rows][1:5] == [1, 1, 2, 2]  # the repeat's passes
    assert rows == expected


def test_positions_are_wp9s_for_the_units_on_the_map(tmp_path):
    folder = written(tmp_path, piece(tapped()))
    time_map = wp9_map(folder / "piece.tla")

    with open_corpus(folder) as corpus, corpus.reading() as r:
        units = r.connection.execute(
            'SELECT c.label, c.start, c."end", p.bar, p.end_bar, p.beat, p.pass, '
            "p.bar_count, p.bar_label, p.bar_beat_count, p.downbeat, p.bar_cadenza, "
            "p.bar_movement FROM components c "
            "LEFT JOIN positions p ON p.component_id = c.id "
            "WHERE c.kind IN ('hierarchy', 'marker')"
        ).fetchall()

    stored = {row[0]: tuple(row[3:]) for row in units}
    expected = {}
    for label, start, end, *_ in units:
        p = time_map.positions(start, end)
        expected[label] = (
            (None,) * 10
            if p is None
            else (
                p.bar,
                p.end_bar,
                p.beat,
                p.pass_,
                p.bar_count,
                p.bar_label,
                p.bar_beat_count,
                int(p.downbeat),
                int(p.cadenza),
                p.movement,
            )
        )
    assert stored == expected
    assert stored["A'"][0:4:3] == (1, 2)  # bar 1, second pass
    assert stored["half"][2] == 1.5  # off the beats: a fractional beat
    assert stored["before"] == (None,) * 10  # before the first beat: off the map


def test_the_file_records_the_time_maps_timeline_and_whether_it_was_guessed(
    tmp_path,
):
    first, chosen = tapped(ordinal=3), tapped(role="time_map", ordinal=4)
    folder = written(tmp_path, piece(first), "guessed.tla")
    written(tmp_path, piece(first, chosen), "chosen.tla")

    with open_corpus(folder) as corpus, corpus.reading() as r:
        got = {
            path: (uuid, guessed)
            for path, uuid, guessed in r.connection.execute(
                "SELECT f.path, t.uuid, f.time_map_guessed FROM files f "
                "JOIN timelines t ON t.id = f.time_map"
            )
        }

    assert got == {"guessed.tla": (first.id, 1), "chosen.tla": (chosen.id, 0)}


def test_the_corpus_keeps_wp9s_time_map_for_queries(tmp_path):
    beats = tapped()
    folder = written(tmp_path, piece(beats))

    with open_corpus(folder) as corpus, corpus.reading() as r:
        (file_id,) = r.connection.execute("SELECT id FROM files").fetchone()
        time_map = r.time_map(file_id)

    assert isinstance(time_map, timemap.TimeMap)
    assert time_map.timeline_id == beats.id
    assert [m[2] for m in time_map.measures()] == NUMBERS


def test_a_file_without_a_beat_timeline_has_no_time_map(tmp_path):
    folder = written(tmp_path, piece())

    with open_corpus(folder) as corpus, corpus.reading() as r:
        con = r.connection
        (file_id, time_map, guessed) = con.execute(
            "SELECT id, time_map, time_map_guessed FROM files"
        ).fetchone()
        measures = con.execute("SELECT count(*) FROM measures").fetchone()[0]
        positions = con.execute("SELECT count(*) FROM positions").fetchone()[0]
        kept = r.time_map(file_id)

    assert (time_map, guessed, measures, positions, kept) == (None, None, 0, 0, None)


def one_beat(role=None, ordinal=3):
    return beat_timeline(
        [{"time": 1.0, "measure": {"number": 1}}], role=role, ordinal=ordinal
    )


def reasons_and_warnings(corpus):
    with corpus.reading() as r:
        con = r.connection
        reasons = dict(con.execute("SELECT path, time_map_reason FROM files"))
        warnings = con.execute(
            "SELECT f.path, w.source, w.message FROM file_warnings w "
            "JOIN files f ON f.id = w.file_id ORDER BY w.rowid"
        ).fetchall()
    return reasons, warnings


def test_a_file_whose_beat_timeline_gives_no_time_map_says_why(tmp_path):
    folder = written(tmp_path, piece(one_beat()), "one-beat.tla")
    written(tmp_path, piece(tapped()), "tapped.tla")
    written(tmp_path, piece(), "no-beats.tla")
    expected = timemap.find_time_map(tla.read(folder / "one-beat.tla")).reason
    assert expected  # WP9 gives a reason

    with open_corpus(folder) as corpus:
        reasons, _ = reasons_and_warnings(corpus)
        with corpus.reading() as r:
            maps = dict(r.connection.execute("SELECT path, time_map FROM files"))
        row = corpus.file("one-beat.tla")

    # no reason with a time map, nor without a beat timeline (nothing wrong)
    assert reasons == {
        "one-beat.tla": expected,
        "tapped.tla": None,
        "no-beats.tla": None,
    }
    assert maps["one-beat.tla"] is None
    assert row is not None and row.time_map_reason == expected


def test_wp9s_warnings_are_rows_of_file_warnings(tmp_path):
    claiming = (tapped(role="time_map", ordinal=3), tapped(role="time_map", ordinal=4))
    folder = written(tmp_path, piece(*claiming), "two.tla")
    written(tmp_path, piece(tapped()), "fine.tla")
    expected = timemap.find_time_map(tla.read(folder / "two.tla")).warnings
    assert expected  # two timelines claim the role

    with open_corpus(folder) as corpus:
        reasons, warnings = reasons_and_warnings(corpus)
        rows = {f.path: f.warnings for f in corpus.files()}

    assert warnings == [("two.tla", "time_map", w) for w in expected]
    assert rows == {"two.tla": tuple(expected), "fine.tla": ()}
    assert reasons["two.tla"] is None  # the first claiming timeline gives a map


def test_the_reason_and_warnings_go_with_the_files_content(tmp_path):
    claiming = (tapped(role="time_map", ordinal=3), tapped(role="time_map", ordinal=4))
    folder = written(tmp_path, piece(*claiming), "two.tla")
    written(tmp_path, piece(one_beat()), "one-beat.tla")

    with open_corpus(folder, rescan_before_reads=False) as corpus:
        reasons, warnings = reasons_and_warnings(corpus)
        assert reasons["one-beat.tla"] and warnings

        # fixed: read again, and its warnings go
        written(tmp_path, piece(tapped()), "two.tla")
        corpus.scan()
        reasons, warnings = reasons_and_warnings(corpus)
        assert warnings == []
        assert reasons["one-beat.tla"]

        # removed: its reason goes with its row
        (folder / "one-beat.tla").unlink()
        corpus.scan()
        with corpus.reading() as r:
            left = r.connection.execute(
                "SELECT path, state, time_map_reason FROM files ORDER BY path"
            ).fetchall()
            orphans = r.connection.execute(
                "SELECT count(*) FROM file_warnings "
                "WHERE file_id NOT IN (SELECT id FROM files)"
            ).fetchone()[0]

    assert left == [
        ("one-beat.tla", "unavailable", None),
        ("two.tla", "readable", None),
    ]
    assert orphans == 0
