"""T5's second test: one edit changes only the lines of the entry it edits,
plus at most the separator at the end of the line before it (JSON's comma).

Each line of a file the writer wrote belongs to one value, found by its path
(`("timelines", id, "components", id)`). After an edit, the lines outside the
edited entry must be the same lines, in the same order, with the entry where
it was: so a line diff, `difflib`'s or git's, shows the entry's lines alone."""

import difflib
import json
from pathlib import Path

import pytest

from tilia_core import tla

EVERY_KIND = Path(__file__).parent / "golden" / "every-kind.tla"


def line_paths(lines):
    """The path of the value each line of a file the writer wrote belongs to."""
    decoder = json.JSONDecoder()
    paths = []
    stack = []  # [path, is an object, index of the next item] per open container
    for line in lines:
        text = line.strip()
        if text.endswith(","):
            text = text[:-1]
        if text in ("}", "]"):
            paths.append(stack.pop()[0])
            continue
        if not stack:
            path, value = (), text
        elif stack[-1][1]:
            key, end = decoder.raw_decode(text)
            assert text[end : end + 2] == ": ", line
            path, value = stack[-1][0] + (key,), text[end + 2 :]
        else:
            path, value = stack[-1][0] + (stack[-1][2],), text
            stack[-1][2] += 1
        paths.append(path)
        if value in ("{", "["):
            stack.append([path, value == "{", 0])
    assert not stack
    return paths


def outside(text, path):
    """The lines outside the entry at `path`, and where the entry starts among
    them (None when the text doesn't hold it)."""
    lines = text.split("\n")[:-1]  # the file ends with a newline
    inside = [i for i, p in enumerate(line_paths(lines)) if p[: len(path)] == path]
    if not inside:
        return lines, None
    start, end = inside[0], inside[-1] + 1
    assert inside == list(range(start, end)), "the entry's lines aren't together"
    return lines[:start] + lines[end:], start


