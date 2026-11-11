"""The seam between a `tla.Document` and TiLiA's state.

An edit is made on the state, as TiLiA's objects would make it, and on a second
read of the file through `attrs`, as the core's API makes it. The two documents
must give the same bytes.
"""

import ast
import copy
import difflib
import hashlib
import json
import sys
from pathlib import Path

import pytest

from tilia.file import tla_bridge
from tilia.file.media_metadata import MediaMetadata
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind
from tilia.timelines.hash_timelines import hash_function
from tilia_core import rules, tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EVERY_KIND = FILES / "golden" / "every-kind.tla"
EMPTY = FILES / "golden" / "empty.tla"
UNKNOWN = FILES / "golden" / "unknown.tla"
OLD_SCORE = FILES / "old" / "0.7.0-osmd.tla"
OLD = sorted((FILES / "old").glob("*.tla"))
ALL_FILES = [EVERY_KIND, EMPTY, UNKNOWN, *OLD]


def ids_of(paths):
    return [path.name for path in paths]


def make_id(number):
    """A valid id, after those of WP3's files."""
    return f"019b76da-f000-7000-8000-{number:012d}"


NEW = make_id(999)


def full_state(doc):
    """The state as `App.get_app_state` gives it: `MediaMetadata` puts its required
    fields first, and the media length among them."""
    fields = {**doc.metadata, "media length": doc.media_length or 0}
    return {
        "media_metadata": dict(MediaMetadata.from_dict(fields)),
        "media_path": doc.media_path,
        "timelines": tla_bridge.state_of(doc),
        "timelines_hash": "",
    }


class Opened:
    """A document with the state it was opened to, and the state after the edits."""

    def __init__(self, doc):
        self.doc = doc
        self.synced = full_state(doc)
        self.current = copy.deepcopy(self.synced)
        self.removed = {}
        self.bytes_read = tla.canonical_bytes(doc)

    @classmethod
    def read(cls, path):
        return cls(tla.read(path))

    @classmethod
    def from_content(cls, content):
        return cls(tla.loads(json.dumps(content).encode()))

    @property
    def timelines(self):
        return self.current["timelines"]

    def timeline(self, timeline_id):
        return self.timelines[timeline_id]

    def component(self, timeline_id, component_id):
        return self.timelines[timeline_id]["components"][component_id]

    def sync(self):
        tla_bridge.apply_changes(
            self.doc, self.synced, self.current, removed=self.removed
        )
        self.synced = copy.deepcopy(self.current)

    def bytes(self):
        return tla.canonical_bytes(self.doc)

    def edit_component(self, timeline_id, component_id, **changes):
        edit(self.component(timeline_id, component_id), **changes)

    def edit_timeline(self, timeline_id, **changes):
        edit(self.timeline(timeline_id), **changes)

    def delete_component(self, timeline_id, component_id):
        del self.timeline(timeline_id)["components"][component_id]

    def add_component(self, timeline_id, component_id, kind, **attrs):
        self.timeline(timeline_id)["components"][component_id] = {
            **attrs,
            "kind": kind,
            "hash": f"hash of {component_id}",
        }

    def swap_ordinals(self, first, second):
        one, other = self.timeline(first), self.timeline(second)
        ordinals = one["ordinal"], other["ordinal"]
        edit(one, ordinal=ordinals[1])
        edit(other, ordinal=ordinals[0])

    def add_timeline(self, timeline_id, kind="Marker", **attrs):
        below = max((tl["ordinal"] for tl in self.timelines.values()), default=0)
        self.timelines[timeline_id] = {
            "kind": kind,
            "name": "New",
            "height": 30,
            "is_visible": True,
            "ordinal": below + 1,
            "measure_table": None,
            "fields": {},
            "components": {},
            "hash": f"hash of {timeline_id}",
            "components_hash": "",
            **attrs,
        }

    def delete_timeline(self, timeline_id):
        ordinal = self.timelines.pop(timeline_id)["ordinal"]
        for timeline in self.timelines.values():
            if timeline["ordinal"] > ordinal:
                edit(timeline, ordinal=timeline["ordinal"] - 1)


def edit(item, **changes):
    """Changes attributes of a state's timeline or component, and so its digest."""
    item.update(changes)
    item["hash"] = item["hash"] + " edited"


def first_of_kind(doc, kind):
    """The first timeline of this kind in the file, or the test doesn't apply."""
    for timeline in sorted(doc.timelines.values(), key=lambda tl: tl.ordinal):
        if timeline.kind == kind:
            return timeline
    pytest.skip(f"no {kind} timeline in this file")


def first_component(doc, kind):
    """The first component of this kind, with its timeline's id, or the test doesn't
    apply."""
    for timeline in doc.timelines.values():
        for component in timeline.components.values():
            if component.kind == kind:
                return timeline.id, component
    pytest.skip(f"no {kind} in this file")


def changed_lines(before, after):
    """The lines of `before` that went, and those of `after` that came, without
    their indentation or the comma JSON puts between entries."""
    diff = difflib.ndiff(before.decode().splitlines(), after.decode().splitlines())
    gone, came = [], []
    for line in diff:
        if line.startswith("- "):
            gone.append(line[2:].strip().rstrip(","))
        elif line.startswith("+ "):
            came.append(line[2:].strip().rstrip(","))
    return gone, came


def file_with(timelines, *, scores=(), metadata=None, media=None):
    """The content of a file in the current format."""
    return {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": make_id(0),
        "time_unit": "seconds",
        "media": media or {"path": "", "length": 100.0},
        "metadata": metadata if metadata is not None else {},
        "timelines": timelines,
        "scores": list(scores),
    }


def marker_timeline(ordinal, **components):
    return {
        "kind": "Marker",
        "name": f"Markers {ordinal}",
        "ordinal": ordinal,
        "height": 30,
        "components": components,
    }


def beat_timeline(beats, *, ordinal=1, **keys):
    return {
        "kind": "Beat",
        "name": "Beats",
        "ordinal": ordinal,
        "height": 35,
        **keys,
        "components": beats,
    }


def beat(time, measure=None, **keys):
    value = {"kind": "BEAT", **keys}
    if time is not None:
        value["time"] = time
    if measure is not None:
        value["measure"] = measure
    return value


class TestNoChange:
    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_gives_the_same_bytes(self, path):
        opened = Opened.read(path)
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_what_the_state_changes_never_reaches_the_document(self, path):
        doc = tla.read(path)
        state = tla_bridge.state_of(doc)
        for timeline in state.values():
            timeline["fields"]["added to the state"] = "value"
            for component in timeline["components"].values():
                component["label"] = "changed on the state"
        assert tla.canonical_bytes(doc) == tla.canonical_bytes(tla.read(path))


