"""The prototype's marks in old files' comments: each `tag=` and `gen=` token
moves into the component's `tags` and `generated_by`, and the rest of the
comment stays character for character (contracts/migration.md, *Comment
marks*; research R12). Other `key=value` tokens stay (Q5)."""

import copy
import json
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla.migrate import marks, to_1

OLD = Path(__file__).parent / "old"


def old_file(comments="", *, kind="MARKER", **attrs):
    """An old file whose one component, of `kind`, has these comments."""
    timeline_kind, component = {
        "HIERARCHY": (
            "Hierarchy",
            {"start": 0, "end": 10, "level": 1, "label": "A", "comments": comments},
        ),
        "MARKER": ("Marker", {"time": 5, "label": "PAC", "comments": comments}),
        "RANGE": (
            "Range",
            {"start": 0, "end": 1, "row_id": "Dw5p2E", "comments": comments},
        ),
        "HARMONY": ("Harmony", {"time": 0, "step": 0, "comments": comments}),
        "MODE": ("Harmony", {"time": 0, "step": 5, "comments": comments}),
    }[kind]
    timeline = {
        "kind": timeline_kind,
        "name": "Analysis",
        "ordinal": 1,
        "height": 30,
        "is_visible": True,
        "components": {"2": {**component, **attrs, "kind": kind, "hash": "0e1f"}},
    }
    if kind == "RANGE":
        timeline["rows"] = [{"id": "Dw5p2E", "name": "Row 0"}]
    return {
        "file_path": "",
        "media_path": "",
        "media_metadata": {"title": "Piece"},
        "timelines": {"1": timeline},
        "app_name": "TiLiA",
        "version": "0.6.0",
    }


def loads(content):
    return tla.loads(json.dumps(content).encode())


def the_component(doc):
    (timeline,) = doc.timelines.values()
    (component,) = timeline.components.values()
    return component


def migrated(comments, **kwargs):
    """The component that an old file's component with these comments becomes."""
    return the_component(loads(old_file(comments, **kwargs)))


def stored_component(comments, **kwargs):
    """The component as the migrated file stores it."""
    content = json.loads(tla.canonical_bytes(loads(old_file(comments, **kwargs))))
    (timeline,) = content["timelines"].values()
    (component,) = timeline["components"].values()
    return component


# The marks move; the rest of the comment stays as it was


def test_a_tag_and_a_generator_move_into_metadata():
    component = migrated("tag=check gen=group/A")
    assert component.metadata == {"tags": ["check"], "generated_by": "group/A"}
    assert component.attrs["comments"] == ""


@pytest.mark.parametrize(
    "comments, rest",
    [
        # After the analyst's own text, as the prototype appends them.
        (
            "Cadence à  la Haydn\t(see m. 12) tag=check gen=group/A",
            "Cadence à  la Haydn\t(see m. 12)",
        ),
        # Before it, and around it: each mark goes with one separator.
        ("tag=check gen=group/A  two  spaces ", " two  spaces "),
        ("first  tag=check  second gen=group/A\nthird", "first   second\nthird"),
        ("  tag=check gen=group/A", " "),
        ("tag=check\t\tgen=group/A", ""),
        ("tag=check\t\t\tgen=group/A", "\t"),
        # Text over several lines.
        ("Line one.\nLine two.\ntag=check\ngen=group/A", "Line one.\nLine two."),
    ],
)
def test_the_rest_of_the_comment_stays_character_for_character(comments, rest):
    component = migrated(comments)
    assert component.metadata == {"tags": ["check"], "generated_by": "group/A"}
    assert component.attrs["comments"] == rest


@pytest.mark.parametrize(
    "comments, rest",
    [
        ("blank|tag=check|gen=group/A", "blank"),
        ("tag=check|gen=group/A|blank", "blank"),
        ("blank|tag=check gen=group/A", "blank"),
        ("tag=check|gen=group/A", ""),
        ("a|tag=check|b gen=group/A", "a|b"),
        ("a||tag=check|gen=group/A", "a|"),
        ("|tag=check|gen=group/A|", "|"),
    ],
)
def test_marks_separated_by_a_bar_move(comments, rest):
    component = migrated(comments)
    assert component.metadata == {"tags": ["check"], "generated_by": "group/A"}
    assert component.attrs["comments"] == rest


@pytest.mark.parametrize("kind", ["HIERARCHY", "MARKER", "RANGE", "HARMONY", "MODE"])
def test_marks_move_in_every_kind_with_comments(kind):
    component = migrated("note tag=check gen=group/A", kind=kind)
    assert component.metadata == {"tags": ["check"], "generated_by": "group/A"}
    assert component.attrs["comments"] == "note"


