"""The tables of a corpus's index.

``show SQL`` prints these table and column names, and ``tql.sql`` runs users'
SQL on them, so users see them: they are lower case and name what they hold.
``packages/tilia-core/docs/index-tables.md`` will document them for users.

- ``files``: one row per file the corpus has seen in this run, readable,
  unreadable or unavailable (``state``). Only readable files have rows in the
  other tables.
- ``timelines`` and ``components``: one row per timeline, and per hierarchy
  unit, marker, range, chord, key or beat. The tables named after a kind
  (``hierarchies``, ``ranges``, ``chords``, ``keys``; see :data:`KIND_TABLES`)
  hold what only that kind has.
- ``categories``: each labelled unit's categories under its timeline's label
  grammar, each with the category it is a subtype of (``supertype``), which
  only a grammar with subtypes gives: with none, a dot is part of the label.
- ``positions`` and ``measures``: what the file's time map gives. ``measures``
  holds one row per bar in playing order: its place in that order (``count``),
  its printed ``number`` and ``label``, its ``start`` and ``end``, its ``beats``
  and its ``pass`` through a repeat (1 without repeats).
- ``fields``: the fields of files, timelines and components, one row per value.

**Keys.** ``files.id``, ``timelines.id`` and ``components.id`` are the index's
own integers (TimeLineAnnotator/project-management#124): unique in the corpus,
kept while their file is unchanged, never reused within a run, and not kept
across runs. Every column that points to one is an integer too. The ids the
files store are columns of their own: ``files.document_id``,
``timelines.uuid`` and ``components.uuid``.

``PRAGMA user_version`` is 1: the version of these names. They, the SQL that
``show SQL`` prints and the ``tql_*`` functions of
:mod:`tilia_core.tql.sqlfuncs` may change, and nothing in them is promised yet.
Tests pin the names, and any rename or removal of a name that SQL can see
raises the version, so that a change is deliberate and a user's saved SQL can
tell a change in the tables from its own typo.
"""

import sqlite3

SCHEMA = """
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT,
    document_id TEXT,
    format_version TEXT,
    state TEXT,
    reason TEXT,
    fingerprint TEXT,
    media_length REAL,
    time_unit TEXT,
    time_map INTEGER,
    time_map_guessed INTEGER
);

CREATE TABLE timelines (
    id INTEGER PRIMARY KEY,
    file_id INTEGER,
    uuid TEXT,
    kind TEXT,
    name TEXT,
    name_folded TEXT,
    ordinal INTEGER,
    role TEXT,
    author TEXT
);

CREATE TABLE components (
    id INTEGER PRIMARY KEY,
    file_id INTEGER,
    timeline_id INTEGER,
    uuid TEXT,
    kind TEXT,
    start REAL,
    "end" REAL,
    label TEXT,
    color TEXT,
    comments TEXT
);

CREATE TABLE hierarchies (
    component_id INTEGER PRIMARY KEY,
    level INTEGER,
    parent_id INTEGER,
    depth INTEGER
);

CREATE TABLE ranges (
    component_id INTEGER PRIMARY KEY,
    row_id TEXT,
    row TEXT,
    row_folded TEXT
);

CREATE TABLE chords (
    component_id INTEGER PRIMARY KEY,
    step INTEGER,
    accidental INTEGER,
    quality TEXT,
    inversion INTEGER,
    applied_to INTEGER,
    custom_text TEXT,
    key_id INTEGER,
    root TEXT,
    roman TEXT,
    symbol TEXT,
    key TEXT
);

CREATE TABLE keys (
    component_id INTEGER PRIMARY KEY,
    step INTEGER,
    accidental INTEGER,
    mode TEXT,
    tonic TEXT,
    key TEXT
);

CREATE TABLE categories (
    component_id INTEGER,
    category TEXT,
    supertype TEXT
);

CREATE TABLE positions (
    component_id INTEGER PRIMARY KEY,
    bar INTEGER,
    end_bar INTEGER,
    beat REAL,
    pass INTEGER,
    bar_count INTEGER,
    bar_label TEXT,
    bar_beat_count INTEGER,
    downbeat INTEGER
);

CREATE TABLE measures (
    file_id INTEGER,
    count INTEGER,
    number INTEGER,
    label TEXT,
    start REAL,
    "end" REAL,
    beats INTEGER,
    pass INTEGER
);

CREATE TABLE fields (
    scope TEXT,
    owner_id INTEGER,
    name TEXT,
    value TEXT
);

CREATE INDEX components_by_timeline ON components (file_id, timeline_id, start);
CREATE INDEX components_by_timeline_id ON components (timeline_id);
CREATE INDEX categories_by_category ON categories (category);
CREATE INDEX categories_by_component ON categories (component_id);
CREATE INDEX fields_by_owner ON fields (scope, owner_id);
CREATE INDEX fields_by_name ON fields (name);
CREATE INDEX hierarchies_by_parent ON hierarchies (parent_id);

PRAGMA user_version = 1;
"""
# positions (component_id), an index data-model.md lists, is the table's
# primary key, as each kind table's component_id is: an alias of the rowid,
# which needs no index of its own.

KIND_TABLES: dict[str, str] = {
    "hierarchy": "hierarchies",
    "range": "ranges",
    "chord": "chords",
    "key": "keys",
}
"""Each kind of component that has a table of its own, and that table. A unit's
properties are its row there; a new kind's table is listed here and nowhere
else."""


def create_schema(con: sqlite3.Connection) -> None:
    """Create the index's tables and indexes in ``con``, which must be empty."""
    con.executescript(SCHEMA)