def assert_only_the_entry_changed(before, after, path):
    diff = "\n".join(
        difflib.unified_diff(before.split("\n"), after.split("\n"), lineterm="")
    )
    old, old_start = outside(before, path)
    new, new_start = outside(after, path)
    assert old_start is not None or new_start is not None, f"no entry at {path}"
    if old_start is not None and new_start is not None:
        assert old_start == new_start, f"the entry moved:\n{diff}"
    start = new_start if new_start is not None else old_start
    assert len(old) == len(new), diff
    changed = [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
    # At most the separator at the end of the line before the entry.
    assert changed in ([], [start - 1]), diff
    for i in changed:
        assert {old[i], new[i]} == {old[i].rstrip(","), old[i].rstrip(",") + ","}, diff


def named(doc, name):
    return next(tl for tl in doc.timelines.values() if tl.name == name)


def nth(timeline, index):
    return list(timeline.components.values())[index]


def at(timeline, component):
    return ("timelines", timeline.id, "components", component.id)


EDITS = {}


def edit(function):
    EDITS[function.__name__] = function
    return function


@edit
def a_label(doc):
    form = named(doc, "Form")
    nth(form, 1).attrs["label"] = "Hauptsatz"
    return at(form, nth(form, 1))


@edit
def a_start(doc):
    form = named(doc, "Form")
    nth(form, 2).attrs["start"] = 6.5
    return at(form, nth(form, 2))


@edit
def a_start_with_its_default_pre_start(doc):
    form = named(doc, "Form")
    nth(form, 3).attrs["start"] = 14.0
    nth(form, 3).attrs["pre_start"] = 14.0
    return at(form, nth(form, 3))


@edit
def a_files_metadata_value(doc):
    doc.metadata["composer"] = "Schubert, Franz"
    return ("metadata", "composer")


@edit
def a_timelines_metadata_value(doc):
    form = named(doc, "Form")
    form.metadata["author"] = "Felipe"
    return ("timelines", form.id, "metadata", "author")


@edit
def a_components_metadata_value(doc):
    form = named(doc, "Form")
    nth(form, 1).metadata["generated_by"] = "group/B"
    return at(form, nth(form, 1))


@edit
def a_colour(doc):
    cadences = named(doc, "Cadences")
    nth(cadences, 0).attrs["color"] = "#ff0000"
    return at(cadences, nth(cadences, 0))


@edit
def a_colour_where_there_was_none(doc):
    cadences = named(doc, "Cadences")
    nth(cadences, 2).attrs["color"] = "#ff0000"
    return at(cadences, nth(cadences, 2))


@edit
def a_timelines_ordinal(doc):
    cadences = named(doc, "Cadences")
    cadences.ordinal = 11
    return ("timelines", cadences.id, "ordinal")


@edit
def a_measures_number(doc):
    # Bar 1 becomes bar 5: the bars after it follow, and their marks don't change.
    beats = named(doc, "Beats")
    nth(beats, 1).attrs["measure"]["number"] = 5
    return at(beats, nth(beats, 1))


@edit
def a_measures_label(doc):
    beats = named(doc, "Beats")
    nth(beats, 10).attrs["measure"]["label"] = "2b'"
    return at(beats, nth(beats, 10))


@edit
def a_beat_unit(doc):
    beats = named(doc, "Beats")
    nth(beats, 14).attrs["beat_unit"]["units"] = "2+1"
    return at(beats, nth(beats, 14))


@edit
def adding_a_component(doc):
    cadences = named(doc, "Cadences")
    new = tla.Component(id=tla.new_id(), kind="marker", attrs={"time": 10.0})
    cadences.components[new.id] = new
    return at(cadences, new)


@edit
def removing_the_first_component(doc):
    cadences = named(doc, "Cadences")
    gone = cadences.components.pop(nth(cadences, 0).id)
    return at(cadences, gone)


@edit
def removing_a_component(doc):
    cadences = named(doc, "Cadences")
    gone = cadences.components.pop(nth(cadences, 1).id)
    return at(cadences, gone)


@edit
def removing_the_last_component(doc):
    cadences = named(doc, "Cadences")
    gone = cadences.components.pop(nth(cadences, 2).id)
    return at(cadences, gone)


@edit
def adding_a_timeline(doc):
    new = tla.Timeline(
        id=tla.new_id(), kind="marker", ordinal=11, name="Phrases", attrs={"height": 30}
    )
    doc.timelines[new.id] = new
    return ("timelines", new.id)


@edit
def removing_a_timeline(doc):
    gone = doc.timelines.pop(named(doc, "Harmony").id)
    return ("timelines", gone.id)


@edit
def removing_the_last_timeline(doc):
    gone = doc.timelines.pop(list(doc.timelines)[-1])
    return ("timelines", gone.id)


@edit
def adding_a_files_metadata_entry(doc):
    doc.metadata["key"] = "F major"
    return ("metadata", "key")


@edit
def adding_a_timelines_metadata_entry(doc):
    form = named(doc, "Form")
    form.metadata["genre"] = "Lied"
    return ("timelines", form.id, "metadata", "genre")


@edit
def adding_the_first_metadata_entry_of_a_timeline(doc):
    texture = named(doc, "Texture")
    texture.metadata["role"] = "texture"
    return ("timelines", texture.id, "metadata")


@edit
def adding_the_first_metadata_entry_of_a_component(doc):
    cadences = named(doc, "Cadences")
    nth(cadences, 1).metadata["tags"] = ["check"]
    return at(cadences, nth(cadences, 1))


@edit
def removing_a_files_metadata_entry(doc):
    del doc.metadata["performer"]
    return ("metadata", "performer")


@edit
def removing_a_timelines_metadata_entry(doc):
    form = named(doc, "Form")
    del form.metadata["source"]
    return ("timelines", form.id, "metadata", "source")


@edit
def adding_an_ordinary_beat(doc):
    beats = named(doc, "Beats")
    new = tla.Component(id=tla.new_id(), kind="beat", attrs={"time": 2.5})
    beats.components[new.id] = new
    return at(beats, new)


@edit
def removing_an_ordinary_beat(doc):
    beats = named(doc, "Beats")
    gone = beats.components.pop(nth(beats, 2).id)
    return at(beats, gone)


@pytest.mark.parametrize("name", EDITS)
def test_one_edit_changes_only_its_entrys_lines(name):
    before = EVERY_KIND.read_text("utf-8")
    doc = tla.loads(before.encode())
    path = EDITS[name](doc)
    after = tla.canonical_bytes(doc).decode()
    assert after != before
    assert_only_the_entry_changed(before, after, path)


def test_removing_the_only_metadata_entry_of_a_timeline():
    # An empty metadata is left out of a timeline, so the whole of it goes.
    with_role = tla.read(EVERY_KIND)
    harmony = named(with_role, "Harmony")
    harmony.metadata["role"] = "harmony"
    before = tla.canonical_bytes(with_role).decode()
    del harmony.metadata["role"]
    after = tla.canonical_bytes(with_role).decode()
    assert after == EVERY_KIND.read_text("utf-8")
    assert_only_the_entry_changed(before, after, ("timelines", harmony.id, "metadata"))


def test_the_check_sees_a_second_entry_changed():
    before = EVERY_KIND.read_text("utf-8")
    doc = tla.loads(before.encode())
    path = a_label(doc)
    nth(named(doc, "Form"), 2).attrs["label"] = "another"
    after = tla.canonical_bytes(doc).decode()
    with pytest.raises(AssertionError):
        assert_only_the_entry_changed(before, after, path)


def test_the_check_sees_an_entry_moved():
    before = EVERY_KIND.read_text("utf-8")
    lines = before.split("\n")
    paths = line_paths(lines[:-1])
    form = named(tla.loads(before.encode()), "Form")
    path = at(form, nth(form, 0))
    entry = [i for i, p in enumerate(paths) if p[: len(path)] == path]
    second = at(form, nth(form, 1))
    after_second = max(i for i, p in enumerate(paths) if p[: len(second)] == second)
    moved = lines[: entry[0]] + lines[entry[-1] + 1 : after_second + 1]
    moved += lines[entry[0] : entry[-1] + 1] + lines[after_second + 1 :]
    with pytest.raises(AssertionError):
        assert_only_the_entry_changed(before, "\n".join(moved), path)


def test_line_paths_follow_the_layout():
    text = EVERY_KIND.read_text("utf-8")
    lines = text.split("\n")[:-1]
    paths = line_paths(lines)
    assert paths[0] == paths[-1] == ()
    assert paths[1] == ("app_name",)
    titled = [
        p
        for line, p in zip(lines, paths, strict=True)
        if line.strip().startswith('"title"')
    ]
    assert titled == [("metadata", "title")]
    genre = [p for p in paths if p[:2] == ("metadata", "genre")]
    assert genre == [
        ("metadata", "genre"),
        ("metadata", "genre", 0),
        ("metadata", "genre", 1),
        ("metadata", "genre"),
    ]