def test_tags_keep_their_order():
    component = migrated("tag=enclosing tag=recheck tag=Satz")
    assert component.metadata == {"tags": ["enclosing", "recheck", "Satz"]}


def test_a_repeated_tag_is_kept_once():
    component = migrated("tag=check tag=recheck tag=check")
    assert component.metadata == {"tags": ["check", "recheck"]}
    assert component.attrs["comments"] == ""


def test_a_tag_repeated_in_another_normal_form_is_kept_once():
    # Tags are text, compared in NFC like all text.
    component = migrated(f"tag=Übergang tag={unicodedata.normalize('NFD', 'Übergang')}")
    assert component.metadata == {"tags": ["Übergang"]}


def test_one_generator_is_a_text():
    assert migrated("gen=cat/B").metadata == {"generated_by": "cat/B"}


def test_two_generators_give_a_list_in_order():
    component = migrated("gen=group/A x gen=cat/B")
    assert component.metadata == {"generated_by": ["group/A", "cat/B"]}
    assert component.attrs["comments"] == "x"


def test_a_tag_alone_gives_tags_only():
    assert migrated("tag=check").metadata == {"tags": ["check"]}


def test_tags_come_before_the_generator_whatever_the_comments_order():
    # In the order layout.md lists a component's fields.
    component = stored_component("gen=group/A tag=check")
    assert list(component["metadata"].items()) == [
        ("tags", ["check"]),
        ("generated_by", "group/A"),
    ]


@pytest.mark.parametrize(
    "token, value",
    [
        ("tag=a=b", "a=b"),
        ("tag=Hauptsatz/Überleitung", "Hauptsatz/Überleitung"),
        ("tag=", ""),  # a mark, as the prototype splits it, with an empty value
    ],
)
def test_a_marks_value_is_everything_after_its_key(token, value):
    component = migrated(f"x {token}")
    assert component.metadata == {"tags": [value]}
    assert component.attrs["comments"] == "x"


# What stays in the comment


@pytest.mark.parametrize(
    "comments, rest",
    [
        (
            "src_start=consensus src_end=a true_end=1.0 tag=check",
            "src_start=consensus src_end=a true_end=1.0",
        ),
        ("blank|src_start=consensus|gen=group/A", "blank|src_start=consensus"),
        ("true_end=12.5 gen=group/A src_end=b", "true_end=12.5 src_end=b"),
    ],
)
def test_the_s4_pipelines_tokens_stay_in_the_comment(comments, rest):
    component = migrated(comments)
    assert component.attrs["comments"] == rest
    assert set(component.metadata) <= {"tags", "generated_by"}


@pytest.mark.parametrize(
    "comments",
    [
        "",
        "A plain comment.",
        "Cadence à  la Haydn\t(see m. 12)  ",
        "tag",  # a word, not a mark
        "tags=check",
        "TAG=check",
        "Tag=check",
        "gene=x",
        "xtag=check",
        "label=tag=check",
        "(tag=check)",
        "tag:check",
        "tag =check",
        "src_start=consensus src_end=a true_end=1.0",
        "blank|src_start=consensus",
    ],
)
def test_a_comment_without_marks_is_unchanged(comments):
    component = migrated(comments)
    assert component.attrs["comments"] == comments
    assert component.metadata == {}


def test_the_marks_change_nothing_else_in_the_component():
    # Marks or not, the rest of the migration is the same.
    expected = stored_component("Plain.")
    expected["metadata"] = {"tags": ["check"]}
    assert stored_component("Plain. tag=check") == expected


def test_a_comment_left_empty_is_left_out_of_the_file():
    # As `comments` is at its default; a legacy score's note, which keeps
    # every attribute, writes it empty (below).
    component = stored_component("tag=check gen=group/A")
    assert "comments" not in component
    assert component["metadata"] == {"tags": ["check"], "generated_by": "group/A"}


def test_a_comment_left_empty_is_left_out_of_the_migrated_content():
    # As every attribute at its default is, before the document id is
    # derived from that content.
    migrated = to_1.migrate(old_file("tag=check gen=group/A"))
    (timeline,) = migrated.content["timelines"].values()
    (component,) = timeline["components"].values()
    assert "comments" not in component
    assert component["metadata"] == {"tags": ["check"], "generated_by": "group/A"}


def test_a_migrated_file_reads_back_with_its_fields():
    doc = loads(old_file("Nice. tag=check gen=group/A"))
    data = tla.canonical_bytes(doc)
    again = tla.loads(data)
    assert the_component(again).metadata == {
        "tags": ["check"],
        "generated_by": "group/A",
    }
    assert the_component(again).attrs["comments"] == "Nice."
    assert tla.canonical_bytes(again) == data