class TestSameEditThroughTheCore:
    """Each edit of SC-002's list, on the state and through `attrs`."""

    def assert_same_bytes(self, opened, second):
        opened.sync()
        assert opened.bytes() != opened.bytes_read
        assert opened.bytes() == tla.canonical_bytes(second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    @pytest.mark.parametrize("kind", ["hierarchy", "marker", "range"])
    def test_a_label(self, path, kind):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, kind)
        opened.edit_component(timeline_id, component.id, label="Ein Thema 主題")
        second.timelines[timeline_id].components[component.id].attrs[
            "label"
        ] = "Ein Thema 主題"
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    @pytest.mark.parametrize("kind", ["hierarchy", "marker", "range"])
    def test_a_colour(self, path, kind):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, kind)
        opened.edit_component(timeline_id, component.id, color="#123456")
        second.timelines[timeline_id].components[component.id].attrs[
            "color"
        ] = "#123456"
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_the_time_of_a_point(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, "marker")
        time = component.attrs["time"] + 0.125
        opened.edit_component(timeline_id, component.id, time=time)
        second.timelines[timeline_id].components[component.id].attrs["time"] = time
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_the_time_of_a_beat(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, "beat")
        time = component.attrs["time"] + 0.0625
        opened.edit_component(timeline_id, component.id, time=time)
        second.timelines[timeline_id].components[component.id].attrs["time"] = time
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_the_start_of_a_hierarchy_with_no_pre_start(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, "hierarchy")
        if "pre_start" in component.attrs:
            pytest.skip("this one stores a pre_start")
        start = component.attrs["start"] + 0.125
        # As the setter does: a pre-start at the start follows it.
        opened.edit_component(timeline_id, component.id, start=start, pre_start=start)
        second.timelines[timeline_id].components[component.id].attrs["start"] = start
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_a_metadata_value(self, path):
        opened, second = Opened.read(path), tla.read(path)
        opened.current["media_metadata"]["notes"] = "changed"
        second.metadata["notes"] = "changed"
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_a_timeline_name(self, path):
        opened, second = Opened.read(path), tla.read(path)
        named = [id for id, tl in opened.timelines.items() if tl["kind"] != "Slider"]
        if not named:
            pytest.skip("no named timeline in this file")
        opened.edit_timeline(named[0], name="Renamed")
        second.timelines[named[0]].name = "Renamed"
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_adding_a_marker(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline = first_of_kind(opened.doc, "marker")
        opened.add_component(
            timeline.id,
            NEW,
            "MARKER",
            time=3.25,
            comments="",
            label="new",
            color=None,
        )
        second.timelines[timeline.id].components[NEW] = tla.Component(
            id=NEW, kind="marker", attrs={"time": 3.25, "label": "new"}
        )
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_adding_a_hierarchy(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline = first_of_kind(opened.doc, "hierarchy")
        opened.add_component(
            timeline.id,
            NEW,
            "HIERARCHY",
            start=1.5,
            pre_start=1.5,
            end=2.5,
            post_end=2.5,
            level=9,
            label="",
            color="",
            comments="",
        )
        second.timelines[timeline.id].components[NEW] = tla.Component(
            id=NEW, kind="hierarchy", attrs={"start": 1.5, "end": 2.5, "level": 9}
        )
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_removing_a_marker(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline_id, component = first_component(opened.doc, "marker")
        opened.delete_component(timeline_id, component.id)
        del second.timelines[timeline_id].components[component.id]
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_adding_a_timeline(self, path):
        opened, second = Opened.read(path), tla.read(path)
        opened.add_timeline(NEW)
        top = max((tl.ordinal for tl in second.timelines.values()), default=0)
        second.timelines[NEW] = tla.Timeline(
            id=NEW,
            kind="marker",
            ordinal=top + 1,
            name="New",
            attrs={"height": 30},
        )
        self.assert_same_bytes(opened, second)

    @pytest.mark.parametrize("path", ALL_FILES, ids=ids_of(ALL_FILES))
    def test_removing_a_timeline(self, path):
        opened, second = Opened.read(path), tla.read(path)
        timeline = first_of_kind(opened.doc, "hierarchy")
        opened.delete_timeline(timeline.id)
        del second.timelines[timeline.id]
        self.assert_same_bytes(opened, second)


class TestNewTimelines:
    @pytest.mark.parametrize(
        "kind,attrs",
        [
            ("Slider", {"name": ""}),
            ("Hierarchy", {}),
            ("Marker", {}),
            ("AudioWave", {}),
            (
                "Beat",
                {
                    "beat_pattern": [4, 3],
                    "beats_in_measure": [],
                    "measure_numbers": [],
                    "measures_to_force_display": [],
                    "measure_source": "tapped",
                },
            ),
            ("Harmony", {"level_count": 2, "level_height": 40}),
            (
                "Range",
                {
                    "default_row_height": 30,
                    "rows": [
                        {"id": "aZ3k9P", "name": "Row", "color": None, "height": None}
                    ],
                },
            ),
            ("Pdf", {"path": "score.pdf"}),
            ("Score", {"svg_data": "<svg/>", "viewer_beat_x": {0.0: 1.0}}),
        ],
    )
    def test_of_each_kind_it_reads_back_as_it_was(self, kind, attrs):
        opened = Opened.read(EMPTY)
        opened.add_timeline(NEW, kind=kind, **attrs)
        opened.sync()
        read_back = tla_bridge.state_of(tla.loads(opened.bytes()))[NEW]
        assert read_back["kind"] == kind
        for attr, value in attrs.items():
            if attr != "name":
                assert read_back[attr] == value

    def test_they_stay_in_id_order(self):
        opened = Opened.read(EVERY_KIND)
        early = "00000000-0000-7000-8000-000000000001"
        marker = first_of_kind(opened.doc, "marker")
        opened.add_timeline(early)
        opened.add_component(marker.id, early, "MARKER", time=2.0, label="")
        opened.sync()
        assert next(iter(opened.doc.timelines)) == early
        assert next(iter(marker.components)) == early


class TestLooksOnlyAtWhatChanged:
    def test_a_component_whose_digest_is_the_same_isnt_looked_at(self):
        opened = Opened.read(EVERY_KIND)
        timeline_id, component = first_component(opened.doc, "marker")
        opened.component(timeline_id, component.id)["label"] = "same digest"
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_timeline_whose_digest_is_the_same_isnt_looked_at(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "marker")
        opened.timeline(timeline.id)["name"] = "same digest"
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_an_empty_digest_says_nothing(self):
        # A slider's digest is always empty, as TiLiA makes it.
        opened = Opened.read(EVERY_KIND)
        slider = first_of_kind(opened.doc, "slider")
        for state in (opened.synced, opened.current):
            state["timelines"][slider.id]["hash"] = ""
        opened.timeline(slider.id)["height"] = 77
        opened.sync()
        assert slider.attrs["height"] == 77

    def test_two_components_that_swap_values_are_seen(self):
        # components_hash is the same: it doesn't know whose values they are.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "marker")
        state = opened.timeline(timeline.id)
        one, other = list(timeline.components)[:2]
        first, second = state["components"][one], state["components"][other]
        for attr in ("time", "label", "hash"):
            first[attr], second[attr] = second[attr], first[attr]
        opened.sync()
        assert timeline.components[one].attrs["label"] == first["label"]
        assert timeline.components[other].attrs["label"] == second["label"]

    def test_a_component_replaced_by_one_with_the_same_values_is_seen(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "marker")
        state = opened.timeline(timeline.id)
        old_id = next(iter(timeline.components))
        state["components"][NEW] = state["components"].pop(old_id)
        opened.sync()
        assert NEW in timeline.components and old_id not in timeline.components

    def test_only_the_attribute_that_differs_is_written(self):
        # Something TiLiA filled in, the same on both sides, isn't written.
        opened = Opened.read(EVERY_KIND)
        timeline_id, component = first_component(opened.doc, "marker")
        for state in (opened.synced, opened.current):
            state["timelines"][timeline_id]["components"][component.id][
                "color"
            ] = "#filled"
        opened.edit_component(timeline_id, component.id, label="edited")
        opened.sync()
        assert component.attrs["color"] != "#filled"
        assert component.attrs["label"] == "edited"


class TestKeepsWhatItDoesntShow:
    """FR-004, next to an edit."""

    def test_unknown_keys_and_tags_of_the_edited_component(self):
        opened = Opened.read(UNKNOWN)
        timeline_id, component = first_component(opened.doc, "marker")
        opened.edit_component(timeline_id, component.id, label="edited")
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes()) == (
            ['"label": "known"'],
            ['"label": "edited"'],
        )

    def test_tags_and_generated_by_of_the_edited_component(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "hierarchy")
        tagged = next(c for c in timeline.components.values() if c.metadata)
        opened.edit_component(timeline.id, tagged.id, label="edited")
        opened.sync()
        assert tagged.metadata == {
            "tags": ["check", "Satz"],
            "generated_by": "group/MT",
        }
        assert len(changed_lines(opened.bytes_read, opened.bytes())[0]) == 1

    def test_a_timeline_and_a_component_of_unknown_kinds(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "marker")
        known = next(c for c in timeline.components.values() if c.kind == "marker")
        opened.delete_component(timeline.id, known.id)
        opened.add_timeline(NEW)
        opened.sync()
        written = json.loads(opened.bytes())
        before = json.loads(opened.bytes_read)
        lyrics = next(
            id for id, tl in before["timelines"].items() if tl["kind"] == "Lyrics"
        )
        assert written["timelines"][lyrics] == before["timelines"][lyrics]
        unknown_component = next(
            id
            for id, c in before["timelines"][timeline.id]["components"].items()
            if c["kind"] == "marker"
        )
        assert (
            written["timelines"][timeline.id]["components"][unknown_component]
            == before["timelines"][timeline.id]["components"][unknown_component]
        )

    def test_neither_of_unknown_kind_is_in_the_state(self):
        doc = tla.read(UNKNOWN)
        state = tla_bridge.state_of(doc)
        kinds = {timeline["kind"] for timeline in state.values()}
        assert kinds == {"Beat", "Marker", "Range"}
        markers = state[first_of_kind(doc, "marker").id]["components"]
        assert [component["kind"] for component in markers.values()] == ["MARKER"]

    def test_a_range_row_keeps_what_it_doesnt_show(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "range")
        rows = copy.deepcopy(opened.timeline(timeline.id)["rows"])
        assert set(rows[0]) == {"id", "name", "color", "height"}
        rows[0]["name"] = "Renamed"
        opened.edit_timeline(timeline.id, rows=rows)
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes()) == (
            ['"name": "Row"'],
            ['"name": "Renamed"'],
        )

    def test_the_unknown_keys_of_the_file_a_timeline_a_beat_and_a_mark(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "beat")
        numbers = opened.timeline(timeline.id)["measure_numbers"]
        opened.edit_timeline(
            timeline.id, measure_numbers=[number + 4 for number in numbers]
        )
        opened.edit_timeline(timeline.id, name="Named")
        opened.current["media_metadata"]["title"] = "Other"
        opened.sync()
        written = json.loads(opened.bytes())
        assert written["Alpha"] == 1
        assert written["media"]["x_media"] == "kept"
        assert written["timelines"][timeline.id]["x_timeline"] == "kept"
        beat_with_mark = next(
            c
            for c in written["timelines"][timeline.id]["components"].values()
            if "measure" in c
        )
        assert beat_with_mark["x_beat"] == "kept"
        assert beat_with_mark["measure"] == {"number": 5, "x_mark": "kept"}
        assert beat_with_mark["beat_unit"]["x_unit"] == 0

    def test_a_beat_without_a_time_stays_in_the_document_only(self):
        no_time, timed = make_id(1), make_id(2)
        opened = Opened.from_content(
            file_with(
                {
                    make_id(3): beat_timeline(
                        {no_time: beat(None, {}), timed: beat(1.0, {})}
                    )
                }
            )
        )
        state = opened.timeline(make_id(3))
        assert list(state["components"]) == [timed]
        assert state["beats_in_measure"] == [1]
        opened.edit_timeline(make_id(3), name="Named")
        opened.sync()
        assert no_time in opened.doc.timelines[make_id(3)].components


class TestFileFields:
    """`data-model.md`, *The file's fields*."""

    @staticmethod
    def opened(metadata):
        return Opened.from_content(file_with({}, metadata=metadata))

    def test_metadata_order_stays_the_files(self):
        # TiLiA's MediaMetadata puts title first, adds notes and the media length.
        opened = self.opened({"composer": "Schubert", "title": "Ständchen"})
        assert next(iter(opened.current["media_metadata"])) == "title"
        opened.sync()
        assert opened.bytes() == opened.bytes_read
        assert list(opened.doc.metadata) == ["composer", "title"]

    def test_title_added_by_tilia_doesnt_reach_the_document(self):
        opened = self.opened({"composer": "Schubert"})
        assert opened.current["media_metadata"]["title"] == "Untitled"
        opened.current["media_metadata"]["composer"] = "Schumann"
        opened.sync()
        assert opened.doc.metadata == {"composer": "Schumann"}

    def test_a_reorder_doesnt_reach_the_document(self):
        opened = self.opened({"composer": "Schubert", "genre": "Lied", "title": "T"})
        fields = opened.current["media_metadata"]
        opened.current["media_metadata"] = dict(reversed(list(fields.items())))
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_changed_value_stays_in_its_place(self):
        opened = self.opened({"composer": "Schubert", "genre": "Lied", "title": "T"})
        opened.current["media_metadata"]["genre"] = "Song"
        opened.sync()
        assert list(opened.doc.metadata) == ["composer", "genre", "title"]
        assert opened.doc.metadata["genre"] == "Song"

    def test_an_added_field_goes_last(self):
        opened = self.opened({"composer": "Schubert", "title": "T"})
        fields = opened.current["media_metadata"]
        opened.current["media_metadata"] = {"first in the state": "x", **fields}
        opened.sync()
        assert list(opened.doc.metadata) == ["composer", "title", "first in the state"]

    def test_a_removed_field_goes(self):
        opened = self.opened({"composer": "Schubert", "title": "T"})
        del opened.current["media_metadata"]["composer"]
        opened.sync()
        assert opened.doc.metadata == {"title": "T"}

    def test_a_list_value_isnt_shared_with_the_state(self):
        opened = self.opened({"genre": ["Lied"]})
        opened.current["media_metadata"]["genre"] = ["Song"]
        opened.sync()
        opened.current["media_metadata"]["genre"].append("later")
        assert opened.doc.metadata["genre"] == ["Song"]

    def test_the_media_length_is_a_field_of_the_media(self):
        opened = self.opened({"title": "T"})
        opened.current["media_metadata"]["media length"] = 12.5
        opened.sync()
        assert opened.doc.media_length == 12.5
        assert "media length" not in opened.doc.metadata

    def test_a_media_length_of_0_is_unknown(self):
        opened = self.opened({"title": "T"})
        opened.current["media_metadata"]["media length"] = 0
        opened.sync()
        assert opened.doc.media_length is None

    def test_the_media_path_only_when_it_differs(self):
        media = {"path": "stored/sonata.ogg", "length": None}
        opened = Opened.from_content(file_with({}, media=media))
        opened.sync()
        assert opened.doc.media_path == "stored/sonata.ogg"

    def test_the_media_path_found_elsewhere_isnt_written(self):
        # What the lookup finds is set in `synced` too (R10).
        media = {"path": "stored/sonata.ogg", "length": None}
        opened = Opened.from_content(file_with({}, media=media))
        opened.synced["media_path"] = "C:/found/sonata.ogg"
        opened.current["media_path"] = "C:/found/sonata.ogg"
        opened.sync()
        assert opened.doc.media_path == "stored/sonata.ogg"

    def test_a_changed_media_path_goes_through_the_core(self):
        opened = self.opened({"title": "T"})
        opened.current["media_path"] = "youtube.com/watch?v=dQw4w9WgXcQ"
        opened.sync()
        assert opened.doc.media_path == tla.as_media_path(
            "youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert opened.doc.media_path.startswith("https://")


class TestOrdinals:
    """R6, FR-011."""

    A, B, C, D = make_id(1), make_id(2), make_id(3), make_id(4)

    def four(self):
        return Opened.from_content(
            file_with({id: marker_timeline(i + 1) for i, id in enumerate(self.ids)})
        )

    @property
    def ids(self):
        return [self.A, self.B, self.C, self.D]

    def with_unknown_between(self):
        lyrics = {
            "kind": "Lyrics",
            "name": "Lyrics",
            "ordinal": 2,
            "height": 40,
            "components": {},
        }
        return Opened.from_content(
            file_with(
                {
                    self.A: marker_timeline(1),
                    self.B: lyrics,
                    self.C: marker_timeline(3),
                }
            )
        )

    def test_the_live_ordinal_is_a_position_from_1(self):
        doc = self.with_unknown_between().doc
        doc.timelines[self.C].ordinal = 30
        state = tla_bridge.state_of(doc)
        assert [(id, tl["ordinal"]) for id, tl in state.items()] == [
            (self.A, 1),
            (self.C, 2),
        ]

    def test_a_deletion_changes_no_other_timeline(self):
        opened = self.four()
        opened.delete_timeline(self.B)
        opened.sync()
        ordinals = {id: tl.ordinal for id, tl in opened.doc.timelines.items()}
        assert ordinals == {self.A: 1, self.C: 3, self.D: 4}
        before, after = json.loads(opened.bytes_read), json.loads(opened.bytes())
        del before["timelines"][self.B]
        assert before == after

    def test_a_swap_changes_two(self):
        opened = self.four()
        opened.swap_ordinals(self.B, self.C)
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes()) == (
            ['"ordinal": 2', '"ordinal": 3'],
            ['"ordinal": 3', '"ordinal": 2'],
        )
        assert opened.doc.timelines[self.B].ordinal == 3
        assert opened.doc.timelines[self.C].ordinal == 2

    def test_a_new_timeline_takes_the_ordinal_above_an_unknown_kinds(self):
        lyrics_last = self.with_unknown_between()
        lyrics_last.doc.timelines[self.B].ordinal = 40
        lyrics_last.sync()
        lyrics_last.add_timeline(NEW)
        lyrics_last.sync()
        assert lyrics_last.doc.timelines[NEW].ordinal == 41

    def test_the_golden_files_new_timeline_is_above_its_unknown_kind(self):
        opened = Opened.read(UNKNOWN)
        opened.add_timeline(NEW)
        opened.sync()
        assert opened.doc.timelines[NEW].ordinal == 5

    def test_an_unknown_kind_is_never_touched(self):
        opened = self.with_unknown_between()
        opened.swap_ordinals(self.A, self.C)
        opened.add_timeline(NEW)
        opened.sync()
        ordinals = {id: tl.ordinal for id, tl in opened.doc.timelines.items()}
        assert ordinals == {self.A: 3, self.B: 2, self.C: 1, NEW: 4}

    def test_a_duplicate_shifts_only_those_below_it(self):
        opened = self.four()
        for timeline_id in (self.B, self.C, self.D):
            state = opened.timeline(timeline_id)
            edit(state, ordinal=state["ordinal"] + 1)
        opened.add_timeline(NEW, ordinal=2)
        opened.sync()
        ordinals = {id: tl.ordinal for id, tl in opened.doc.timelines.items()}
        assert ordinals == {self.A: 1, NEW: 2, self.B: 3, self.C: 4, self.D: 5}

    def test_a_timeline_deleted_then_back_has_its_ordinal_and_the_same_bytes(self):
        opened = self.four()
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(self.B)
        opened.sync()
        opened.current = before
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_an_order_tilia_gives_them_on_loading_isnt_written(self):
        # The same on both sides, so no change, whatever the file stores.
        opened = self.four()
        for state in (opened.synced, opened.current):
            state["timelines"][self.A]["ordinal"] = 4
            state["timelines"][self.D]["ordinal"] = 1
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_slider_that_isnt_stored_stays_out(self):
        # Both states hold it, and the document doesn't (FR-007).
        opened = self.four()
        slider = {
            "kind": "Slider",
            "is_visible": True,
            "height": 16,
            "components": {},
            "hash": "",
            "components_hash": "",
        }
        for state in (opened.synced, opened.current):
            for timeline in state["timelines"].values():
                timeline["ordinal"] += 1
            state["timelines"][NEW] = {**slider, "ordinal": 1}
        opened.sync()
        assert opened.bytes() == opened.bytes_read
        opened.swap_ordinals(self.A, self.B)
        opened.sync()
        assert NEW not in opened.doc.timelines
        assert opened.doc.timelines[self.A].ordinal == 2
        assert opened.doc.timelines[self.B].ordinal == 1

    def test_stored_ordinals_with_gaps(self):
        doc = self.four().doc
        doc.timelines[self.B].ordinal = 7
        doc.timelines[self.C].ordinal = 9
        doc.timelines[self.D].ordinal = 30
        order = [self.C, self.A, NEW, self.B]
        # D, left out of `order`, isn't given one, and the free one is above it.
        assert tla_bridge.stored_ordinals(doc, order) == {
            self.C: 1,
            self.A: 7,
            NEW: 9,
            self.B: 31,
        }

    def test_stored_ordinals_of_an_empty_document(self):
        doc = tla.read(EMPTY)
        assert tla_bridge.stored_ordinals(doc, [NEW]) == {NEW: 1}

    def test_stored_ordinals_leaves_out_an_unknown_kind(self):
        doc = self.with_unknown_between().doc
        assert tla_bridge.stored_ordinals(doc, [self.C, self.B, self.A]) == {
            self.C: 1,
            self.A: 3,
        }


class TestPreStartAndPostEnd:
    """FR-003, FR-004."""

    HIERARCHY, RANGE, TL = make_id(1), make_id(2), make_id(3)

    def opened(self, **attrs):
        component = {"kind": "HIERARCHY", "start": 1.0, "end": 2.0, "level": 1, **attrs}
        timeline = {
            "kind": "Hierarchy",
            "ordinal": 1,
            "height": 60,
            "components": {self.HIERARCHY: component},
        }
        return Opened.from_content(file_with({self.TL: timeline}))

    def attrs(self, opened):
        return opened.doc.timelines[self.TL].components[self.HIERARCHY].attrs

    def edit(self, opened, **changes):
        opened.edit_component(self.TL, self.HIERARCHY, **changes)

    def test_unset_ones_are_filled_in_the_state(self):
        component = self.opened().component(self.TL, self.HIERARCHY)
        assert component["pre_start"] == 1.0
        assert component["post_end"] == 2.0

    def test_filled_ones_arent_written(self):
        opened = self.opened()
        self.edit(opened, label="edited")
        opened.sync()
        assert "pre_start" not in self.attrs(opened)
        assert "post_end" not in self.attrs(opened)

    def test_dragged_away_it_is_written(self):
        opened = self.opened()
        self.edit(opened, pre_start=0.5, post_end=2.5)
        opened.sync()
        assert self.attrs(opened)["pre_start"] == 0.5
        assert self.attrs(opened)["post_end"] == 2.5

    def test_a_change_that_leaves_one_equal_writes_it_as_unset(self):
        opened = self.opened(pre_start=0.5, post_end=2.5)
        self.edit(opened, pre_start=1.0, post_end=2.0)
        opened.sync()
        assert "pre_start" not in self.attrs(opened)
        assert "post_end" not in self.attrs(opened)

    def test_moving_the_start_onto_a_stored_pre_start_writes_it_as_unset(self):
        opened = self.opened(pre_start=0.5)
        self.edit(opened, start=0.5)
        opened.sync()
        assert self.attrs(opened)["start"] == 0.5
        assert "pre_start" not in self.attrs(opened)

    def test_moving_the_start_away_from_an_unset_one_writes_it(self):
        # The state keeps it where it was, so the document must say so: unset,
        # it would follow the start.
        opened = self.opened()
        self.edit(opened, start=1.5)
        opened.sync()
        assert self.attrs(opened)["pre_start"] == 1.0

    def test_stored_equal_stays_without_an_edit(self):
        opened = self.opened(pre_start=1.0, post_end=2.0)
        opened.sync()
        assert opened.bytes() == opened.bytes_read
        assert self.attrs(opened)["pre_start"] == 1.0

    def test_stored_equal_stays_when_another_component_is_edited(self):
        opened = self.opened(pre_start=1.0, post_end=2.0)
        opened.add_component(
            self.TL, NEW, "HIERARCHY", start=3.0, end=4.0, level=1, label=""
        )
        opened.sync()
        assert self.attrs(opened)["pre_start"] == 1.0
        assert self.attrs(opened)["post_end"] == 2.0

    def test_stored_equal_goes_when_that_component_is_edited(self):
        opened = self.opened(pre_start=1.0, post_end=2.0)
        self.edit(opened, label="edited")
        opened.sync()
        assert "pre_start" not in self.attrs(opened)
        assert "post_end" not in self.attrs(opened)

    def test_a_digest_that_differs_with_no_attribute_that_does_is_no_edit(self):
        opened = self.opened(pre_start=1.0)
        self.edit(opened)
        opened.sync()
        assert self.attrs(opened)["pre_start"] == 1.0

    def test_a_stored_one_that_differs_stays_as_it_is_after_an_edit(self):
        opened = self.opened(pre_start=0, post_end=3)
        self.edit(opened, label="edited")
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes())[0] == [
            '"label": ""'
        ] or ('"pre_start": 0' in opened.bytes().decode().replace("\n", " "))
        assert type(self.attrs(opened)["pre_start"]) is int

    def test_a_new_one_equal_is_unset(self):
        opened = self.opened()
        opened.add_component(
            self.TL,
            NEW,
            "HIERARCHY",
            start=3.0,
            pre_start=3.0,
            end=4.0,
            post_end=4.0,
            level=1,
        )
        opened.sync()
        attrs = opened.doc.timelines[self.TL].components[NEW].attrs
        assert "pre_start" not in attrs and "post_end" not in attrs

    def test_a_new_one_that_differs_is_written(self):
        opened = self.opened()
        opened.add_component(
            self.TL,
            NEW,
            "HIERARCHY",
            start=3.0,
            pre_start=2.5,
            end=4.0,
            post_end=4.5,
            level=1,
        )
        opened.sync()
        attrs = opened.doc.timelines[self.TL].components[NEW].attrs
        assert attrs["pre_start"] == 2.5 and attrs["post_end"] == 4.5

    def test_a_range_too(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "range")
        stored = next(c for c in timeline.components.values() if "pre_start" in c.attrs)
        opened.edit_component(
            timeline.id,
            stored.id,
            pre_start=stored.attrs["start"],
            post_end=stored.attrs["end"],
        )
        opened.sync()
        assert "pre_start" not in stored.attrs and "post_end" not in stored.attrs


