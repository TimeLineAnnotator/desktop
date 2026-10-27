# The index's tables

When you open a folder of TiLiA files as a corpus, `tilia-core` reads every file and keeps what queries search in an SQLite database in memory: the index. These are its tables. TQL's "show SQL" prints SQL that reads them, and `tql.sql` runs your own read-only `SELECT` on them, so with this page you can write your own queries.

- **The keys are the index's own.** `files.id`, `timelines.id` and `components.id` are whole numbers the index gives when it reads a file, and every column that points to a row (`file_id`, `timeline_id`, `component_id`, `parent_id`, `key_id`, `owner_id`, `files.time_map`) holds one of them. A key is unique in the corpus and stays the same while its file is unchanged, but it isn't kept when a file is read again after a change, nor from one session to the next. So no join mixes the units of two files, even of two copies of one file.
- **The files' own ids** are columns of their own: `files.document_id`, and `timelines.uuid` and `components.uuid`. Copies of a file share them; that is why the index doesn't use them as keys. To name a file across sessions, use its `path`.
- **From** says where a value comes from: stored in the file, or computed by `tilia-core` when it reads the file, and by what.
- **Text** from the files (labels, names, rows, comments, custom text, field values) is stored in Unicode's NFC form. A `_folded` column holds the text folded for comparing, as TQL compares words: full case folding, so `strasse` matches "Straße".
- Times are in seconds, or in quarter notes in a file whose `time_unit` is `quarters`.
- **Reads run side by side.** Each read of a corpus (a query, a statistics table, a statement of `tql.sql`) has a connection of its own, and several threads can read at once. A read sees one state of the index from start to end; a rescan applies its changes between reads, never during one.

The names of these tables and columns may still change before `tilia-core` 1.0: `PRAGMA user_version` gives their version.

## `files`

One row per file the corpus has seen since it was opened: readable, unreadable or unavailable. Only readable files have rows in the other tables, and queries and statistics go over readable files only.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `id` | INTEGER | the file's key | the index |
| `path` | TEXT | the file's path relative to the corpus folder, with `/` | the file system |
| `document_id` | TEXT | the document id the file stores; copies share it. Empty for an unreadable file | the file |
| `format_version` | TEXT | the format version the file was written in | the file |
| `state` | TEXT | `readable`; `unreadable`, when the file can't be read; or `unavailable`, when it was found before and is missing now | computed |
| `reason` | TEXT | for an unreadable file, why, with the line where reading stopped: "can't read (line 12): …" | computed |
| `fingerprint` | TEXT | the SHA-256, in hexadecimal, of the file as `tilia-core` would write it, so line endings and the order of keys don't change it. Empty when the file is unreadable or unavailable | computed |
| `media_length` | REAL | the length of the file's media; positions in percent use it | the file |
| `time_unit` | TEXT | `seconds` or `quarters` | the file |
| `time_map` | INTEGER | the key (`timelines.id`) of the beat timeline that gives the file's bars and beats: the one whose role is `time_map`, else the first beat timeline. Empty without one | computed |
| `time_map_guessed` | INTEGER | 1 when the time map is the first beat timeline, because no timeline has the role `time_map`; 0 when found by its role; empty without a time map | computed |

An unavailable file keeps its `document_id`, `format_version`, `media_length` and `time_unit` as last read.

## `timelines`

One row per timeline of a readable file, of every kind.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `id` | INTEGER | the timeline's key | the index |
| `file_id` | INTEGER | its file (`files.id`) | the index |
| `uuid` | TEXT | the timeline's id in the file | the file |
| `kind` | TEXT | `hierarchy`, `marker`, `range`, `harmony`, `beat`, `score`, `pdf`, `audiowave`, `slider`, or the kind as the file names it, for kinds `tilia-core` doesn't know | the file |
| `name` | TEXT | the timeline's name | the file |
| `name_folded` | TEXT | its name, folded | computed |
| `ordinal` | INTEGER | the timeline's place in the file, from 1 | the file |
| `role` | TEXT | its role (`form`, `time_map`, …): the one the corpus's settings give, else the timeline's `role` field. Empty without one | the file, or the corpus's settings |
| `author` | TEXT | its `author` field | the file |

## `components`

One row per unit a query can find: hierarchy units, markers, ranges, chords, keys and beats. The units of score, PDF, audio-wave and slider timelines aren't indexed. Bars are in `measures`.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `id` | INTEGER | the unit's key | the index |
| `file_id` | INTEGER | its file (`files.id`) | the index |
| `timeline_id` | INTEGER | its timeline (`timelines.id`) | the index |
| `uuid` | TEXT | the unit's id in the file | the file |
| `kind` | TEXT | `hierarchy`, `marker`, `range`, `chord`, `key` or `beat` | the file |
| `start` | REAL | where it starts. A chord or a key starts at its time | the file |
| `end` | REAL | where it ends. For a marker or a beat, its time again; a chord or a key lasts until the next one of its kind in the timeline, the last one until the end of the media. `end` is an SQL keyword: write it `"end"` | the file; computed for chords and keys |
| `label` | TEXT | the unit's label. For a chord or a key, the text TiLiA shows for it; empty for a beat | the file; computed for chords and keys |
| `color` | TEXT | its colour as `#rrggbb`, in lower case; empty without one | the file |
| `comments` | TEXT | its comments; empty without any | the file |

