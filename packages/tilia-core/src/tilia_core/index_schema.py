"""The tables of the index that TQL queries run on.

This is WP13's proposal for the index's tables. The index package
(TimeLineAnnotator/project-management#16) takes it over. ``show SQL`` prints
these table and column names, so users see them: they are lower case and name
what they hold.

One row of ``components`` per hierarchy unit, marker, range, chord, key or
beat; the tables named after a kind (``hierarchies``, ``ranges``, ``chords``,
``keys``) hold what only that kind has, ``positions`` and ``measures`` what the
file's time map gives, and ``fields`` the user-set fields of files and others.

``PRAGMA user_version`` is 1: the version of these names. They are a stand-in
that WP12's index will own. They, the SQL that ``show SQL`` prints and the
``tql_*`` functions of :mod:`tilia_core.tql.sqlfuncs` may change, and nothing
in them is promised yet. Tests pin the names, and any change to a name that SQL
can see raises the version, so that a change is deliberate.
"""

import sqlite3

SCHEMA = """
CREATE TABLE files (
    id TEXT PRIMARY KEY,
    path TEXT,
    media_length REAL,
    time_unit TEXT,
    time_map TEXT
);

CREATE TABLE timelines (
    id TEXT PRIMARY KEY,
    file_id TEXT,
    kind TEXT,
    name TEXT,
    name_folded TEXT,
    ordinal INTEGER,
    role TEXT,
    author TEXT
);

CREATE TABLE components (
    id TEXT PRIMARY KEY,
    file_id TEXT,
    timeline_id TEXT,
    kind TEXT,
    start REAL,
    "end" REAL,
    label TEXT,
    label_folded TEXT,
    color TEXT,
    comments TEXT
);

CREATE TABLE hierarchies (
    component_id TEXT PRIMARY KEY,
    level INTEGER,
    parent_id TEXT,
    depth INTEGER
);

CREATE TABLE ranges (
    component_id TEXT PRIMARY KEY,
    row_id TEXT,
    row TEXT,
    row_folded TEXT
);

CREATE TABLE chords (
    component_id TEXT PRIMARY KEY,
    step INTEGER,
    accidental INTEGER,
    quality TEXT,
    inversion INTEGER,
    applied_to INTEGER,
    custom_text TEXT,
    key_id TEXT,
    root TEXT,
    roman TEXT,
    symbol TEXT,
    key TEXT
);

CREATE TABLE keys (
    component_id TEXT PRIMARY KEY,
    step INTEGER,
    accidental INTEGER,
    mode TEXT,
    tonic TEXT,
    key TEXT
);

CREATE TABLE categories (
    component_id TEXT,
    category TEXT
);

CREATE TABLE positions (
    component_id TEXT PRIMARY KEY,
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
    file_id TEXT,
    count INTEGER,
    number INTEGER,
    label TEXT,
    start REAL,
    "end" REAL,
    beats INTEGER
);

CREATE TABLE fields (
    scope TEXT,
    owner_id TEXT,
    name TEXT,
    value TEXT
);

CREATE INDEX components_by_timeline ON components (file_id, timeline_id, start);
CREATE INDEX categories_by_category ON categories (category);
CREATE INDEX categories_by_component ON categories (component_id);
CREATE INDEX components_by_label ON components (label_folded);

PRAGMA user_version = 1;
"""


def create_schema(con: sqlite3.Connection) -> None:
    """Create the index's tables and indexes in ``con``, which must be empty."""
    con.executescript(SCHEMA)