class TestBeatTimelinesStageOne:
    """R14's interim mapping: the lists from the marks, and back."""

    def beats_of(self, opened, timeline_id):
        return opened.doc.timelines[timeline_id].components

    def test_the_lists_come_from_the_measure_table(self):
        doc = tla.read(EVERY_KIND)
        state = tla_bridge.state_of(doc)
        timeline = first_of_kind(doc, "beat")
        beats = state[timeline.id]
        assert beats["beats_in_measure"] == [1, 3, 3, 3, 3, 1, 2, 1]
        assert beats["measure_numbers"] == [0, 1, 2, 1, 2, 2, 3, 4]
        assert beats["measures_to_force_display"] == [2]

    def test_the_lists_of_an_old_file(self):
        doc = tla.read(FILES / "old" / "0.5.15.0-many-beats.tla")
        beats = tla_bridge.state_of(doc)[first_of_kind(doc, "beat").id]
        assert sum(beats["beats_in_measure"]) == 1000
        assert beats["measure_numbers"][:3] == [1, 2, 3]

    def test_the_beat_pattern_through_the_time_map(self):
        doc = tla.read(FILES / "old" / "0.6.0-s4-10.tla")
        timeline = first_of_kind(doc, "beat")
        state = tla_bridge.state_of(doc)[timeline.id]
        assert all(isinstance(bars, int) for bars in state["beat_pattern"])
        assert len(state["beat_pattern"]) > 1

    def test_a_beat_pattern_that_doesnt_parse_is_todays_default(self):
        id = make_id(1)
        opened = Opened.from_content(
            file_with(
                {
                    id: beat_timeline(
                        {make_id(2): beat(0.0, {})}, beat_pattern="not a pattern"
                    )
                }
            )
        )
        assert opened.timeline(id)["beat_pattern"] == [4]
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_an_edited_beat_pattern_is_text(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, beat_pattern=[4, 4, 3])
        opened.sync()
        assert timeline.attrs["beat_pattern"] == "2[4] 3"
        gone, came = changed_lines(opened.bytes_read, opened.bytes())
        assert gone == ['"beat_pattern": "3"'] and came == ['"beat_pattern": "2[4] 3"']

    def test_lists_tilia_fills_in_arent_written(self):
        # The same on both sides, so no change, when a beat's time is edited.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        for state in (opened.synced, opened.current):
            state["timelines"][timeline.id]["measures_to_force_display"] = [0, 1]
        last = timeline.measures.rows[-1].id
        opened.edit_component(timeline.id, last, time=16.5)
        opened.sync()
        gone, came = changed_lines(opened.bytes_read, opened.bytes())
        assert gone == ['"time": 16.0'] and came == ['"time": 16.5']

    def test_a_measure_number_edit_changes_one_mark(self):
        # As set_measure_number leaves the numbers: those after it follow.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, measure_numbers=[0, 1, 2, 1, 2, 2, 10, 11])
        opened.sync()
        gone, came = changed_lines(opened.bytes_read, opened.bytes())
        assert gone == ['"measure": {}']
        assert came == ['"measure": {', '"number": 10', "}"]

    def test_a_number_back_to_what_it_follows_from_is_unset(self):
        # A reset, or an undo: the mark is as it was.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        numbers = opened.timeline(timeline.id)["measure_numbers"]
        opened.edit_timeline(timeline.id, measure_numbers=[0, 1, 2, 1, 2, 2, 10, 11])
        opened.sync()
        opened.edit_timeline(timeline.id, measure_numbers=list(numbers))
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_stored_number_stays_a_number_at_what_it_would_follow_from(self):
        # As the same edit through `attrs` leaves it.
        first, second, tl = make_id(1), make_id(2), make_id(9)
        beats = {first: beat(0.0, {}), second: beat(1.0, {"number": 7})}
        content = file_with({tl: beat_timeline(beats)})
        opened = Opened.from_content(content)
        opened.edit_timeline(tl, measure_numbers=[1, 2])
        opened.sync()
        through_attrs = tla.loads(json.dumps(content).encode())
        through_attrs.timelines[tl].components[second].attrs["measure"]["number"] = 2
        assert opened.bytes() == tla.canonical_bytes(through_attrs)

    def test_a_stored_number_edited_and_back_is_as_the_file_had_it(self):
        tl = make_id(9)
        beats = {
            make_id(1): beat(0.0, {"number": 1}),
            make_id(2): beat(1.0, {"number": 2}),
        }
        opened = Opened.from_content(file_with({tl: beat_timeline(beats)}))
        opened.edit_timeline(tl, measure_numbers=[5, 6])
        opened.sync()
        opened.edit_timeline(tl, measure_numbers=[1, 2])
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_stored_number_that_changes_is_written(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, measure_numbers=[7, 8, 9, 1, 2, 2, 3, 4])
        opened.sync()
        gone, came = changed_lines(opened.bytes_read, opened.bytes())
        assert gone == ['"number": 0'] and came == ['"number": 7']

    def test_force_display(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        rows = timeline.measures.rows
        opened.edit_timeline(timeline.id, measures_to_force_display=[6])
        opened.sync()
        assert timeline.components[rows[6].id].attrs["measure"]["force_display"]
        assert not timeline.components[rows[2].id].attrs["measure"]["force_display"]
        written = json.loads(opened.bytes())["timelines"][timeline.id]["components"]
        assert "force_display" not in written[rows[2].id]["measure"]

    def test_keys_of_a_mark_on_a_beat_still_a_downbeat_stay(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        before = json.loads(opened.bytes_read)["timelines"][timeline.id]["components"]
        rows = timeline.measures.rows
        state = opened.timeline(timeline.id)
        # The last measure gets its beats from the one before.
        opened.edit_timeline(
            timeline.id,
            measure_numbers=[*state["measure_numbers"][:4], 8, 8, 9, 10],
            beats_in_measure=[1, 3, 3, 3, 3, 1, 1, 2],
        )
        opened.sync()
        written = json.loads(opened.bytes())["timelines"][timeline.id]["components"]
        cadenza = rows[5].id
        assert written[cadenza]["measure"] == {
            **before[cadenza]["measure"],
            "number": 8,
        }
        repeat = rows[3].id
        assert written[repeat]["measure"] == before[repeat]["measure"]
        assert written[repeat]["measure"]["metadata"] == {"tags": ["repeat"]}
        assert written[repeat]["measure"]["source"] == "edited"

    def test_a_measure_that_is_gone_leaves_its_mark_for_an_undo(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        rows = timeline.measures.rows
        state = opened.timeline(timeline.id)
        before = copy.deepcopy(state)
        # "Set beat amount": the second measure takes the third one's beats. The
        # third is gone, and the later measures keep their downbeats and marks.
        opened.edit_timeline(
            timeline.id,
            beats_in_measure=[1, 6, 3, 3, 1, 2, 1],
            measure_numbers=[0, 1, 1, 2, 2, 3, 4],
            measures_to_force_display=[],
        )
        opened.sync()
        assert "measure" not in timeline.components[rows[2].id].attrs
        assert timeline.components[rows[3].id].attrs["measure"]["source"] == "edited"
        assert len(opened.removed[f"{rows[2].id}/measure"]) > 0
        opened.current["timelines"][timeline.id] = before
        opened.sync()
        assert opened.bytes() == opened.bytes_read, changed_lines(
            opened.bytes_read, opened.bytes()
        )

    def test_a_new_measure_gets_an_empty_mark(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        state = opened.timeline(timeline.id)
        opened.add_component(timeline.id, NEW, "BEAT", time=17.0)
        opened.edit_timeline(
            timeline.id,
            beats_in_measure=[*state["beats_in_measure"], 1],
            measure_numbers=[*state["measure_numbers"], 5],
        )
        opened.sync()
        mark = json.loads(opened.bytes())["timelines"][timeline.id]["components"][NEW][
            "measure"
        ]
        assert mark == {}

    def test_a_beat_back_where_no_measure_starts_has_no_mark(self):
        # The lists say which beats start a measure, whatever a beat brings back.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        downbeat = timeline.measures.rows[2].id
        state = copy.deepcopy(opened.component(timeline.id, downbeat))
        opened.delete_component(timeline.id, downbeat)
        opened.edit_timeline(timeline.id, beats_in_measure=[1, 3, 2, 3, 3, 1, 2, 1])
        opened.sync()
        opened.timeline(timeline.id)["components"][downbeat] = state
        opened.edit_timeline(timeline.id, beats_in_measure=[1, 6, 3, 3, 1, 2, 1])
        opened.sync()
        assert "measure" not in timeline.components[downbeat].attrs
        assert tla.loads(opened.bytes())

    def test_a_deleted_downbeats_measure_gets_a_new_downbeat(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        rows = timeline.measures.rows
        opened.delete_component(timeline.id, rows[1].id)
        opened.edit_timeline(timeline.id, beats_in_measure=[1, 2, 3, 3, 3, 1, 2, 1])
        opened.sync()
        assert "measure" in timeline.components[rows[1].beats[1]].attrs
        assert tla.loads(opened.bytes())

    def test_a_beat_moved_past_another_moves_the_downbeat(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        rows = timeline.measures.rows
        downbeat, second = rows[1].beats[:2]
        one, other = (
            opened.component(timeline.id, downbeat),
            opened.component(timeline.id, second),
        )
        times = one["time"], other["time"]
        edit(one, time=times[1])
        edit(other, time=times[0])
        opened.sync()
        assert "measure" in timeline.components[second].attrs
        assert "measure" not in timeline.components[downbeat].attrs

    def test_the_table_in_the_document_follows(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, measure_numbers=[0, 1, 2, 1, 2, 2, 10, 11])
        opened.sync()
        assert [row.number for row in timeline.measures.rows] == [
            0,
            1,
            2,
            1,
            2,
            2,
            10,
            11,
        ]

    def test_the_table_follows_a_moved_beat(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        last = timeline.measures.rows[-1].id
        opened.edit_component(timeline.id, last, time=16.5)
        opened.sync()
        assert timeline.measures == tla.measure_table(timeline)

    def test_a_next_keeps_naming_the_same_measures(self):
        # A one-beat measure is deleted: the measures after it keep their downbeats,
        # and a `next` naming the one that is gone names the next, as the core does.
        opened = Opened.read(EVERY_KIND)
        timeline = next(
            tl for tl in opened.doc.timelines.values() if tl.name == "Bars of the score"
        )
        rows = timeline.measures.rows
        opened.delete_component(timeline.id, rows[2].id)
        opened.edit_timeline(
            timeline.id,
            beats_in_measure=[1, 1, 1, 1, 1],
            measure_numbers=[0, 1, 2, 3, 1],
        )
        opened.sync()
        following = timeline.components[rows[1].id].attrs["measure"]["next"]
        assert following == [rows[3].id, rows[3].id]
        assert tla.loads(opened.bytes())

    def test_a_next_with_nothing_after_it_goes(self):
        first, second = make_id(1), make_id(2)
        tl = make_id(3)
        opened = Opened.from_content(
            file_with(
                {
                    tl: beat_timeline(
                        {first: beat(0.0, {"next": [second]}), second: beat(1.0, {})}
                    )
                }
            )
        )
        opened.delete_component(tl, second)
        opened.edit_timeline(tl, beats_in_measure=[1], measure_numbers=[1])
        opened.sync()
        assert "next" not in opened.doc.timelines[tl].components[first].attrs["measure"]
        assert tla.loads(opened.bytes())

    def test_a_closing_tap_stays_in_the_document_only(self):
        tap, tl = make_id(3), make_id(9)
        beats = {
            make_id(1): beat(0.0, {}),
            make_id(2): beat(1.0),
            tap: beat(2.0, closing=True),
        }
        opened = Opened.from_content(file_with({tl: beat_timeline(beats)}))
        state = opened.timeline(tl)
        assert tap not in state["components"]
        assert state["beats_in_measure"] == [2]
        opened.edit_timeline(tl, measure_numbers=[5])
        opened.sync()
        written = json.loads(opened.bytes())["timelines"][tl]["components"]
        assert written[tap] == {"kind": "BEAT", "time": 2.0, "closing": True}

    def test_no_beats_left(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "beat")
        state = opened.timeline(timeline.id)
        for beat_id in list(state["components"]):
            opened.delete_component(timeline.id, beat_id)
        opened.edit_timeline(timeline.id, beats_in_measure=[], measure_numbers=[])
        opened.sync()
        assert not timeline.components
        assert timeline.measures.rows == []

    def test_a_new_beat_timeline_gets_marks(self):
        opened = Opened.read(EMPTY)
        one, two = make_id(1), make_id(2)
        opened.add_timeline(
            NEW,
            kind="Beat",
            beat_pattern=[4],
            beats_in_measure=[1, 1],
            measure_numbers=[1, 2],
            measures_to_force_display=[],
            components={
                one: {"kind": "BEAT", "time": 0.0, "hash": "a"},
                two: {"kind": "BEAT", "time": 1.0, "hash": "b"},
            },
        )
        opened.sync()
        written = json.loads(opened.bytes())["timelines"][NEW]["components"]
        assert written[one] == {"kind": "BEAT", "time": 0.0, "measure": {}}
        assert written[two] == {"kind": "BEAT", "time": 1.0, "measure": {}}


class TestLegacyScores:
    """R16."""

    def opened(self):
        opened = Opened.read(OLD_SCORE)
        timeline = first_of_kind(opened.doc, "score")
        return opened, timeline, opened.doc.scores[timeline.attrs["score"]]

    def test_the_state_holds_the_score(self):
        opened, timeline, score = self.opened()
        state = opened.timeline(timeline.id)
        assert state["svg_data"] == score.text
        assert state["svg_data"].startswith("<svg")
        pairs = score.extra["beat_x"]
        assert pairs
        assert state["viewer_beat_x"] == {float(p): x for p, x in pairs}
        assert all(isinstance(position, float) for position in state["viewer_beat_x"])

    def test_untouched_it_stays(self):
        opened, timeline, score = self.opened()
        opened.edit_timeline(timeline.id, name="Renamed")
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes())[0] == [
            '"name": "Score"'
        ]

    def test_an_import_makes_a_new_score(self):
        opened, timeline, score = self.opened()
        lines = list(score.lines)
        opened.edit_timeline(timeline.id, svg_data="<svg>other</svg>\n")
        opened.sync()
        new = opened.doc.scores[timeline.attrs["score"]]
        assert new is not score and score.id not in opened.doc.scores
        assert new.lines == ["<svg>other</svg>", ""]
        assert new.extra["beat_x"]
        assert score.lines == lines

    def test_edited_positions_are_pairs_in_their_order(self):
        opened, timeline, score = self.opened()
        opened.edit_timeline(timeline.id, viewer_beat_x={2.5: 30.0, 1.0: 10.0})
        opened.sync()
        assert score.extra["beat_x"] == [[1.0, 10.0], [2.5, 30.0]]

    def test_clearing_removes_the_score_and_undo_gets_it_back_whole(self):
        opened, timeline, score = self.opened()
        score_id = score.id
        before = copy.deepcopy(opened.timeline(timeline.id))
        opened.edit_timeline(timeline.id, svg_data="", components={})
        opened.sync()
        assert score_id not in opened.doc.scores
        assert timeline.attrs["score"] is None
        assert tla.loads(opened.bytes())
        opened.current["timelines"][timeline.id] = before
        opened.sync()
        assert opened.doc.scores[score_id] is score
        assert opened.bytes() == opened.bytes_read

    def test_deleting_removes_the_score_and_undo_gets_it_back_whole(self):
        opened, timeline, score = self.opened()
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(timeline.id)
        opened.sync()
        assert score.id not in opened.doc.scores
        assert opened.removed[score.id] is score
        opened.current = before
        opened.sync()
        assert opened.doc.scores[score.id] is score
        assert opened.bytes() == opened.bytes_read

    def test_positions_tilia_fills_in_arent_written(self):
        # The same on both sides, so the score stays as it was (FR-004).
        opened, timeline, score = self.opened()
        for state in (opened.synced, opened.current):
            state["timelines"][timeline.id]["viewer_beat_x"] = {9.0: 9.0}
        opened.edit_timeline(timeline.id, name="Renamed")
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes())[0] == [
            '"name": "Score"'
        ]

    def test_an_mei_score_comes_back_with_its_timeline(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "score")
        mei = opened.doc.scores[timeline.attrs["score"]]
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(timeline.id)
        opened.sync()
        assert mei.id not in opened.doc.scores
        opened.current = before
        opened.sync()
        assert opened.doc.scores[mei.id] is mei
        assert opened.bytes() == opened.bytes_read

    def test_a_score_another_timeline_names_stays(self):
        opened, timeline, score = self.opened()
        other = make_id(1)
        opened.doc.timelines[other] = tla.Timeline(
            id=other,
            kind="score",
            ordinal=9,
            attrs={"height": 1, "score": score.id},
        )
        opened.delete_timeline(timeline.id)
        opened.sync()
        assert score.id in opened.doc.scores

    def test_an_import_makes_a_legacy_score(self):
        opened = Opened.read(EMPTY)
        opened.add_timeline(NEW, kind="Score", svg_data="", viewer_beat_x={})
        opened.sync()
        assert opened.doc.scores == {}
        opened.edit_timeline(
            NEW,
            svg_data="<svg>new</svg>",
            viewer_beat_x={1.0: 12.5},
            measure_table=make_id(5),
        )
        opened.sync()
        timeline = opened.doc.timelines[NEW]
        score = opened.doc.scores[timeline.attrs["score"]]
        assert score.format == "svg-osmd-legacy"
        assert score.text == "<svg>new</svg>"
        assert score.extra["beat_x"] == [[1.0, 12.5]]
        assert timeline.attrs["measure_table"] == make_id(5)

    def test_a_new_score_timeline_with_its_score(self):
        opened = Opened.read(EMPTY)
        opened.add_timeline(
            NEW, kind="Score", svg_data="<svg>new</svg>", viewer_beat_x={}
        )
        opened.sync()
        timeline = opened.doc.timelines[NEW]
        score = opened.doc.scores[timeline.attrs["score"]]
        assert score.extra["beat_x"] == []
        assert tla.loads(opened.bytes())

    def test_an_mei_score_is_kept_and_not_given_to_the_svg_viewer(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "score")
        state = opened.timeline(timeline.id)
        assert state["svg_data"] == ""
        assert state["viewer_beat_x"] == {}
        opened.edit_timeline(timeline.id, name="Renamed")
        opened.sync()
        assert changed_lines(opened.bytes_read, opened.bytes())[0] == [
            '"name": "Score"'
        ]

    def test_an_import_over_an_mei_score_and_its_undo_keep_the_mei(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "score")
        mei = opened.doc.scores[timeline.attrs["score"]]
        opened.edit_timeline(timeline.id, svg_data="<svg>new</svg>", viewer_beat_x={})
        opened.sync()
        assert mei.id not in opened.doc.scores
        assert opened.doc.scores[timeline.attrs["score"]].format == "svg-osmd-legacy"
        opened.edit_timeline(timeline.id, svg_data="")
        opened.sync()
        assert opened.doc.scores[timeline.attrs["score"]] is mei
        assert opened.bytes() == opened.bytes_read

    def test_a_cleared_timeline_with_an_mei_score_keeps_it(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "score")
        opened.edit_timeline(timeline.id, svg_data="", viewer_beat_x={1.0: 2.0})
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_beat_positions_too_short_to_be_pairs_are_left_out(self):
        score, tl = make_id(1), make_id(2)
        opened = Opened.from_content(
            file_with(
                {
                    tl: {
                        "kind": "Score",
                        "ordinal": 1,
                        "height": 160,
                        "score": score,
                        "components": {},
                    }
                },
                scores=[
                    {
                        "id": score,
                        "format": "svg-osmd-legacy",
                        "content": ["<svg/>"],
                        "beat_x": [[1.0, 2.0], [3.0], []],
                    }
                ],
            )
        )
        assert opened.timeline(tl)["viewer_beat_x"] == {1.0: 2.0}


class TestRemoved:
    """R13."""

    def test_a_component_deleted_then_back_has_its_tags(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "hierarchy")
        tagged = next(c for c in timeline.components.values() if c.metadata)
        state = copy.deepcopy(opened.component(timeline.id, tagged.id))
        opened.delete_component(timeline.id, tagged.id)
        opened.sync()
        assert tagged.id not in timeline.components
        assert opened.removed[tagged.id] is tagged
        opened.timeline(timeline.id)["components"][tagged.id] = state
        opened.sync()
        assert timeline.components[tagged.id].metadata["tags"] == ["check", "Satz"]
        assert tagged.id not in opened.removed
        assert opened.bytes() == opened.bytes_read

    def test_it_keeps_its_unknown_keys_too(self):
        opened = Opened.read(UNKNOWN)
        timeline_id, component = first_component(opened.doc, "marker")
        state = copy.deepcopy(opened.component(timeline_id, component.id))
        opened.delete_component(timeline_id, component.id)
        opened.sync()
        opened.timeline(timeline_id)["components"][component.id] = state
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_back_with_a_value_tilia_holds_differently_is_no_edit(self):
        # TiLiA holds a time signature's numerator as text: the digests agree.
        opened = Opened.read(OLD_SCORE)
        timeline_id, component = first_component(opened.doc, "time_signature")
        state = copy.deepcopy(opened.component(timeline_id, component.id))
        state["numerator"] = str(state["numerator"])
        opened.delete_component(timeline_id, component.id)
        opened.sync()
        opened.timeline(timeline_id)["components"][component.id] = state
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_back_with_another_value_has_it_as_well(self):
        # The gate can restore a state other than the last one synced.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "hierarchy")
        tagged = next(c for c in timeline.components.values() if c.metadata)
        state = copy.deepcopy(opened.component(timeline.id, tagged.id))
        opened.delete_component(timeline.id, tagged.id)
        opened.sync()
        edit(state, label="restored")
        opened.timeline(timeline.id)["components"][tagged.id] = state
        opened.sync()
        back = timeline.components[tagged.id]
        assert back.attrs["label"] == "restored"
        assert back.metadata["tags"] == ["check", "Satz"]

    def test_a_timeline_deleted_then_back_is_whole(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "beat")
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(timeline.id)
        opened.sync()
        assert opened.removed[timeline.id] is timeline
        assert timeline.id not in opened.doc.timelines
        opened.current = before
        opened.sync()
        assert opened.doc.timelines[timeline.id] is timeline
        assert opened.bytes() == opened.bytes_read

    def test_a_timeline_back_with_another_value_has_it(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "marker")
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(timeline.id)
        opened.sync()
        opened.current = before
        edit(opened.timeline(timeline.id), name="Renamed")
        opened.sync()
        assert timeline.name == "Renamed"
        assert timeline.components

    def test_a_timeline_back_with_a_component_it_lost_before(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "hierarchy")
        first = copy.deepcopy(opened.current)
        tagged = next(c for c in timeline.components.values() if c.metadata)
        opened.delete_component(timeline.id, tagged.id)
        opened.sync()
        opened.delete_timeline(timeline.id)
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_row_deleted_then_back_keeps_what_it_doesnt_show(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "range")
        rows = copy.deepcopy(opened.timeline(timeline.id)["rows"])
        opened.edit_timeline(timeline.id, rows=[])
        opened.sync()
        opened.edit_timeline(timeline.id, rows=rows)
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_row_of_the_same_id_in_another_timeline_isnt_taken_for_it(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "range")
        rows = copy.deepcopy(opened.timeline(timeline.id)["rows"])
        opened.edit_timeline(timeline.id, rows=[])
        opened.add_timeline(NEW, kind="Range", rows=rows, default_row_height=None)
        opened.sync()
        written = json.loads(opened.bytes())["timelines"][NEW]["rows"]
        assert written == [{"id": rows[0]["id"], "name": "Row"}]

    def test_a_new_component_comes_with_nothing_of_a_removed_one(self):
        opened = Opened.read(UNKNOWN)
        timeline_id, component = first_component(opened.doc, "marker")
        opened.delete_component(timeline_id, component.id)
        opened.add_component(timeline_id, NEW, "MARKER", time=5.0, label="new")
        opened.sync()
        assert opened.doc.timelines[timeline_id].components[NEW].metadata == {}
        assert component.id in opened.removed


class TestAudioWave:
    def test_its_components_arent_stored(self):
        # TiLiA computes them when the media loads, which may be after the
        # state it compares with.
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "audiowave")
        opened.add_component(
            timeline.id, NEW, "AUDIOWAVE", start=0.0, end=1.0, amplitude=0.5
        )
        opened.sync()
        assert opened.bytes() == opened.bytes_read
        opened.delete_component(timeline.id, NEW)
        opened.sync()
        assert opened.bytes() == opened.bytes_read


class TestComponentForRules:
    def state_of_kind(self, kind):
        doc = tla.read(EVERY_KIND)
        timeline_id, component = first_component(doc, kind)
        state = tla_bridge.state_of(doc)
        return doc, component, state[timeline_id]["components"][component.id]

    @pytest.mark.parametrize(
        "name,kind",
        [
            ("HIERARCHY", "hierarchy"),
            ("MARKER", "marker"),
            ("RANGE", "range"),
            ("HARMONY", "harmony"),
            ("MODE", "mode"),
            ("BEAT", "beat"),
            ("PDF_MARKER", "pdf_marker"),
        ],
    )
    def test_kinds_and_attributes(self, name, kind):
        _, component, state = self.state_of_kind(kind)
        for_rules = tla_bridge.component_for_rules(component.id, name, state)
        assert isinstance(for_rules, tla.Component)
        assert for_rules.id == component.id
        assert for_rules.kind == kind
        assert "hash" not in for_rules.attrs and "kind" not in for_rules.attrs
        assert (
            for_rules.attrs.items()
            >= {
                key: value
                for key, value in component.attrs.items()
                if key in ("time", "start", "end", "label", "level", "page_number")
            }.items()
        )

    def test_a_kind_tilia_has_and_the_rules_dont(self):
        for_rules = tla_bridge.component_for_rules(
            NEW, "AUDIOWAVE", {"start": 0.0, "end": 1.0, "amplitude": 0.5}
        )
        assert isinstance(for_rules.kind, tla.UnknownKind)
        assert rules.check_timeline(1.0, [for_rules]) == {}

    def test_it_doesnt_share_the_states_values(self):
        _, component, state = self.state_of_kind("marker")
        for_rules = tla_bridge.component_for_rules(component.id, "MARKER", state)
        for_rules.attrs["label"] = "changed"
        assert state["label"] != "changed"

    def test_check_timeline_takes_a_whole_timeline(self):
        doc = tla.read(EVERY_KIND)
        states = tla_bridge.state_of(doc)
        for timeline in doc.timelines.values():
            state = states[timeline.id]
            components = [
                tla_bridge.component_for_rules(id, component["kind"], component)
                for id, component in state["components"].items()
            ]
            found = rules.check_timeline(
                doc.media_length,
                components,
                rows=state.get("rows"),
                page_count=10,
            )
            assert all(checked.outcome for checked in found.values()), timeline.name

    def test_a_broken_rule_is_found(self):
        marker = tla_bridge.component_for_rules(
            NEW,
            "MARKER",
            {
                "kind": "MARKER",
                "hash": "x",
                "time": 200.0,
                "comments": "",
                "label": "",
                "color": None,
            },
        )
        found = rules.check_timeline(100.0, [marker])
        assert not found[NEW].outcome


class TestState:
    def test_the_kinds_are_tilias(self):
        doc = tla.read(EVERY_KIND)
        state = tla_bridge.state_of(doc)
        for timeline_id, timeline in state.items():
            assert doc.timelines[timeline_id].kind == timeline["kind"].lower()
            for component_id, component in timeline["components"].items():
                stored = doc.timelines[timeline_id].components[component_id]
                assert stored.kind == component["kind"].lower()
        assert {timeline["kind"] for timeline in state.values()} == {
            "Slider",
            "Beat",
            "Hierarchy",
            "Marker",
            "Harmony",
            "Range",
            "Score",
            "Pdf",
            "AudioWave",
        }

    def test_every_timeline_kind_tilia_has_is_in_the_table(self):
        assert set(tla_bridge.TIMELINE_KINDS) == {
            cls.type_name() for cls in Timeline.subclasses()
        }

    def test_every_component_kind_tilia_stores_is_in_the_table(self):
        assert set(tla_bridge.COMPONENT_KINDS) == {
            kind.name for kind in ComponentKind if kind != ComponentKind.AUDIOWAVE
        }

    @pytest.mark.parametrize(
        "kind", [kind for kind in ComponentKind if kind != ComponentKind.AUDIOWAVE]
    )
    def test_a_components_attributes_are_tilias(self, kind):
        cls = get_component_class_by_kind(kind)
        document_kind = tla_bridge.COMPONENT_KINDS[kind.name]
        assert list(tla_bridge.COMPONENT_ATTRIBUTES[document_kind]) == cls.SERIALIZABLE

    @pytest.mark.parametrize(
        "name", ["Hierarchy", "Marker", "Beat", "Harmony", "Range", "Pdf", "Score"]
    )
    def test_a_timelines_attributes_are_tilias(self, name):
        cls = Timeline.get_class_by_name(name)
        doc = tla.read(EVERY_KIND)
        state = tla_bridge.state_of(doc)[first_of_kind(doc, name.lower()).id]
        assert set(cls.SERIALIZABLE) <= set(state)

    def test_a_sliders_attributes_are_tilias(self):
        cls = Timeline.get_class_by_name("Slider")
        doc = tla.read(EVERY_KIND)
        state = tla_bridge.state_of(doc)[first_of_kind(doc, "slider").id]
        assert set(cls.SERIALIZABLE) <= set(state)
        assert "name" not in state

    def test_new_attributes_of_every_timeline(self):
        doc = tla.read(EVERY_KIND)
        state = tla_bridge.state_of(doc)
        markers = first_of_kind(doc, "marker")
        assert state[markers.id]["measure_table"] == markers.attrs["measure_table"]
        assert state[markers.id]["fields"] == markers.metadata
        beats = first_of_kind(doc, "beat")
        assert state[beats.id]["measure_source"] == "tapped"

    def test_the_new_attributes_are_written_back(self):
        opened = Opened.read(EVERY_KIND)
        markers = first_of_kind(opened.doc, "marker")
        opened.edit_timeline(markers.id, measure_table=None)
        fields = dict(opened.timeline(markers.id)["fields"])
        fields["role"] = "other"
        fields["added"] = "value"
        del fields["vocabulary"]
        opened.edit_timeline(markers.id, fields=fields)
        beats = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(beats.id, measure_source="import")
        opened.sync()
        assert (
            "measure_table" not in json.loads(opened.bytes())["timelines"][markers.id]
        )
        assert markers.metadata == {"role": "other", "added": "value"}
        assert list(markers.metadata) == ["role", "added"]
        assert beats.attrs["measure_source"] == "import"

    @pytest.mark.parametrize(
        "kind,attr,value",
        [
            ("hierarchy", "height", 90),
            ("marker", "is_visible", False),
            ("harmony", "level_count", 3),
            ("harmony", "level_height", 40),
            ("harmony", "visible_level_count", 2),
            ("range", "default_row_height", 44),
            ("pdf", "path", "other.pdf"),
        ],
    )
    def test_a_timeline_attribute_is_written(self, kind, attr, value):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, kind)
        opened.edit_timeline(timeline.id, **{attr: value})
        opened.sync()
        assert timeline.attrs[attr] == value

    def test_a_time_signature_with_pairs_keeps_them_as_a_key_the_core_doesnt_know(self):
        # In TiLiA's SERIALIZABLE, not in the format's layout: the reader keeps it
        # in `extra`, and the writer refuses a key in both.
        staff, signature, tl = make_id(1), make_id(2), make_id(3)
        timeline = {
            "kind": "Score",
            "ordinal": 1,
            "height": 160,
            "components": {
                staff: {"kind": "STAFF", "line_count": 5, "index": 0},
                signature: {
                    "kind": "TIME_SIGNATURE",
                    "staff_index": 0,
                    "time": 0.0,
                    "numerator": None,
                    "denominator": None,
                    "pairs": [["2", 4], ["3", 8]],
                },
            },
        }
        opened = Opened.from_content(file_with({tl: timeline}))
        component = opened.doc.timelines[tl].components[signature]
        assert opened.component(tl, signature)["pairs"] == [["2", 4], ["3", 8]]
        opened.sync()
        assert opened.bytes() == opened.bytes_read
        opened.edit_component(tl, signature, pairs=[["3", 4]])
        opened.sync()
        assert component.extra["pairs"] == [["3", 4]]
        assert "pairs" not in component.attrs
        assert tla.loads(opened.bytes())

    def test_a_new_time_signature_without_pairs_has_no_key_for_them(self):
        tl = make_id(3)
        timeline = {"kind": "Score", "ordinal": 1, "height": 160, "components": {}}
        opened = Opened.from_content(file_with({tl: timeline}))
        opened.add_component(
            tl,
            NEW,
            "TIME_SIGNATURE",
            staff_index=0,
            time=0.0,
            numerator="3",
            denominator=4,
            pairs=None,
        )
        opened.sync()
        written = json.loads(opened.bytes())["timelines"][tl]["components"][NEW]
        assert "pairs" not in written
        assert written["numerator"] == "3"

    def test_a_lone_surrogate_in_a_label_gives_a_digest(self):
        content = file_with(
            {
                make_id(1): marker_timeline(
                    1,
                    **{
                        make_id(2): {
                            "kind": "MARKER",
                            "time": 1.0,
                            "label": "\ud83c",
                        }
                    },
                )
            }
        )
        doc = tla.loads(json.dumps(content).encode())
        state = tla_bridge.state_of(doc)
        assert state[make_id(1)]["components"][make_id(2)]["hash"]

    def test_a_components_digest_changes_with_its_value(self):
        doc = tla.read(EVERY_KIND)
        timeline_id, component = first_component(doc, "marker")
        before = tla_bridge.state_of(doc)[timeline_id]["components"][component.id]
        component.attrs["label"] = "changed"
        after = tla_bridge.state_of(doc)[timeline_id]["components"][component.id]
        assert before["hash"] != after["hash"]


class TestLiveTimelines:
    """The state is what TiLiA's objects give back, so nothing reads as an edit."""

    @pytest.fixture
    def live(self, tls):
        yield tls
        tls.clear()

    @pytest.mark.parametrize(
        "path",
        [EVERY_KIND, UNKNOWN, *OLD],
        ids=ids_of([EVERY_KIND, UNKNOWN, *OLD]),
    )
    def test_each_attribute_and_component_digest(self, live, tilia_state, path):
        doc = tla.read(path)
        state = tla_bridge.state_of(doc)
        tilia_state.duration = 10_000
        live.deserialize_timelines(state)
        given, _ = live.serialize_timelines()
        assert set(given) == set(state)
        for timeline_id, timeline in state.items():
            live_timeline = given[timeline_id]
            cls = Timeline.get_class_by_name(timeline["kind"])
            for attr in cls.SERIALIZABLE:
                assert live_timeline[attr] == timeline[attr], (timeline["kind"], attr)
            live_components = live_timeline["components"]
            if timeline["kind"] == "AudioWave":
                continue
            assert set(live_components) == set(timeline["components"])
            for component_id, component in timeline["components"].items():
                if component.get("numerator") is not None:
                    # TiLiA holds it as text. The same on both sides, so no edit,
                    # and the digest doesn't see the difference.
                    component = {**component, "numerator": str(component["numerator"])}
                assert live_components[component_id] == component, component["kind"]

    @pytest.mark.parametrize(
        "path",
        [EVERY_KIND, UNKNOWN, *OLD],
        ids=ids_of([EVERY_KIND, UNKNOWN, *OLD]),
    )
    def test_nothing_the_objects_fill_in_reads_as_an_edit(
        self, live, tilia_state, path
    ):
        doc = tla.read(path)
        before = tla.canonical_bytes(doc)
        tilia_state.duration = 10_000
        live.deserialize_timelines(tla_bridge.state_of(doc))
        given, digest = live.serialize_timelines()
        fields = {"media_metadata": {}, "media_path": "", "timelines_hash": digest}
        synced = {**fields, "timelines": tla_bridge.state_of(doc)}
        current = {**fields, "timelines": given}
        tla_bridge.apply_changes(doc, synced, current, removed={})
        assert tla.canonical_bytes(doc) == before
        tla_bridge.apply_changes(doc, current, copy.deepcopy(current), removed={})
        assert tla.canonical_bytes(doc) == before


class Live:
    """A document with TiLiA's real timelines built from it, and the state they give,
    as `App.get_app_state` gives it, with TiLiA's own digests."""

    def __init__(self, tls, tilia_state, doc):
        tilia_state.duration = 10_000
        self.tls, self.doc = tls, doc
        tls.deserialize_timelines(tla_bridge.state_of(doc))
        self.removed = {}
        self.notes = []
        self.bytes_read = tla.canonical_bytes(doc)
        self.synced = self.state()
        self.first = copy.deepcopy(self.synced)

    def state(self):
        given, digest = self.tls.serialize_timelines()
        return {
            "media_metadata": {},
            "media_path": "",
            "timelines": given,
            "timelines_hash": digest,
        }

    def sync(self, current=None):
        """Applies TiLiA's state, or `current`, as an undo to it would leave TiLiA."""
        current = copy.deepcopy(current) if current is not None else self.state()
        self.notes += tla_bridge.apply_changes(
            self.doc, self.synced, current, removed=self.removed
        )
        self.synced = copy.deepcopy(current)

    def timeline(self, timeline_id):
        return self.tls.get_timeline(timeline_id)

    def bytes(self):
        return tla.canonical_bytes(self.doc)

    def written(self, timeline_id):
        return json.loads(self.bytes())["timelines"][timeline_id]


@pytest.fixture
def live(tls, tilia_state):
    def make(doc):
        return Live(tls, tilia_state, doc)

    yield make
    tls.clear()


def loads(content):
    return tla.loads(json.dumps(content).encode())


def marked_measures():
    """15 beats in 3-beat measures, whose marks hold every key a mark can."""
    ids = [make_id(i) for i in range(1, 16)]
    marks = {
        0: {"label": "A", "source": "tapped", "metadata": {"tags": ["first"]}},
        3: {"number": 2, "cadenza": True, "next": [ids[9]]},
        6: {"label": "C", "force_display": True, "x_mark": "kept"},
        9: {"restart": True, "number": 1, "source": "import"},
        12: {"label": "E", "metadata": {"tags": ["last"]}, "x_mark": "last"},
    }
    beats = {}
    for place, beat_id in enumerate(ids):
        beats[beat_id] = beat(float(place), marks.get(place))
    timeline_id = make_id(99)
    doc = loads(file_with({timeline_id: beat_timeline(beats, beat_pattern="3")}))
    return timeline_id, ids, doc


def marks_by_measure(written):
    """The marks in time order, without the beats they are on."""
    beats = sorted(written["components"].values(), key=lambda b: b["time"])
    return [b["measure"] for b in beats if "measure" in b]


def without_the_lists(marks):
    """The marks without what TiLiA's lists set by position: the number, and whether
    it is always shown."""
    return [
        {
            key: value
            for key, value in mark.items()
            if key not in ("number", "force_display")
        }
        for mark in marks
    ]


def downbeats(written):
    beats = sorted(written["components"].items(), key=lambda item: item[1]["time"])
    return [beat_id for beat_id, b in beats if "measure" in b]


class TestMarksFollowTheirMeasures:
    """Until the beat timeline is on the marks, TiLiA keeps its measures by position,
    and moves later downbeats when a beat is added or deleted outside the last
    measure. Each mark follows its measure, and a `next` keeps naming the same
    measure (TimeLineAnnotator/project-management#523)."""

    def test_a_beat_added_in_the_second_measure(self, live):
        timeline_id, ids, doc = marked_measures()
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.create_component(ComponentKind.BEAT, 4.5)
        opened.sync()
        written = opened.written(timeline_id)
        after = marks_by_measure(written)
        assert after[:5] == [
            *before[:1],
            {**before[1], "next": [ids[8]]},
            *before[2:5],
        ]
        assert after[5:] == [{}]
        # The measures that moved start one beat earlier.
        assert downbeats(written) == [ids[0], ids[3], ids[5], ids[8], ids[11], ids[14]]
        assert tla.loads(opened.bytes())
        assert opened.notes == []

    def test_its_undo(self, live):
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        opened.timeline(timeline_id).create_component(ComponentKind.BEAT, 4.5)
        opened.sync()
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_its_undo_through_tilia(self, live):
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        opened.timeline(timeline_id).create_component(ComponentKind.BEAT, 4.5)
        opened.sync()
        opened.tls.restore_state(copy.deepcopy(opened.first["timelines"]))
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_beat_deleted_in_the_second_measure_and_its_undo(self, live):
        timeline_id, ids, doc = marked_measures()
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[4])])
        opened.sync()
        written = opened.written(timeline_id)
        assert marks_by_measure(written) == [
            before[0],
            {**before[1], "next": [ids[10]]},
            *before[2:],
        ]
        assert downbeats(written) == [ids[0], ids[3], ids[7], ids[10], ids[13]]
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_downbeat_deleted_and_its_undo(self, live):
        timeline_id, ids, doc = marked_measures()
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[6])])
        opened.sync()
        # Its measure stays, starting a beat later, so its mark goes there, and the
        # later marks follow theirs.
        written = opened.written(timeline_id)
        assert without_the_lists(marks_by_measure(written)) == without_the_lists(
            [before[0], {**before[1], "next": [ids[10]]}, *before[2:]]
        )
        assert downbeats(written) == [ids[0], ids[3], ids[7], ids[10], ids[13]]
        assert opened.notes == []
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_add_measure_zero_and_its_undo(self, live):
        # TiLiA adds a measure before the first: the other downbeats stay where they
        # were, at the next index, and keep their marks.
        timeline_id, ids, doc = marked_measures()
        for component in doc.timelines[timeline_id].components.values():
            component.attrs["time"] += 5
        doc.timelines[timeline_id].measures = tla.measure_table(
            doc.timelines[timeline_id]
        )
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        done, reason = opened.timeline(timeline_id).add_measure_zero(0.5)
        assert done, reason
        opened.sync()
        written = opened.written(timeline_id)
        marks = marks_by_measure(written)
        assert marks[0] == {"number": 0}
        assert without_the_lists(marks[1:]) == without_the_lists(before)
        assert downbeats(written)[1:] == [ids[0], ids[3], ids[6], ids[9], ids[12]]
        assert opened.notes == []
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_one_beat_measure_deleted_and_its_undo(self, live):
        # The other measures keep their downbeats and marks, restart included.
        ids = [make_id(i) for i in range(1, 7)]
        timeline_id = make_id(99)
        beats = {
            beat_id: beat(
                float(place),
                {"label": f"m{place + 1}", **({"restart": True} if place == 5 else {})},
            )
            for place, beat_id in enumerate(ids)
        }
        doc = loads(file_with({timeline_id: beat_timeline(beats)}))
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[1])])
        opened.sync()
        written = opened.written(timeline_id)["components"]
        for place in (0, 2, 3, 4, 5):
            assert written[ids[place]]["measure"]["label"] == f"m{place + 1}"
        assert written[ids[5]]["measure"]["restart"] is True
        assert len(opened.notes) == 1 and ids[1] in opened.notes[0]
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_set_beat_amount_that_takes_the_next_measure_and_its_undo(self, live):
        # The first measure takes the second's beats: the second is gone, and the
        # others keep their downbeats and marks.
        timeline_id, ids, doc = marked_measures()
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        opened.timeline(timeline_id).set_beat_amount_in_measure(0, 6)
        opened.sync()
        written = opened.written(timeline_id)
        assert downbeats(written)[:4] == [ids[0], ids[6], ids[9], ids[12]]
        assert without_the_lists(marks_by_measure(written)[1:4]) == without_the_lists(
            before[2:]
        )
        assert len(opened.notes) == 1
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_set_beat_amount_and_its_undo(self, live):
        timeline_id, ids, doc = marked_measures()
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
        )
        opened = live(doc)
        opened.timeline(timeline_id).set_beat_amount_in_measure(1, 2)
        opened.sync()
        written = opened.written(timeline_id)
        assert marks_by_measure(written)[:5] == [
            before[0],
            {**before[1], "next": [ids[8]]},
            *before[2:],
        ]
        assert downbeats(written)[:5] == [ids[0], ids[3], ids[5], ids[8], ids[11]]
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_set_beat_amount_that_takes_the_last_measure_and_its_undo(self, live):
        # Its beats join the measure before: the measure's mark waits in `removed`.
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        opened.timeline(timeline_id).set_beat_amount_in_measure(3, 6)
        opened.sync()
        assert "measure" not in opened.written(timeline_id)["components"][ids[12]]
        assert len(opened.notes) == 1
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_measure_that_is_gone_leaves_a_note_and_comes_back(self, live):
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(id) for id in ids[12:]])
        opened.sync()
        assert len(marks_by_measure(opened.written(timeline_id))) == 4
        assert len(opened.notes) == 1 and "left the file" in opened.notes[0]
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_next_naming_a_measure_that_is_gone_goes_with_a_note(self, live):
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(id) for id in ids[9:]])
        opened.sync()
        assert (
            "next" not in opened.written(timeline_id)["components"][ids[3]]["measure"]
        )
        assert any("followed" in note for note in opened.notes)
        assert tla.loads(opened.bytes())

    def test_a_next_naming_a_beat_deleted_since_goes(self, live):
        # a | b (next: d) | c | d e: a mark's next can't name a beat that is gone.
        a, b, c, d, e = (make_id(i) for i in (1, 2, 3, 4, 5))
        timeline_id = make_id(9)
        beats = {
            a: beat(0.0, {}),
            b: beat(1.0, {"next": [d]}),
            c: beat(2.0, {}),
            d: beat(3.0, {}),
            e: beat(4.0),
        }
        opened = live(loads(file_with({timeline_id: beat_timeline(beats)})))
        timeline = opened.timeline(timeline_id)
        timeline.set_beat_amount_in_measure(0, 2)
        opened.sync()
        timeline.delete_components([timeline.get_component(d)])
        opened.sync()
        timeline.set_beat_amount_in_measure(0, 1)
        opened.sync()
        assert tla.loads(opened.bytes())

    def test_a_next_naming_a_downbeat_without_a_time_stays(self):
        a, b, untimed, c, tl = (make_id(i) for i in (1, 2, 3, 4, 9))
        beats = {
            a: beat(0.0, {}),
            b: beat(1.0, {"next": [untimed]}),
            untimed: beat(None, {}),
            c: beat(2.0, {}),
        }
        opened = Opened.from_content(file_with({tl: beat_timeline(beats)}))
        opened.edit_timeline(tl, measure_numbers=[1, 7, 8])
        opened.sync()
        mark = opened.doc.timelines[tl].components[b].attrs["measure"]
        assert mark["next"] == [untimed]

    def test_a_number_the_bridge_wrote_goes_with_its_undo(self, live):
        timeline_id, ids, doc = marked_measures()
        opened = live(doc)
        opened.timeline(timeline_id).set_measure_number(2, 40)
        opened.sync()
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_number_written_after_the_edited_one_goes_with_its_undo(self):
        # set_measure_number(1, 40) with measure 2 forced: b is 40, c stays 3.
        a, b, c, tl = make_id(1), make_id(2), make_id(3), make_id(9)
        beats = {a: beat(0.0, {}), b: beat(1.0, {}), c: beat(2.0, {})}
        opened = Opened.from_content(file_with({tl: beat_timeline(beats)}))
        first = copy.deepcopy(opened.current)
        opened.edit_timeline(tl, measure_numbers=[1, 40, 3])
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read