## `hierarchies`

What a hierarchy unit has besides the columns of `components`.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the unit (`components.id`) | the index |
| `level` | INTEGER | its level | the file |
| `parent_id` | INTEGER | the unit it lies in, one level up (`components.id`); empty at the top | computed, as TiLiA finds parents |
| `depth` | INTEGER | how deep it lies: 1 at the top | computed |

## `ranges`

What a range has besides the columns of `components`.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the range (`components.id`) | the index |
| `row_id` | TEXT | the id of its row in the file | the file |
| `row` | TEXT | its row's name | the file |
| `row_folded` | TEXT | its row's name, folded | computed |

## `chords`

What a chord of a harmony timeline has besides the columns of `components`. Before a harmony timeline's first key, chords are read in C major, as TiLiA reads them.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the chord (`components.id`) | the index |
| `step` | INTEGER | its root's letter, as a step from C (0) to B (6) | the file |
| `accidental` | INTEGER | its root's accidental, in semitones: -1 for a flat, 1 for a sharp | the file |
| `quality` | TEXT | its quality, as TiLiA stores it (`major`, `minor`, `dominant-seventh`, …) | the file |
| `inversion` | INTEGER | its inversion: 0 in root position | the file |
| `applied_to` | INTEGER | the degree it is applied to, for an applied chord; 0 otherwise | the file |
| `custom_text` | TEXT | the text the user typed for it, if any | the file |
| `key_id` | INTEGER | the key in force (`components.id` of a key); empty before the first key | computed |
| `root` | TEXT | its root's name, such as `F#` | computed |
| `roman` | TEXT | its Roman numeral in the key in force, such as `V65` | computed |
| `symbol` | TEXT | its chord symbol, such as `G7/B` | computed |
| `key` | TEXT | the key in force, such as `C` or `g` (lower case for minor) | computed |

## `keys`

What a key of a harmony timeline has besides the columns of `components`.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the key (`components.id`) | the index |
| `step` | INTEGER | its tonic's letter, as a step from C (0) to B (6) | the file |
| `accidental` | INTEGER | its tonic's accidental, in semitones | the file |
| `mode` | TEXT | `major` or `minor` | the file |
| `tonic` | TEXT | its tonic's name, such as `Bb` | computed |
| `key` | TEXT | the key's name, such as `Bb` or `g` (lower case for minor) | computed |

## `categories`

The categories of each labelled hierarchy unit, marker and range: one row or more per unit. Chords, keys and beats have none.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the unit (`components.id`) | the index |
| `category` | TEXT | a category of its label, folded, under the label grammar in force for its timeline; without a grammar, the whole label | computed |
| `supertype` | TEXT | the category this one is a subtype of under the grammar, such as `bridge` for `bridge.modern`; empty when it is no subtype, and always without a grammar | computed |

## `positions`

Where each unit of a file with a time map starts and ends in bars and beats. A unit that starts before the first beat has no row, and neither does a unit of a file without a time map.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `component_id` | INTEGER | the unit (`components.id`) | the index |
| `bar` | INTEGER | the printed number of the bar where it starts | computed from the time map |
| `end_bar` | INTEGER | the printed number of the bar where it ends, the end point left out; for a point, its `bar` | computed from the time map |
| `beat` | REAL | the beat where it starts, with a fraction | computed from the time map |
| `pass` | INTEGER | which time through that printed bar number, from 1 | computed from the time map |
| `bar_count` | INTEGER | the bar's place in playing order, from 1 | computed from the time map |
| `bar_label` | TEXT | the bar's printed name, such as `16a` | computed from the time map |
| `bar_beat_count` | INTEGER | how many beats that bar has | computed from the time map |
| `downbeat` | INTEGER | 1 when the unit starts on the bar's first beat, 0 otherwise | computed from the time map |

## `measures`

The bars of each file with a time map, one row per bar in playing order.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `file_id` | INTEGER | the file (`files.id`) | the index |
| `count` | INTEGER | the bar's place in playing order, from 1 | computed from the time map |
| `number` | INTEGER | its printed number | computed from the time map |
| `label` | TEXT | its printed name, such as `16a` | computed from the time map |
| `start` | REAL | its downbeat | computed from the time map |
| `end` | REAL | the next bar's downbeat. Write it `"end"` | computed from the time map |
| `beats` | INTEGER | how many beats it has | computed from the time map |
| `pass` | INTEGER | which pass through a repeat it belongs to: 1 without repeats | computed from the time map |

## `fields`

The fields of files, timelines and units, such as `tags`, `vocabulary`, `generated_by` and users' own, and a file's metadata: one row per value, so a list field has a row per item.

| Column | Type | What it holds | From |
| --- | --- | --- | --- |
| `scope` | TEXT | `file`, `timeline` or `component`: what the field belongs to | the file |
| `owner_id` | INTEGER | the key of that file, timeline or unit (`files.id`, `timelines.id` or `components.id`) | the index |
| `name` | TEXT | the field's name, in lower case, with spaces as `_` | the file |
| `value` | TEXT | one value | the file |

A timeline's `role` and `author` are columns of `timelines`, not rows here.