# Only known kinds' comments


def test_a_component_of_a_kind_the_core_doesnt_know_is_unchanged():
    content = old_file()
    content["timelines"]["1"]["components"]["3"] = {
        "time": 1,
        "comments": "x tag=check",
        "kind": "LYRIC",
    }
    doc = loads(content)
    (timeline,) = doc.timelines.values()
    lyric = next(c for c in timeline.components.values() if c.kind != "marker")
    assert lyric.extra["comments"] == "x tag=check"
    assert lyric.metadata == {}


def test_a_timeline_of_a_kind_the_core_doesnt_know_is_unchanged():
    content = old_file()
    content["timelines"]["9"] = {
        "kind": "Lyrics",
        "name": "Words",
        "ordinal": 2,
        "components": {"10": {"kind": "LYRIC", "comments": "x tag=check"}},
    }
    doc = loads(content)
    lyrics = next(tl for tl in doc.timelines.values() if tl.name == "Words")
    assert lyrics.raw["components"]["10"] == {
        "kind": "LYRIC",
        "comments": "x tag=check",
    }


def test_a_comments_key_on_a_kind_without_comments_is_unchanged():
    # A beat has no comments: such a key is one the core doesn't know, kept
    # as it is.
    content = old_file()
    content["timelines"]["9"] = {
        "kind": "Beat",
        "name": "Measures",
        "ordinal": 2,
        "height": 35,
        "beat_pattern": [4],
        "measure_numbers": [1],
        "beats_in_measure": [1],
        "measures_to_force_display": [],
        "components": {"10": {"time": 0.0, "kind": "BEAT", "comments": "tag=check"}},
    }
    doc = loads(content)
    beats = next(tl for tl in doc.timelines.values() if tl.name == "Measures")
    (beat,) = beats.components.values()
    assert beat.extra == {"comments": "tag=check"}
    assert beat.metadata == {}


MISPLACED = {
    "a marker in a hierarchy timeline": ("HIERARCHY", {"time": 1, "kind": "MARKER"}),
    "a hierarchy in a marker timeline": (
        "MARKER",
        {"start": 0, "end": 1, "level": 1, "kind": "HIERARCHY"},
    ),
    "a mode in a marker timeline": ("MARKER", {"time": 1, "kind": "MODE"}),
}


@pytest.mark.parametrize("case", MISPLACED)
def test_marks_stay_in_a_component_its_timeline_doesnt_hold(case):
    # Such a component is kept as it is, as the check keeps it, with a
    # warning: its comments aren't read for marks.
    timeline_kind, component = MISPLACED[case]
    content = old_file(kind=timeline_kind)
    content["timelines"]["1"]["components"]["3"] = {
        **component,
        "comments": "y tag=check gen=group/A",
    }
    migrated = to_1.migrate(copy.deepcopy(content))
    (timeline,) = migrated.content["timelines"].values()
    (kept,) = [
        c for c in timeline["components"].values() if c["kind"] == component["kind"]
    ]
    assert kept["comments"] == "y tag=check gen=group/A"
    assert "metadata" not in kept
    assert "marks_moved" not in migrated.changes
    doc = loads(content)
    (timeline,) = doc.timelines.values()
    (read,) = [
        c for c in timeline.components.values() if isinstance(c.kind, tla.UnknownKind)
    ]
    assert read.extra["comments"] == "y tag=check gen=group/A"
    assert read.metadata == {}


def test_marks_still_move_beside_a_component_its_timeline_doesnt_hold():
    content = old_file("x tag=check", kind="HIERARCHY")
    content["timelines"]["1"]["components"]["3"] = {
        "time": 1,
        "comments": "y tag=check",
        "kind": "MARKER",
    }
    migrated = to_1.migrate(copy.deepcopy(content))
    assert migrated.changes == {"marks_moved": 1}
    (timeline,) = loads(content).timelines.values()
    (section,) = [c for c in timeline.components.values() if c.kind == "hierarchy"]
    assert (section.attrs["comments"], section.metadata) == ("x", {"tags": ["check"]})


# A legacy score's notes, which keep every attribute (FR-022)