def labelled(counts, pattern=None, extra=None, closing=False):
    """Beats in measures of these counts, each mark labelled with its measure, from m1,
    with `extra` keys by measure; a closing tap after them if asked."""
    timeline_id = make_id(99)
    beats, place, measure = {}, 0, 0
    for count in counts:
        measure += 1
        for in_measure in range(count):
            mark = None
            if in_measure == 0:
                mark = {"label": f"m{measure}", **(extra or {}).get(measure, {})}
            beats[make_id(place + 1)] = beat(float(place), mark)
            place += 1
    if closing:
        beats[make_id(place + 1)] = beat(float(place), closing=True)
    keys = {"beat_pattern": pattern} if pattern else {}
    doc = loads(file_with({timeline_id: beat_timeline(beats, **keys)}))
    return timeline_id, [make_id(i + 1) for i in range(place)], doc


def labels_by_beat(opened, timeline_id):
    components = opened.written(timeline_id)["components"]
    return {
        beat_id: beat["measure"].get("label")
        for beat_id, beat in components.items()
        if "measure" in beat
    }


def labels_in_order(opened, timeline_id):
    return [mark.get("label") for mark in marks_by_measure(opened.written(timeline_id))]


class TestMarksInOneAction:
    """What one action does to several measures, and its undo, which must give the
    bytes back. A beat that stays a downbeat keeps its own mark."""

    def test_set_beat_amount_on_two_measures(self, live):
        timeline_id, ids, doc = labelled([2] * 6, pattern="2")
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.set_beat_amount_in_measure(3, 4)
        timeline.set_beat_amount_in_measure(1, 4)
        opened.sync()
        by_beat = labels_by_beat(opened, timeline_id)
        for beat_id, label in by_beat.items():
            if label is not None:
                assert label == f"m{ids.index(beat_id) // 2 + 1}"
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_two_one_beat_downbeats_deleted(self, live):
        timeline_id, ids, doc = labelled([1] * 6, pattern="1")
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components(
            [timeline.get_component(ids[1]), timeline.get_component(ids[4])]
        )
        opened.sync()
        assert labels_in_order(opened, timeline_id) == ["m1", "m3", "m4", "m6"]
        assert len(opened.notes) == 2
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_one_beat_downbeat_and_a_plain_beat_deleted(self, live):
        timeline_id, ids, doc = labelled([1, 3, 1, 3, 1], pattern="3")
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components(
            [timeline.get_component(ids[2]), timeline.get_component(ids[4])]
        )
        opened.sync()
        # TiLiA takes both beats from the last measures, so it shows four measures,
        # the later two starting on other beats: m3 and m4 by their places, and the
        # last measure, m5, is gone, with a note.
        assert labels_in_order(opened, timeline_id) == ["m1", "m2", "m3", "m4"]
        assert len(opened.notes) == 1 and "m5" in opened.notes[0]
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_add_measure_zero_then_a_deletion(self, live):
        timeline_id, ids, doc = labelled([3] * 5, pattern="3")
        for component in doc.timelines[timeline_id].components.values():
            component.attrs["time"] += 5
        doc.timelines[timeline_id].measures = tla.measure_table(
            doc.timelines[timeline_id]
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.add_measure_zero(0.5)
        opened.sync()
        zero = copy.deepcopy(opened.synced)
        zero_bytes = opened.bytes()
        timeline.delete_components([timeline.get_component(ids[4])])
        opened.sync()
        assert labels_in_order(opened, timeline_id) == [
            None,
            "m1",
            "m2",
            "m3",
            "m4",
            "m5",
        ]
        opened.sync(zero)
        assert opened.bytes() == zero_bytes
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    @pytest.mark.parametrize("amount", [2, 6], ids=["giving", "taking"])
    def test_set_beat_amount_giving_or_taking(self, live, amount):
        timeline_id, ids, doc = labelled([3] * 5, pattern="3")
        opened = live(doc)
        opened.timeline(timeline_id).set_beat_amount_in_measure(1, amount)
        opened.sync()
        assert tla.loads(opened.bytes())
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_beat_added_where_the_shift_lands_on_old_downbeats(self, live):
        timeline_id, ids, doc = labelled([2, 1, 1, 1, 1], pattern="1")
        opened = live(doc)
        opened.timeline(timeline_id).create_component(ComponentKind.BEAT, 0.5)
        opened.sync()
        by_beat = labels_by_beat(opened, timeline_id)
        for place in (2, 3, 4, 5):
            assert by_beat[ids[place]] == f"m{place}"
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_beat_added_among_one_beat_measures_and_its_undo(self, live):
        # The new beat starts a new measure, and the others keep their marks.
        extra = {3: {"restart": True, "number": 1, "source": "import"}}
        timeline_id, ids, doc = labelled([1] * 5, pattern="1", extra=extra)
        opened = live(doc)
        opened.timeline(timeline_id).create_component(ComponentKind.BEAT, 1.5)
        opened.sync()
        assert labels_in_order(opened, timeline_id) == [
            "m1",
            "m2",
            None,
            "m3",
            "m4",
            "m5",
        ]
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_with_a_restart_and_a_closing_tap(self, live):
        extra = {4: {"restart": True, "number": 1}}
        timeline_id, ids, doc = labelled(
            [3, 3, 1, 3, 3], pattern="3", extra=extra, closing=True
        )
        tap = make_id(len(ids) + 1)
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[6])])
        opened.sync()
        written = opened.written(timeline_id)["components"]
        assert written[ids[7]]["measure"]["restart"] is True
        assert written[tap] == {"kind": "BEAT", "time": 13.0, "closing": True}
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_long_measures_deleted_downbeat_and_its_undo(self, live):
        # Its measure stays, so its mark goes to the next beat.
        extra = {3: {"restart": True, "number": 1, "source": "import"}}
        timeline_id, ids, doc = labelled([3] * 4, pattern="3", extra=extra)
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[6])])
        opened.sync()
        mark = opened.written(timeline_id)["components"][ids[7]]["measure"]
        assert mark["label"] == "m3" and mark["restart"] is True
        assert mark["source"] == "import"
        assert opened.notes == []
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_number_written_on_a_deleted_downbeat_and_two_undos(self, live):
        # The deleted downbeat's measure stays, so a copy of its mark, with the number
        # written on it, goes to the next beat; back, the beat's own mark is the
        # one whose number goes with the second undo.
        timeline_id, ids, doc = labelled([3] * 4, pattern="3")
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.set_measure_number(2, 40)
        opened.sync()
        numbered = copy.deepcopy(opened.synced)
        timeline.delete_components([timeline.get_component(ids[6])])
        opened.sync()
        opened.sync(numbered)
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_number_written_on_a_measure_that_goes_and_two_undos(self, live):
        # What `removed` keeps of the mark, the number written on it, stays with it.
        timeline_id, ids, doc = labelled([3] * 5, pattern="3")
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.set_measure_number(4, 40)
        opened.sync()
        numbered = copy.deepcopy(opened.synced)
        timeline.set_beat_amount_in_measure(3, 6)
        opened.sync()
        opened.sync(numbered)
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_the_measure_a_restart_goes_to_states_its_number(self, live):
        # As the core does: so the number holds whatever comes before it.
        timeline_id, ids, doc = labelled(
            [1] * 5, pattern="1", extra={3: {"restart": True}}
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[2])])
        opened.sync()
        mark = opened.written(timeline_id)["components"][ids[3]]["measure"]
        assert mark["restart"] is True
        assert mark["number"] == 3

    def test_a_restart_on_a_measure_that_is_gone_goes_to_the_next(self, live):
        # As the core does when a one-beat measure's downbeat is deleted: the next
        # measure states the number it read, unless TiLiA's lists say another.
        extra = {2: {"restart": True, "number": 1}}
        timeline_id, ids, doc = labelled([1] * 5, pattern="1", extra=extra)
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[1])])
        opened.sync()
        mark = opened.written(timeline_id)["components"][ids[2]]["measure"]
        assert mark["label"] == "m3" and mark["restart"] is True
        assert "number" in mark
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_next_naming_a_measure_that_is_gone_names_the_next(self, live):
        timeline_id, ids, doc = labelled(
            [1] * 4, pattern="1", extra={1: {"next": [make_id(2)]}}
        )
        opened = live(doc)
        timeline = opened.timeline(timeline_id)
        timeline.delete_components([timeline.get_component(ids[1])])
        opened.sync()
        mark = opened.written(timeline_id)["components"][ids[0]]["measure"]
        assert mark["next"] == [ids[2]]
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read


