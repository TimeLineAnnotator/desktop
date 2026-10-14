# Files the reader refuses

One file for each way a file can be broken: invalid JSON, an empty file, a file that isn't a TiLiA file, another format version, and each broken structure the reader checks for. `test_tla_unreadable.py` names the message, the place (a JSON Pointer) and the line it expects for each.

They are made by `make_broken.py`, which writes them with `json.dumps` directly, so they don't depend on the code under test. Most are one valid file with one thing broken, laid out as the writer lays a file out, so that the line a refusal names is exact. Don't edit them by hand: change the script and run it again.

The last column says whether the format's JSON Schema refuses the file too. Three checks are the core's alone, since JSON Schema can't express them: an id used twice, a reference that names nothing, and a key repeated in one object (FR-090).

| File | What is wrong | The schema |
| --- | --- | --- |
| `another-program.tla` | JSON from another program, not a TiLiA file | refuses |
| `component-without-id.tla` | a component whose id is empty | refuses |
| `cut-short.tla` | a file cut off while it was being saved | can't parse |
| `empty-file.tla` | nothing in it | can't parse |
| `error-page.tla` | a web page saved under the file's name | can't parse |
| `id-in-two-timelines.tla` | a component's id used again in another timeline | core only |
| `id-not-a-uuid.tla` | a component whose id isn't a UUID | refuses |
| `imported-measure-table-named-nowhere.tla` | a timeline imported by measure names a measure table the file doesn't have | core only |
| `joined-to-nothing.tla` | a range is joined to a range its timeline doesn't have | core only |
| `level-missing.tla` | a hierarchy without its level | refuses |
| `measure-table-not-a-beat-timeline.tla` | a measure table that names a timeline that isn't a beat timeline | core only |
| `metadata-not-an-object.tla` | a timeline's metadata given as a list | refuses |
| `newer-format.tla` | written by a newer TiLiA (format 2.0.0) | refuses |
| `not-json.tla` | a comma missing | can't parse |
| `older-draft.tla` | an earlier draft of the format | refuses |
| `repeated-key.tla` | a key given twice in one object | core only |
| `row-named-nowhere.tla` | a range names a row its timeline doesn't have | core only |
| `score-measure-table-named-nowhere.tla` | a score timeline names a measure table the file doesn't have | core only |
| `score-named-nowhere.tla` | a score timeline names a score the file doesn't have | core only |
| `score-without-lines.tla` | a score whose content is an empty list | refuses |
| `second-byte-order-mark.tla` | two byte-order marks: the reader skips one | can't parse |
| `time-as-text.tla` | a marker's time given as text | refuses |