def with_note_comment(comments):
    """TiLiA 0.7.0's file, its score timeline's note with these comments."""
    content = json.loads((OLD / "0.7.0.tla").read_bytes())
    (score,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Score"]
    (note,) = [c for c in score["components"].values() if c["kind"] == "NOTE"]
    note["comments"] = comments
    return content


def the_note(doc):
    (score,) = [tl for tl in doc.timelines.values() if tl.kind == "score"]
    (note,) = [c for c in score.components.values() if c.kind == "note"]
    return note


def test_marks_move_in_a_legacy_scores_note():
    note = the_note(loads(with_note_comment("x  tag=check gen=group/A")))
    assert note.metadata == {"tags": ["check"], "generated_by": "group/A"}
    assert note.attrs["comments"] == "x "


def test_a_notes_comment_left_empty_is_written_empty():
    # A legacy score's components write every attribute, as TiLiA 0.7 did,
    # so the comment the marks leave empty is written "", not left out.
    doc = loads(with_note_comment("tag=check gen=group/A"))
    assert the_note(doc).attrs["comments"] == ""
    content = json.loads(tla.canonical_bytes(doc))
    (score,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Score"]
    (note,) = [c for c in score["components"].values() if c["kind"] == "NOTE"]
    assert note["comments"] == ""
    assert note["metadata"] == {"tags": ["check"], "generated_by": "group/A"}
    assert list(note)[-2:] == ["display_accidental", "metadata"]


def test_a_notes_marks_are_counted():
    migrated = to_1.migrate(with_note_comment("tag=check gen=group/A"))
    plain = to_1.migrate(with_note_comment(""))
    assert migrated.changes["marks_moved"] == plain.changes["marks_moved"] + 2


# The old files the tests read (tests/tla/old/README.md), whose comments
# hold marks

EXPOSITION = (
    "hierarchy",
    "Exposição",
    {"tags": ["p1"], "generated_by": "ai"},
    "first theme",
)
# Each file's components with metadata, as (kind, label, metadata,
# comments), in timeline order, and the number of marks moved.
OLD_FILES_MARKS = {
    "0.0.96.tla": ([EXPOSITION], 2),
    "0.0.96-saved-by-0.7.0.tla": ([EXPOSITION], 2),
    "0.5.15.tla": ([EXPOSITION], 2),
    "0.5.15-saved-by-0.7.0.tla": ([EXPOSITION], 2),
    "0.5.15.0-many-beats.tla": ([], 0),
    "0.6.0-s4-10.tla": ([], 0),
    "0.7.0.tla": ([EXPOSITION, ("range", "", {"tags": ["bass"]}, "")], 3),
}


def test_there_is_an_entry_for_each_old_file():
    assert sorted(OLD_FILES_MARKS) == sorted(path.name for path in OLD.glob("*.tla"))


@pytest.mark.parametrize("name", sorted(OLD_FILES_MARKS))
def test_the_old_files_marks_move(name):
    # "tag=p1 first theme gen=ai" on a section, and "tag=bass" on a range.
    expected, _ = OLD_FILES_MARKS[name]
    doc = tla.read(OLD / name)
    timelines = sorted(doc.timelines.values(), key=lambda tl: tl.ordinal)
    found = [
        (c.kind, c.attrs.get("label"), c.metadata, c.attrs.get("comments"))
        for tl in timelines
        if not isinstance(tl.kind, tla.UnknownKind)
        for c in tl.components.values()
        if c.metadata
    ]
    assert found == expected


@pytest.mark.parametrize("name", sorted(OLD_FILES_MARKS))
def test_the_old_files_marks_are_counted(name):
    _, count = OLD_FILES_MARKS[name]
    changes = to_1.migrate(json.loads((OLD / name).read_bytes())).changes
    assert changes.get("marks_moved", 0) == count


def test_the_old_files_range_is_written_without_its_emptied_comment():
    content = json.loads(tla.canonical_bytes(tla.read(OLD / "0.7.0.tla")))
    (voices,) = [tl for tl in content["timelines"].values() if tl["kind"] == "Range"]
    (bass,) = [c for c in voices["components"].values() if "metadata" in c]
    assert bass["metadata"] == {"tags": ["bass"]}
    assert "comments" not in bass


# An old component that already has metadata (only a file made by hand has)


def test_marks_join_the_tags_and_generator_a_component_already_has():
    content = old_file("tag=check tag=new gen=group/B")
    content["timelines"]["1"]["components"]["2"]["metadata"] = {
        "mine": "x",
        "tags": ["old", "check"],
        "generated_by": "group/A",
    }
    component = the_component(loads(content))
    assert component.metadata == {
        "mine": "x",
        "tags": ["old", "check", "new"],
        "generated_by": ["group/A", "group/B"],
    }
    assert component.attrs["comments"] == ""


def test_a_tag_and_a_generator_given_as_text_join_as_lists():
    content = old_file("tag=new gen=group/B")
    content["timelines"]["1"]["components"]["2"]["metadata"] = {
        "generated_by": ["group/A"],
        "tags": "old",
    }
    assert the_component(loads(content)).metadata == {
        "generated_by": ["group/A", "group/B"],
        "tags": ["old", "new"],
    }


def test_marks_are_added_after_the_fields_a_component_already_has():
    content = old_file("tag=check")
    content["timelines"]["1"]["components"]["2"]["metadata"] = {"mine": "x"}
    assert list(the_component(loads(content)).metadata.items()) == [
        ("mine", "x"),
        ("tags", ["check"]),
    ]


@pytest.mark.parametrize(
    "metadata, place",
    [
        (["x"], "/metadata"),
        ({"tags": 5}, "/metadata/tags"),
        ({"generated_by": ["a", 5]}, "/metadata/generated_by/1"),
    ],
)
def test_marks_stay_where_the_metadata_is_refused(metadata, place):
    # The check refuses such a metadata; the marks aren't moved into it.
    content = old_file("tag=check gen=group/A")
    content["timelines"]["1"]["components"]["2"]["metadata"] = metadata
    with pytest.raises(tla.UnreadableFile) as raised:
        loads(content)
    assert raised.value.place.endswith(place)


# The counts of the migration report (FR-102)


def test_the_marks_moved_are_counted():
    content = old_file("tag=check tag=check gen=group/A")
    content["timelines"]["1"]["components"]["3"] = {
        "time": 6,
        "comments": "x|gen=cat/B src_start=a",
        "kind": "MARKER",
    }
    migrated = to_1.migrate(content)
    assert migrated.changes == {"marks_moved": 4}


def test_marks_in_several_timelines_are_counted_together():
    content = old_file("tag=check", kind="HIERARCHY")
    other = old_file("gen=group/A", kind="MARKER")["timelines"]["1"]
    content["timelines"]["5"] = {**other, "ordinal": 2}
    assert to_1.migrate(content).changes == {"marks_moved": 2}


@pytest.mark.parametrize("comments", ["", "a plain comment", "src_start=a"])
def test_a_file_without_marks_counts_none(comments):
    assert "marks_moved" not in to_1.migrate(old_file(comments)).changes


def test_the_count_sits_beside_the_migrations_other_counts():
    content = old_file("tag=check", kind="HIERARCHY", formal_type="sonata")
    assert to_1.migrate(content).changes == {
        "formal_values_dropped": 1,
        "marks_moved": 1,
    }


def test_moving_marks_adds_no_warning():
    assert loads(old_file("tag=check gen=group/A")).warnings == []


# The document id


def test_the_document_id_is_the_same_at_every_read():
    content = old_file("x tag=check gen=group/A")
    first = loads(copy.deepcopy(content))
    assert loads(content).document_id == first.document_id


def test_the_document_id_changes_with_the_marks():
    # The id is derived from the migrated content, where the marks are fields.
    ids = {
        loads(old_file(comments)).document_id
        for comments in ("x", "x tag=check", "x tag=other", "x gen=group/A")
    }
    assert len(ids) == 4


@pytest.mark.parametrize(
    "comments", ["tag=check gen=group/A", "x tag=check gen=group/A"]
)
def test_the_document_id_is_that_of_the_marks_as_fields(comments):
    # A file whose marks are already fields, as only a hand-edited one can
    # be, gets the same id: it is derived from the migrated content.
    fields = old_file(comments.removesuffix("tag=check gen=group/A").rstrip())
    fields["timelines"]["1"]["components"]["2"]["metadata"] = {
        "tags": ["check"],
        "generated_by": "group/A",
    }
    assert loads(old_file(comments)).document_id == loads(fields).document_id


# The split itself


@pytest.mark.parametrize(
    "comment, rest, tags, generated_by, count",
    [
        ("", "", [], [], 0),
        ("plain", "plain", [], [], 0),
        ("tag=a", "", ["a"], [], 1),
        ("tag=a tag=a", "", ["a"], [], 2),
        ("gen=x gen=x", "", [], ["x", "x"], 2),
        ("a tag=b c", "a c", ["b"], [], 1),
        ("a tag=b", "a", ["b"], [], 1),  # a no-break space separates too
        ("a　tag=b c", "a c", ["b"], [], 1),
    ],
)
def test_split(comment, rest, tags, generated_by, count):
    split = marks.split(comment)
    assert (split.comment, split.tags, split.generated_by, split.count) == (
        rest,
        tags,
        generated_by,
        count,
    )