class TestNextThroughChainsOfChanges:
    """A `next` that a change made name another measure, because the one it named went,
    comes back with each undo, one change at a time or several at once, and goes again
    with each redo. a, b, c, d and e are one-beat measures; a is followed by c, then d,
    unless a test says otherwise."""

    A, B, C, D, E, TL = (make_id(i) for i in (1, 2, 3, 4, 5, 9))

    def opened(self, following):
        beats = {
            self.A: beat(0.0, {"next": following}),
            self.B: beat(1.0, {"label": "b"}),
            self.C: beat(2.0, {"label": "c"}),
            self.D: beat(3.0, {"label": "d"}),
            self.E: beat(4.0, {"label": "e"}),
        }
        return Opened.from_content(file_with({self.TL: beat_timeline(beats)}))

    def through(self, following, counts, opened=None):
        """The states as TiLiA gives these beat counts of measures in turn, numbered
        from 1 unless the counts come with their numbers."""
        opened = opened or self.opened(following)
        states = [copy.deepcopy(opened.current)]
        written = [opened.bytes_read]
        for each in counts:
            each, numbers = each if isinstance(each, tuple) else (each, None)
            opened.edit_timeline(
                self.TL,
                beats_in_measure=list(each),
                measure_numbers=numbers or list(range(1, len(each) + 1)),
            )
            opened.sync()
            states.append(copy.deepcopy(opened.current))
            written.append(opened.bytes())
        return opened, states, written

    def states(self):
        opened = self.opened([self.C, self.D])
        states = [copy.deepcopy(opened.current)]
        written = [opened.bytes_read]
        for gone, count in ((self.C, 4), (self.D, 3)):
            opened.delete_component(self.TL, gone)
            opened.edit_timeline(
                self.TL,
                beats_in_measure=[1] * count,
                measure_numbers=list(range(1, count + 1)),
            )
            opened.sync()
            states.append(copy.deepcopy(opened.current))
            written.append(opened.bytes())
        return opened, states, written

    def go(self, opened, state):
        opened.current = copy.deepcopy(state)
        opened.sync()

    def following(self, opened):
        return opened.doc.timelines[self.TL].components[self.A].attrs["measure"]["next"]

    def test_each_change_names_the_next_measure(self):
        opened, states, written = self.states()
        assert self.following(opened) == [self.E, self.E]

    def test_undone_one_at_a_time(self):
        opened, states, written = self.states()
        self.go(opened, states[1])
        assert opened.bytes() == written[1]
        self.go(opened, states[0])
        assert opened.bytes() == written[0]

    def test_undone_at_once(self):
        opened, states, written = self.states()
        self.go(opened, states[0])
        assert opened.bytes() == written[0]

    def test_redone(self):
        opened, states, written = self.states()
        for back in (1, 0):
            self.go(opened, states[back])
        for again in (1, 2):
            self.go(opened, states[again])
            assert opened.bytes() == written[again]

    def test_undone_redone_and_undone_further(self):
        # The second change's turn back lies above the first's, as its opposite.
        opened, states, written = self.states()
        for state in (states[1], states[2], states[1], states[0]):
            self.go(opened, state)
        assert opened.bytes() == written[0]

    def test_undone_after_a_change_that_brought_its_measure_back(self):
        # a is followed by d. d's measure goes into c's, so a is followed by e. Then
        # c's goes into b's and e's into d's, which starts again: a is followed by d
        # again. Undoing that matches d's measure with c's, by place, but a is followed
        # by e, as it was.
        opened, states, written = self.through([self.D], ([1, 1, 2, 1], [1, 2, 2]))
        assert self.following(opened) == [self.D]
        self.go(opened, states[1])
        assert opened.bytes() == written[1]
        self.go(opened, states[0])
        assert opened.bytes() == written[0]

    def test_a_list_comes_back_only_while_its_measures_start(self):
        # c's measure goes into b's, so a is followed by d, d. Then c starts a measure
        # again and d's goes into it: a's list as it was, c, d, would name a beat that
        # starts no measure, so a stays followed by the measure d's is now, by place.
        opened, states, written = self.through(
            [self.C, self.D], ([1, 2, 1, 1], [1, 1, 2, 1])
        )
        assert self.following(opened) == [self.C, self.C]
        tla.loads(opened.bytes())
        for back in (1, 0):
            self.go(opened, states[back])
            assert opened.bytes() == written[back]

    def test_undone_after_its_mark_moved_to_another_beat(self):
        # a | b c | d | e | f, with d followed by f, become a | b | c d | e f: d's
        # measure, in its place, starts at c, so its mark moves there, and f's goes
        # with none after it, so the mark loses its `next`. The undo moves the mark
        # back to d, followed by f.
        F = make_id(6)
        beats = {
            self.A: beat(0.0, {"label": "a"}),
            self.B: beat(1.0, {"label": "b"}),
            self.C: beat(2.0),
            self.D: beat(3.0, {"label": "d", "next": [F]}),
            self.E: beat(4.0, {"label": "e"}),
            F: beat(5.0, {"label": "f"}),
        }
        opened = Opened.from_content(file_with({self.TL: beat_timeline(beats)}))
        first = copy.deepcopy(opened.current)
        opened.edit_timeline(
            self.TL, beats_in_measure=[1, 1, 2, 2], measure_numbers=[1, 2, 3, 4]
        )
        opened.sync()
        moved = opened.doc.timelines[self.TL].components[self.C].attrs["measure"]
        assert moved["label"] == "d" and "next" not in moved
        self.go(opened, first)
        assert opened.bytes() == opened.bytes_read

    def test_a_list_changed_since_stays(self):
        # a is followed by c. c's measure goes into b's, so a is followed by d, then
        # d's goes into b's too, so by e. When c starts a measure again, the list is
        # no longer as the first change left it, so a stays followed by e. Each undo
        # gives the bytes back.
        opened, states, written = self.through(
            [self.C], ([1, 2, 1, 1], [1, 3, 1], [1, 1, 2, 1])
        )
        assert self.following(opened) == [self.E]
        for back in (2, 1, 0):
            self.go(opened, states[back])
            assert opened.bytes() == written[back]

    def test_a_turn_goes_back_only_with_the_change_that_starts_its_names(self):
        # a | b | c d | e f, with a followed by c. c's measure goes into b's, so a is
        # followed by e; e's measure, in its place, starts at d, so a is followed by
        # d. c and e start measures again, and a stays followed by d, as the list
        # changed since. Then d's measure goes: a is followed by e, the list the first
        # change left. An edit of a measure number doesn't start c again, since it
        # already did, so a stays followed by e, and each undo gives the bytes back.
        F = make_id(6)
        beats = {
            self.A: beat(0.0, {"label": "a", "next": [self.C]}),
            self.B: beat(1.0, {"label": "b"}),
            self.C: beat(2.0, {"label": "c"}),
            self.D: beat(3.0),
            self.E: beat(4.0, {"label": "e"}),
            F: beat(5.0),
        }
        opened = Opened.from_content(file_with({self.TL: beat_timeline(beats)}))
        counts = (
            [1, 3, 2],
            [1, 2, 3],
            [1, 1, 1, 1, 2],
            [1, 1, 2, 2],
            ([1, 1, 2, 2], [1, 2, 3, 7]),
        )
        followed = []
        states = [copy.deepcopy(opened.current)]
        written = [opened.bytes_read]
        for each in counts:
            _, more, also = self.through(None, [each], opened)
            states.append(more[-1])
            written.append(also[-1])
            followed.append(self.following(opened))
        E, D = self.E, self.D
        assert followed == [[E], [D], [D], [E], [E]]
        for back in range(len(counts) - 1, -1, -1):
            self.go(opened, states[back])
            assert opened.bytes() == written[back]


class TestSameEditThroughTiLiA:
    """SC-002's beat edits, made by TiLiA's own timelines, against the same edit
    through `attrs`, with what TiLiA's lists also change."""

    BEAT_FILES = [EVERY_KIND, UNKNOWN, *OLD]

    @staticmethod
    def first_beats(doc):
        beats = [tl for tl in doc.timelines.values() if tl.kind == "beat"]
        if not beats:
            pytest.skip("no beat timeline in this file")
        return min(beats, key=lambda tl: tl.ordinal)

    @pytest.mark.parametrize("path", BEAT_FILES, ids=ids_of(BEAT_FILES))
    def test_a_measure_number(self, live, path):
        # TiLiA's set_measure_number also always shows the number it sets.
        doc, second = tla.read(path), tla.read(path)
        beats = self.first_beats(doc)
        last = beats.measures.rows[-1].id
        opened = live(doc)
        timeline = opened.timeline(beats.id)
        timeline.set_measure_number(timeline.measure_count - 1, 2000)
        opened.sync()
        mark = second.timelines[beats.id].components[last].attrs["measure"]
        mark["number"] = 2000
        mark["force_display"] = True
        assert opened.bytes() == tla.canonical_bytes(second)

    @pytest.mark.parametrize("path", BEAT_FILES, ids=ids_of(BEAT_FILES))
    def test_adding_a_beat_at_the_end(self, live, path):
        # A beat after a full last measure starts a measure, with an empty mark.
        doc, second = tla.read(path), tla.read(path)
        beats = self.first_beats(doc)
        opened = live(doc)
        timeline = opened.timeline(beats.id)
        measures = timeline.measure_count
        time = max(b.time for b in timeline.components) + 1
        new, _ = timeline.create_component(ComponentKind.BEAT, time)
        opened.sync()
        attrs = {"time": time}
        if timeline.measure_count > measures:
            attrs["measure"] = {}
        second.timelines[beats.id].components[new.id] = tla.Component(
            id=new.id, kind="beat", attrs=attrs
        )
        assert opened.bytes() == tla.canonical_bytes(second)

    @pytest.mark.parametrize("path", BEAT_FILES, ids=ids_of(BEAT_FILES))
    def test_removing_a_beat_that_starts_no_measure(self, live, path):
        # TiLiA takes the beat from the last measure, so the later downbeats move,
        # and each mark follows its measure
        # (TimeLineAnnotator/project-management#523).
        doc = tla.read(path)
        beats = self.first_beats(doc)
        row = next((r for r in beats.measures.rows[:-1] if len(r.beats) > 1), None)
        if row is None:
            pytest.skip("no measure but the last has more than one beat")
        before = marks_by_measure(
            json.loads(tla.canonical_bytes(doc))["timelines"][beats.id]
        )
        opened = live(doc)
        timeline = opened.timeline(beats.id)
        timeline.delete_components([timeline.get_component(row.beats[1])])
        opened.sync()
        # A beat that stays a downbeat keeps its own mark, so a mark between two such
        # can be left without a measure: it goes, with a note.
        written = opened.written(beats.id)
        after = without_the_lists(marks_by_measure(written))
        kept = iter(without_the_lists(before))
        assert all(mark == {} or mark in kept for mark in after)
        missing = [m for m in without_the_lists(before) if m and m not in after]
        assert len(opened.notes) == len(missing)
        live_downbeats = [b.id for b in timeline.components if b.is_first_in_measure]
        assert downbeats(written) == live_downbeats
        assert tla.loads(opened.bytes())


class TestFilledIn:
    """What TiLiA fills in for an empty timeline is stored the first time it is edited
    or something refers to it (TimeLineAnnotator/project-management#524)."""

    def test_an_empty_hierarchy_timeline_saves_unchanged(self, live):
        tl = make_id(1)
        doc = loads(
            file_with(
                {
                    tl: {
                        "kind": "Hierarchy",
                        "ordinal": 1,
                        "height": 60,
                        "components": {},
                    }
                }
            )
        )
        opened = live(doc)
        assert len(opened.timeline(tl)) == 1
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_its_unit_is_stored_once_edited(self, live):
        tl = make_id(1)
        doc = loads(
            file_with(
                {
                    tl: {
                        "kind": "Hierarchy",
                        "ordinal": 1,
                        "height": 60,
                        "components": {},
                    }
                }
            )
        )
        opened = live(doc)
        timeline = opened.timeline(tl)
        unit = next(iter(timeline.components))
        timeline.set_component_data(unit.id, "label", "Exposition")
        opened.sync()
        written = opened.written(tl)["components"]
        assert written[unit.id]["label"] == "Exposition"
        assert written[unit.id]["level"] == 1
        assert tla.loads(opened.bytes())

    def test_a_range_timeline_without_rows_saves_unchanged(self, live):
        tl = make_id(1)
        doc = loads(
            file_with(
                {
                    tl: {
                        "kind": "Range",
                        "ordinal": 1,
                        "height": 40,
                        "rows": [],
                        "components": {},
                    }
                }
            )
        )
        opened = live(doc)
        assert len(opened.timeline(tl).rows) == 1
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_its_row_is_stored_once_a_range_names_it(self, live):
        tl = make_id(1)
        doc = loads(
            file_with(
                {
                    tl: {
                        "kind": "Range",
                        "ordinal": 1,
                        "height": 40,
                        "rows": [],
                        "components": {},
                    }
                }
            )
        )
        opened = live(doc)
        timeline = opened.timeline(tl)
        row = timeline.rows[0]
        made, reason = timeline.create_component(
            ComponentKind.RANGE, start=1.0, end=2.0, row_id=row.id
        )
        assert made, reason
        opened.sync()
        written = opened.written(tl)
        assert [r["id"] for r in written["rows"]] == [row.id]
        assert written["components"][made.id]["row_id"] == row.id
        assert tla.loads(opened.bytes())

    def test_a_filled_in_row_isnt_stored_for_a_range_on_a_stored_row(self):
        tl = make_id(1)
        timeline = {
            "kind": "Range",
            "ordinal": 1,
            "height": 40,
            "rows": [{"id": "aZ3k9P", "name": "Row"}],
            "components": {},
        }
        opened = Opened.from_content(file_with({tl: timeline}))
        for state in (opened.synced, opened.current):
            state["timelines"][tl]["rows"].append(
                {"id": "filled", "name": "Filled", "color": None, "height": None}
            )
        opened.add_component(tl, NEW, "RANGE", start=1.0, end=2.0, row_id="aZ3k9P")
        opened.sync()
        assert [r["id"] for r in opened.doc.timelines[tl].attrs["rows"]] == ["aZ3k9P"]


class TestComesBackAsTiLiAHeldIt:
    """A timeline or component back from `removed` is compared with the state it left
    with, as TiLiA held it, with TiLiA's digest, not with the document."""

    def test_a_pdf_path_found_elsewhere(self):
        tl = make_id(1)
        content = file_with(
            {
                tl: {
                    "kind": "Pdf",
                    "ordinal": 1,
                    "height": 200,
                    "path": "score.pdf",
                    "components": {},
                }
            }
        )
        opened = Opened.from_content(content)
        found = "C:/Users/someone/found/score.pdf"
        for state in (opened.synced, opened.current):
            state["timelines"][tl]["path"] = found
            state["timelines"][tl]["hash"] = "TiLiA's digest"
        opened.sync()
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(tl)
        opened.sync()
        opened.current = before
        opened.sync()
        assert opened.doc.timelines[tl].attrs["path"] == "score.pdf"
        assert opened.bytes() == opened.bytes_read

    def test_an_audiowave_timeline_tilia_hides(self, live):
        tl = make_id(1)
        doc = loads(
            file_with(
                {
                    tl: {
                        "kind": "AudioWave",
                        "ordinal": 1,
                        "height": 40,
                        "components": {},
                    }
                }
            )
        )
        opened = live(doc)
        assert opened.synced["timelines"][tl]["is_visible"] is False
        opened.tls.delete_timeline(opened.timeline(tl))
        opened.sync()
        opened.sync(opened.first)
        assert opened.bytes() == opened.bytes_read

    def test_a_component_with_a_value_tilia_fills_in(self):
        opened = Opened.read(EVERY_KIND)
        timeline_id, component = first_component(opened.doc, "marker")
        for state in (opened.synced, opened.current):
            marker = state["timelines"][timeline_id]["components"][component.id]
            marker["color"] = "#filled"
            marker["hash"] = "TiLiA's digest"
        before = copy.deepcopy(opened.current)
        opened.delete_component(timeline_id, component.id)
        opened.sync()
        opened.current = before
        opened.sync()
        assert opened.bytes() == opened.bytes_read


class TestOrdinalsAfterUndo:
    def test_a_duplicate_in_the_middle_and_its_undo(self):
        a, b, c = make_id(1), make_id(2), make_id(3)
        opened = Opened.from_content(
            file_with(
                {a: marker_timeline(1), b: marker_timeline(2), c: marker_timeline(3)}
            )
        )
        first = copy.deepcopy(opened.current)
        edit(opened.timeline(b), ordinal=3)
        edit(opened.timeline(c), ordinal=4)
        opened.add_timeline(NEW, ordinal=2)
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_no_two_timelines_get_one_ordinal(self):
        # Delete the last, duplicate the first, then undo both: the one deleted comes
        # back with its ordinal, which no other may have taken.
        a, b, y = make_id(1), make_id(2), make_id(3)
        opened = Opened.from_content(
            file_with(
                {a: marker_timeline(1), b: marker_timeline(2), y: marker_timeline(3)}
            )
        )
        first = copy.deepcopy(opened.current)
        opened.delete_timeline(y)
        opened.sync()
        edit(opened.timeline(b), ordinal=3)
        opened.add_timeline(NEW, ordinal=2)
        opened.sync()
        ordinals = [tl.ordinal for tl in opened.doc.timelines.values()]
        assert len(set(ordinals)) == len(ordinals)
        assert opened.doc.timelines[b].ordinal != 3
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_the_free_ordinal_is_above_those_of_removed_timelines(self):
        a, y = make_id(1), make_id(2)
        doc = loads(file_with({a: marker_timeline(1)}))
        removed = {y: tla.Timeline(id=y, kind="marker", ordinal=7)}
        assert tla_bridge.stored_ordinals(doc, [a, NEW], removed=removed) == {
            a: 1,
            NEW: 8,
        }


class TestScoresShared:
    """Two timelines can name one score, as a duplicate does (FR-023)."""

    @staticmethod
    def shared(format):
        score, a, b = make_id(1), make_id(2), make_id(3)

        def timeline(ordinal):
            return {
                "kind": "Score",
                "ordinal": ordinal,
                "height": 40,
                "components": {},
                "score": score,
            }

        stored = {"id": score, "format": format, "content": ["<x/>"]}
        if format == "mei":
            stored["source"] = {"file": "a.mei"}
        if format == "svg-osmd-legacy":
            stored["beat_x"] = [[1.0, 10.0]]
        opened = Opened.from_content(
            file_with({a: timeline(1), b: timeline(2)}, scores=[stored])
        )
        return opened, a, b, score

    @pytest.mark.parametrize("format", ["mei", "svg-osmd-legacy"])
    def test_an_import_on_one_leaves_the_others_score(self, format):
        opened, a, b, score = self.shared(format)
        before = json.loads(opened.bytes_read)["scores"][0]
        opened.edit_timeline(a, svg_data="<svg>new</svg>", viewer_beat_x={5.0: 50.0})
        opened.sync()
        written = json.loads(opened.bytes())
        assert written["timelines"][b]["score"] == score
        assert next(s for s in written["scores"] if s["id"] == score) == before
        assert written["timelines"][a]["score"] != score
        assert tla.loads(opened.bytes())

    @pytest.mark.parametrize("format", ["mei", "svg-osmd-legacy"])
    def test_and_its_undo(self, format):
        opened, a, b, score = self.shared(format)
        first = copy.deepcopy(opened.current)
        opened.edit_timeline(a, svg_data="<svg>new</svg>", viewer_beat_x={5.0: 50.0})
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_new_positions_on_one_leave_the_others(self):
        opened, a, b, score = self.shared("svg-osmd-legacy")
        opened.edit_timeline(a, viewer_beat_x={1.0: 99.0})
        opened.sync()
        written = json.loads(opened.bytes())
        shared = next(s for s in written["scores"] if s["id"] == score)
        assert shared["beat_x"] == [[1.0, 10.0]]
        own = next(
            s for s in written["scores"] if s["id"] == written["timelines"][a]["score"]
        )
        assert own["beat_x"] == [[1.0, 99.0]]

    def test_clearing_two_with_one_drawing_and_undoing_gives_each_its_own(self):
        # Two scores with the same drawing, each its timeline's.
        one, two, a, b = make_id(1), make_id(2), make_id(3), make_id(4)

        def timeline(ordinal, score):
            return {
                "kind": "Score",
                "ordinal": ordinal,
                "height": 40,
                "components": {},
                "score": score,
            }

        scores = [
            {
                "id": id,
                "format": "svg-osmd-legacy",
                "content": ["<x/>"],
                "beat_x": [[1.0, x]],
            }
            for id, x in ((one, 10.0), (two, 20.0))
        ]
        opened = Opened.from_content(
            file_with({a: timeline(1, one), b: timeline(2, two)}, scores=scores)
        )
        first = copy.deepcopy(opened.current)
        opened.edit_timeline(b, svg_data="")
        opened.sync()
        opened.edit_timeline(a, svg_data="")
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read

    def test_a_timeline_of_an_unknown_kind_keeps_the_score_it_names(self):
        score, a, lyrics = make_id(1), make_id(2), make_id(3)
        stored = {
            "id": score,
            "format": "mei",
            "content": ["<mei/>"],
            "source": {"file": "a.mei"},
        }
        timelines = {
            a: {
                "kind": "Score",
                "ordinal": 1,
                "height": 40,
                "components": {},
                "score": score,
            },
            lyrics: {"kind": "Lyrics", "ordinal": 2, "components": {}, "score": score},
        }
        opened = Opened.from_content(file_with(timelines, scores=[stored]))
        opened.delete_timeline(a)
        opened.sync()
        assert score in opened.doc.scores
        assert tla.loads(opened.bytes())

    @pytest.mark.parametrize(
        "beat_x",
        [
            [],
            [[1, 10]],
            [[2.0, 20.0], [1.0, 10.0]],
            [[1.0, 10.0], [3.0], []],
            [[1.0, 10.0, 99]],
        ],
        ids=repr,
    )
    def test_an_import_over_a_legacy_score_and_its_undo(self, beat_x):
        score, tl = make_id(1), make_id(2)
        timeline = {
            "kind": "Score",
            "ordinal": 1,
            "height": 40,
            "components": {},
            "score": score,
        }
        stored = {
            "id": score,
            "format": "svg-osmd-legacy",
            "content": ["<svg/>"],
            "beat_x": beat_x,
        }
        opened = Opened.from_content(file_with({tl: timeline}, scores=[stored]))
        first = copy.deepcopy(opened.current)
        opened.edit_timeline(tl, svg_data="<svg>new</svg>", viewer_beat_x={5.0: 50.0})
        opened.sync()
        opened.current = first
        opened.sync()
        assert opened.bytes() == opened.bytes_read


class TestLoneSurrogates:
    """A file can hold a lone surrogate, such as a label cut inside an emoji."""

    def test_tilias_digest_takes_one(self):
        assert hash_function("\ud83c")

    def test_tilias_digest_of_other_text_is_md5_of_its_utf8(self):
        for text in ("", "label", "Ständchen 主題 🎻"):
            assert hash_function(text) == hashlib.md5(text.encode("utf-8")).hexdigest()

    def test_tilia_builds_timelines_with_one(self, live):
        tl, marker = make_id(1), make_id(2)
        timeline = marker_timeline(
            1, **{marker: {"kind": "MARKER", "time": 1.0, "label": "\ud83c"}}
        )
        timeline["name"] = "\udfbb"
        doc = loads(file_with({tl: timeline}))
        opened = live(doc)
        given = opened.synced["timelines"][tl]
        expected = tla_bridge.state_of(doc)[tl]["components"][marker]
        assert given["components"][marker]["hash"] == expected["hash"]
        assert given["name"] == "\udfbb"
        opened.sync()
        assert opened.bytes() == opened.bytes_read


class TestNotes:
    def test_an_ordinary_edit_gives_none(self):
        opened = Opened.read(EVERY_KIND)
        timeline_id, component = first_component(opened.doc, "marker")
        opened.edit_component(timeline_id, component.id, label="edited")
        assert (
            tla_bridge.apply_changes(
                opened.doc, opened.synced, opened.current, removed=opened.removed
            )
            == []
        )


class TestDefensive:
    """What TiLiA's states don't hold today, and the bridge mustn't trip on."""

    def test_a_beat_both_states_hold_and_the_document_doesnt(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        for state in (opened.synced, opened.current):
            state["timelines"][timeline.id]["components"][NEW] = {
                "kind": "BEAT",
                "time": 0.5,
                "hash": "same",
            }
        numbers = opened.timeline(timeline.id)["measure_numbers"]
        opened.edit_timeline(timeline.id, measure_numbers=[n + 1 for n in numbers])
        opened.sync()
        assert tla.loads(opened.bytes())

    def test_no_counts_is_one_measure(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, beats_in_measure=[], measure_numbers=[])
        opened.sync()
        first = min(timeline.components.values(), key=lambda b: b.attrs["time"])
        assert isinstance(first.attrs.get("measure"), dict)
        assert tla.loads(opened.bytes())

    def test_fewer_numbers_than_measures(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(timeline.id, measure_numbers=[0, 1])
        opened.sync()
        assert [row.number for row in timeline.measures.rows][:4] == [0, 1, 2, 3]

    def test_a_measure_of_no_beats_and_more_counts_than_beats(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(
            timeline.id,
            beats_in_measure=[1, 0, 3, 3, 3, 3, 1, 2, 1, 4, 4],
            measure_numbers=list(range(11)),
        )
        opened.sync()
        assert len(timeline.measures.rows) == 8
        assert tla.loads(opened.bytes())

    def test_a_measure_of_no_beats_starts_none(self):
        opened = Opened.read(UNKNOWN)
        timeline = first_of_kind(opened.doc, "beat")
        opened.edit_timeline(
            timeline.id, beats_in_measure=[1, 0], measure_numbers=[1, 2]
        )
        opened.sync()
        assert len(timeline.measures.rows) == 1

    def test_a_new_timeline_of_a_kind_tilia_doesnt_store(self):
        opened = Opened.read(EMPTY)
        opened.add_timeline(NEW, kind="Lyrics")
        opened.sync()
        assert NEW not in opened.doc.timelines

    def test_something_else_under_a_timelines_id_in_removed(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "marker")
        before = copy.deepcopy(opened.current)
        opened.delete_timeline(timeline.id)
        opened.sync()
        stranger = tla.Component(id=timeline.id, kind="marker")
        opened.removed[timeline.id] = stranger
        opened.current = before
        opened.sync()
        assert opened.removed[timeline.id] is stranger
        assert opened.doc.timelines[timeline.id] is not timeline


class TestNoSharing:
    """A value of the state is never the document's, nor the other way round."""

    TL, SIGNATURE = make_id(3), make_id(2)

    def opened(self):
        timeline = {
            "kind": "Score",
            "ordinal": 1,
            "height": 160,
            "components": {
                make_id(1): {"kind": "STAFF", "line_count": 5, "index": 0},
                self.SIGNATURE: {
                    "kind": "TIME_SIGNATURE",
                    "staff_index": 0,
                    "time": 0.0,
                    "numerator": None,
                    "denominator": None,
                    "pairs": [["2", 4], ["3", 8]],
                },
            },
        }
        return Opened.from_content(file_with({self.TL: timeline}))

    def test_a_list_in_a_components_state(self):
        doc = self.opened().doc
        state = tla_bridge.state_of(doc)
        state[self.TL]["components"][self.SIGNATURE]["pairs"].append(["5", 8])
        stored = doc.timelines[self.TL].components[self.SIGNATURE]
        assert stored.extra["pairs"] == [["2", 4], ["3", 8]]

    def test_a_list_written_to_a_component(self):
        opened = self.opened()
        opened.edit_component(self.TL, self.SIGNATURE, pairs=[["3", 4]])
        opened.sync()
        opened.component(self.TL, self.SIGNATURE)["pairs"].append(["5", 8])
        stored = opened.doc.timelines[self.TL].components[self.SIGNATURE]
        assert stored.extra["pairs"] == [["3", 4]]


class TestOnlyWhatDiffersOnTimelines:
    def test_a_timeline_attribute_tilia_fills_in_isnt_written(self):
        opened = Opened.read(EVERY_KIND)
        timeline = first_of_kind(opened.doc, "marker")
        for state in (opened.synced, opened.current):
            state["timelines"][timeline.id]["height"] = 77
        opened.edit_timeline(timeline.id, name="Renamed")
        opened.sync()
        assert timeline.attrs["height"] == 30
        assert timeline.name == "Renamed"


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    return modules


class TestImports:
    def test_the_module_needs_neither_qt_nor_the_requests(self):
        # Of the app, only TiLiA's digest, which needs nothing else.
        bridge = Path(tla_bridge.__file__)
        digest = bridge.parents[1] / "timelines" / "hash_timelines.py"
        of_the_app = {"tilia.timelines.hash_timelines"}
        assert {
            name for name in imported_modules(bridge) if name.split(".")[0] == "tilia"
        } == of_the_app
        allowed = set(sys.stdlib_module_names) | {"tilia_core"}
        for path in (bridge, digest):
            outside = {
                name
                for name in imported_modules(path) - of_the_app
                if name.split(".")[0] not in allowed
            }
            assert outside == set(), path.name
