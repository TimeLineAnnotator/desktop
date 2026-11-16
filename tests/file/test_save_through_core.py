"""Saving a `.tla` file through the core.

Every save writes, through `tla.write`, the document TiLiA read, which follows each
action: a save without an edit gives the file's bytes, and an edit changes what the
same edit through the core's API changes. WP3's files are read in place; a file a
test saves is one the core wrote into the test's folder, so that the paths it
stores are the same for TiLiA and for the core.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import tilia.file.common
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tilia.file import autosave, open_document, tla_bridge
from tilia.file.media_metadata import MediaMetadata
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui import commands
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
EVERY_KIND = FILES / "golden" / "every-kind.tla"
EMPTY = FILES / "golden" / "empty.tla"
# WP3's third, unknown.tla, measures its times in quarter notes, which TiLiA refuses.
GOLDEN = [EVERY_KIND, EMPTY]
# Ids after those of WP3's files.
NEW = "019b76da-f000-7000-8000-000000000999"
OTHER = "019b76da-f000-7000-8000-000000000998"


def names(paths):
    return [path.name for path in paths]


def open_file(path) -> bool:
    """Opens `path`, as the File menu does, without saving the file open, keeping
    timelines of kinds TiLiA doesn't know and declining to look for media or PDFs
    that aren't there."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
    ):
        return commands.execute("file.open", path)


def save() -> bool:
    return commands.execute("file.save")


def save_as(path: Path) -> bool:
    return commands.execute("file.save_as", str(path))


def record() -> None:
    """Ends an action, as each of TiLiA's actions does."""
    post(Post.APP_STATE_RECORD, "test")


def written_by_the_core(source: Path, folder: Path, change=None) -> Path:
    """`source`, with `change` made to its document, as the core writes it into
    `folder`."""
    doc = tla.read(source)
    if change is not None:
        change(doc)
    path = folder / "file.tla"
    tla.write(path, doc)
    return path


def the_core_s_bytes(path: Path, change) -> bytes:
    """What the core writes for `change`, made through its API to the file at `path`,
    into the same folder, so that the paths it stores are the same."""
    doc = tla.read(path)
    change(doc)
    other = path.parent / "by the core.tla"
    tla.write(other, doc)
    return other.read_bytes()


def first_of_kind(doc: tla.Document, kind: str) -> tla.Timeline:
    return min(
        (tl for tl in doc.timelines.values() if tl.kind == kind),
        key=lambda tl: tl.ordinal,
    )


def keys_in(value):
    """Every key of every object in `value`, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys_in(item)


def ids_in(content: dict) -> set[str]:
    """The document's id, and each timeline's and component's."""
    found = {content["document_id"]}
    for timeline_id, timeline in content["timelines"].items():
        found.add(timeline_id)
        found.update(timeline.get("components", {}))
    return found


def the_document(tilia) -> tla.Document:
    return tilia.file_manager.file.document


@pytest.fixture
def every_kind(qtui, tilia, tls, tmp_path) -> Path:
    """WP3's file of every kind, as the core writes it into the test's folder, open."""
    path = written_by_the_core(EVERY_KIND, tmp_path)
    assert open_file(path)
    return path


class TestNoEdit:
    @pytest.mark.parametrize("golden", GOLDEN, ids=names(GOLDEN))
    def test_a_file_the_core_wrote_keeps_its_bytes(
        self, qtui, tilia, tls, tmp_path, golden
    ):
        # Its media and PDF aren't there: TiLiA says so, and the file keeps their
        # paths.
        path = written_by_the_core(golden, tmp_path)
        before = path.read_bytes()
        assert open_file(path)

        assert save()

        assert path.read_bytes() == before
        assert not tilia.is_file_modified()

    @pytest.mark.parametrize("golden", GOLDEN, ids=names(GOLDEN))
    def test_saved_as_it_gives_the_core_s_bytes(
        self, qtui, tilia, tls, tmp_path, golden
    ):
        # The golden file, read in place: saved elsewhere, its paths follow the new
        # folder, as the core's write does.
        expected = tmp_path / "by the core.tla"
        tla.write(expected, tla.read(golden))
        assert open_file(golden)

        assert save_as(tmp_path / "saved.tla")

        assert (tmp_path / "saved.tla").read_bytes() == expected.read_bytes()

    def test_a_file_without_paths_saved_elsewhere_keeps_its_bytes(
        self, qtui, tilia, tls, tmp_path
    ):
        assert open_file(EMPTY)

        assert save_as(tmp_path / "saved.tla")

        assert (tmp_path / "saved.tla").read_bytes() == EMPTY.read_bytes()


class TestSameEditThroughTheCore:
    """SC-002's edits, made in TiLiA and through the core's API: the files are
    byte-identical. An edit ends with a record, as TiLiA's actions do; one that
    doesn't record, such as a metadata field's, reaches the file at the save."""

    def assert_the_core_s(self, path: Path, change) -> None:
        expected = the_core_s_bytes(path, change)
        before = path.read_bytes()

        assert save()

        assert path.read_bytes() != before
        assert path.read_bytes() == expected

    @staticmethod
    def markers(tilia):
        timeline = first_of_kind(the_document(tilia), "marker")
        return timeline.id, next(iter(timeline.components))

    def test_a_label(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.markers(tilia)
        tls.get_timeline(timeline_id).set_component_data(
            marker_id, "label", "Ein Thema 主題"
        )
        record()

        def change(doc):
            doc.timelines[timeline_id].components[marker_id].attrs[
                "label"
            ] = "Ein Thema 主題"

        self.assert_the_core_s(every_kind, change)

    def test_a_time(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.markers(tilia)
        time = (
            the_document(tilia)
            .timelines[timeline_id]
            .components[marker_id]
            .attrs["time"]
        )
        tls.get_timeline(timeline_id).set_component_data(
            marker_id, "time", time + 0.125
        )
        record()

        def change(doc):
            doc.timelines[timeline_id].components[marker_id].attrs["time"] = (
                time + 0.125
            )

        self.assert_the_core_s(every_kind, change)

    def test_a_colour(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.markers(tilia)
        tls.get_timeline(timeline_id).set_component_data(marker_id, "color", "#123456")
        record()

        def change(doc):
            doc.timelines[timeline_id].components[marker_id].attrs["color"] = "#123456"

        self.assert_the_core_s(every_kind, change)

    def test_a_metadata_value(self, every_kind, tilia):
        post(Post.MEDIA_METADATA_FIELD_SET, "composer", "F. Schubert")

        def change(doc):
            doc.metadata["composer"] = "F. Schubert"

        self.assert_the_core_s(every_kind, change)

    def test_a_timeline_s_name(self, every_kind, tilia, tls):
        timeline_id, _ = self.markers(tilia)
        tls.set_timeline_data(timeline_id, "name", "Renamed")
        record()

        def change(doc):
            doc.timelines[timeline_id].name = "Renamed"

        self.assert_the_core_s(every_kind, change)

    def test_a_component_added(self, every_kind, tilia, tls):
        timeline_id, _ = self.markers(tilia)
        with Serve(Get.ID, NEW):
            tls.get_timeline(timeline_id).create_component(
                ComponentKind.MARKER, time=3.25
            )
        record()

        def change(doc):
            doc.timelines[timeline_id].components[NEW] = tla.Component(
                id=NEW, kind="marker", attrs={"time": 3.25}
            )

        self.assert_the_core_s(every_kind, change)

    def test_a_component_removed(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.markers(tilia)
        timeline = tls.get_timeline(timeline_id)
        timeline.delete_components([timeline.get_component(marker_id)])
        record()

        def change(doc):
            del doc.timelines[timeline_id].components[marker_id]

        self.assert_the_core_s(every_kind, change)

    def test_a_timeline_added(self, every_kind, tilia, tls):
        top = max(tl.ordinal for tl in the_document(tilia).timelines.values())
        with Serve(Get.ID, NEW):
            tls.create_timeline(MarkerTimeline, name="New")
        record()
        height = tls.get_timeline(NEW).get_data("height")

        def change(doc):
            doc.timelines[NEW] = tla.Timeline(
                id=NEW,
                kind="marker",
                ordinal=top + 1,
                name="New",
                attrs={"height": height},
            )

        self.assert_the_core_s(every_kind, change)

    def test_a_timeline_removed(self, every_kind, tilia, tls):
        timeline_id = first_of_kind(the_document(tilia), "hierarchy").id
        tls.delete_timeline(tls.get_timeline(timeline_id))
        record()

        def change(doc):
            del doc.timelines[timeline_id]

        self.assert_the_core_s(every_kind, change)


class TestWhatTiLiADoesntShow:
    def test_a_timeline_of_a_kind_tilia_doesnt_know_keeps_its_place(
        self, qtui, tilia, tls, tmp_path
    ):
        # US1's scenario 3 and FR-011: kept between two TiLiA knows, it is written
        # back as it was, with its ordinal, and a new timeline goes after it.
        content = json.loads(EVERY_KIND.read_bytes())
        for timeline in content["timelines"].values():
            if timeline["ordinal"] >= 3:
                timeline["ordinal"] += 1
        lyrics = {
            "kind": "Lyrics",
            "name": "Lyrics",
            "ordinal": 3,
            "x_syllables": ["Lei", "se"],
            "components": {OTHER: {"kind": "SYLLABLE", "time": 1.0, "text": "Lei"}},
        }
        content["timelines"][OTHER] = lyrics
        path = tmp_path / "file.tla"
        tla.write(path, tla.loads(json.dumps(content).encode()))
        written = json.loads(path.read_bytes())["timelines"][OTHER]
        top = max(timeline["ordinal"] for timeline in content["timelines"].values())
        assert open_file(path)

        with Serve(Get.ID, NEW):
            tls.create_timeline(MarkerTimeline, name="New")
        record()
        assert save()

        saved = json.loads(path.read_bytes())["timelines"]
        assert saved[OTHER] == written
        assert saved[OTHER]["ordinal"] == 3
        assert saved[NEW]["ordinal"] == top + 1

    def test_tags_generated_by_and_unknown_keys_stay(self, qtui, tilia, tls, tmp_path):
        # US1's scenario 4, with an edit of the component that holds them.
        hierarchy = "019b76da-a824-7a81-acc3-ea266958308f"

        def unknown_keys(doc):
            form = first_of_kind(doc, "hierarchy")
            form.components[hierarchy].extra["x_analyst"] = "AF"
            form.extra["x_layer"] = {"kept": True}

        path = written_by_the_core(EVERY_KIND, tmp_path, unknown_keys)
        component = json.loads(path.read_bytes())["timelines"][
            "019b76da-a804-7297-8763-137b42b8b88a"
        ]["components"][hierarchy]
        assert component["metadata"]["tags"] and component["metadata"]["generated_by"]
        assert open_file(path)
        form = first_of_kind(the_document(tilia), "hierarchy").id

        tls.get_timeline(form).set_component_data(hierarchy, "label", "Hauptsatz")
        record()

        def change(doc):
            doc.timelines[form].components[hierarchy].attrs["label"] = "Hauptsatz"

        expected = the_core_s_bytes(path, change)
        assert save()
        assert path.read_bytes() == expected
        saved = json.loads(path.read_bytes())["timelines"][form]
        assert saved["components"][hierarchy]["metadata"] == component["metadata"]
        assert saved["components"][hierarchy]["x_analyst"] == "AF"
        assert saved["x_layer"] == {"kept": True}


class TestPreStart:
    """US1's scenario 5, as `plan.md` reads it."""

    def test_a_hierarchy_made_in_tilia_stores_none(
        self, qtui, tilia, hierarchy_tlui, tmp_path
    ):
        # Its pre-start and post-end are its start and end.
        hierarchy_tlui.timeline.create_component(
            ComponentKind.HIERARCHY, start=10.0, end=20.0, level=1
        )
        record()
        path = tmp_path / "file.tla"

        assert save_as(path)

        components = json.loads(path.read_bytes())["timelines"][hierarchy_tlui.id][
            "components"
        ]
        assert len(components) == 1
        for component in components.values():
            assert "pre_start" not in component
            assert "post_end" not in component

    def test_a_dragged_one_is_written(self, every_kind, tilia, tls):
        form = first_of_kind(the_document(tilia), "hierarchy").id
        theme = "019b76da-a826-7213-a688-b35de6509a46"  # 14.5 to 16.0, none stored
        tls.get_timeline(form).set_component_data(theme, "pre_start", 14.0)
        record()

        assert save()

        saved = json.loads(every_kind.read_bytes())["timelines"][form]["components"]
        assert saved[theme]["pre_start"] == 14.0

    def test_one_the_file_stores_equal_stays_until_edited(
        self, qtui, tilia, tls, tmp_path
    ):
        theme = "019b76da-a826-7213-a688-b35de6509a46"

        def store_it_equal(doc):
            first_of_kind(doc, "hierarchy").components[theme].attrs["pre_start"] = 14.5

        path = written_by_the_core(EVERY_KIND, tmp_path, store_it_equal)
        before = path.read_bytes()
        assert open_file(path)
        form = first_of_kind(the_document(tilia), "hierarchy").id

        assert save()
        assert path.read_bytes() == before

        tls.get_timeline(form).set_component_data(theme, "label", "Thema")
        record()
        assert save()
        saved = json.loads(path.read_bytes())["timelines"][form]["components"]
        assert "pre_start" not in saved[theme]


def assert_holds_no_hash_no_file_path_and_the_format_s_version(path: Path) -> None:
    content = json.loads(path.read_bytes())
    assert content["version"] == tla.FORMAT_VERSION
    keys = set(keys_in(content))
    assert not keys & {"hash", "components_hash", "timelines_hash", "file_path"}


class TestWhatTheFileHolds:
    """US1's scenario 6: no hash, no `file_path`, and the format's version."""

    def test_a_new_file(self, qtui, tilia, marker_tlui, tmp_path):
        marker_tlui.timeline.create_component(ComponentKind.MARKER, time=1.5)
        record()
        path = tmp_path / "saved.tla"

        assert save_as(path)

        assert_holds_no_hash_no_file_path_and_the_format_s_version(path)

    def test_a_file_read(self, every_kind, tilia, tls):
        timeline_id = first_of_kind(the_document(tilia), "marker").id
        tls.get_timeline(timeline_id).create_component(ComponentKind.MARKER, time=1.5)
        record()

        assert save()

        assert_holds_no_hash_no_file_path_and_the_format_s_version(every_kind)

    def test_a_new_file_starts_as_the_core_makes_one(self, qtui, tilia, tmp_path):
        # FR-008.
        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            commands.execute("file.new")
        path = tmp_path / "new.tla"

        assert save_as(path)

        content = json.loads(path.read_bytes())
        fields = settings.get("media_metadata", "default_fields")
        assert content["metadata"] == {
            "title": "Untitled",
            "notes": "",
            **{field: "" for field in fields},
        }
        assert content["time_unit"] == "seconds"
        assert tla.read(path).document_id == the_document(tilia).document_id

    def test_two_new_files_have_their_own_document_ids(self, qtui, tilia, tmp_path):
        ids = []
        for name in ("one.tla", "two.tla"):
            with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
                commands.execute("file.new")
            assert save_as(tmp_path / name)
            ids.append(tla.read(tmp_path / name).document_id)
        assert ids[0] != ids[1]


class TestTitle:
    """FR-008, as #563 (an untitled file) decided: a file opened without a title shows
    "Untitled", and no title is written until the user sets one."""

    def test_a_file_without_one_shows_untitled_and_writes_none(
        self, qtui, tilia, tmp_path
    ):
        assert open_file(EMPTY)
        assert get(Get.MEDIA_TITLE) == MediaMetadata.REQUIRED_FIELDS["title"]

        assert save_as(tmp_path / "Some Name.tla")

        assert (
            "title"
            not in json.loads((tmp_path / "Some Name.tla").read_bytes())["metadata"]
        )
        assert get(Get.MEDIA_TITLE) == MediaMetadata.REQUIRED_FIELDS["title"]

    def test_save_as_doesn_t_make_the_file_s_name_its_title(
        self, qtui, tilia, tmp_path
    ):
        path = tmp_path / "Some Name.tla"

        assert save_as(path)

        assert get(Get.MEDIA_TITLE) == MediaMetadata.REQUIRED_FIELDS["title"]
        assert json.loads(path.read_bytes())["metadata"]["title"] == "Untitled"

    def test_one_the_user_sets_is_written(self, qtui, tilia, tmp_path):
        assert open_file(EMPTY)
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "Ständchen")

        assert save_as(tmp_path / "saved.tla")

        content = json.loads((tmp_path / "saved.tla").read_bytes())
        assert content["metadata"] == {"title": "Ständchen"}


class TestSaveAs:
    def test_keeps_every_id(self, every_kind, tilia, tmp_path):
        # FR-005.
        (tmp_path / "copy").mkdir()
        copy_path = tmp_path / "copy" / "copy.tla"

        assert save_as(copy_path)

        assert ids_in(json.loads(copy_path.read_bytes())) == ids_in(
            json.loads(every_kind.read_bytes())
        )

    def test_the_media_path_follows_the_new_folder(self, qtui, tilia, tmp_path):
        (tmp_path / "media").mkdir()
        media = tmp_path / "media" / "example.mp3"
        media.write_bytes(Path(EXAMPLE_MEDIA_PATH).read_bytes())

        def with_media(doc):
            doc.media_path = str(media)
            # Its length, so that loading it asks nothing about scaling.
            doc.media_length = 9.952

        path = written_by_the_core(EMPTY, tmp_path, with_media)
        assert json.loads(path.read_bytes())["media"]["path"] == "media/example.mp3"
        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
            assert open_file(path)
        (tmp_path / "elsewhere").mkdir()

        assert save_as(tmp_path / "elsewhere" / "saved.tla")

        saved = json.loads((tmp_path / "elsewhere" / "saved.tla").read_bytes())
        assert saved["media"]["path"] == "../media/example.mp3"

    def test_the_file_open_is_then_the_one_saved(self, every_kind, tilia, tmp_path):
        other = tmp_path / "other.tla"

        assert save_as(other)

        assert Path(tilia.file_manager.file.file_path) == other
        assert not tilia.is_file_modified()


class TestTheDocumentWritten:
    """The one read, with its fingerprint (#533, desktop#856), never one built again
    from TiLiA's state: a document built in memory has no fingerprint, and the check
    before saving would then check nothing."""

    def test_is_the_one_read(self, every_kind, tilia, tls):
        read = the_document(tilia)
        assert read.fingerprint == tla.fingerprint(every_kind)
        timeline_id = first_of_kind(read, "marker").id
        marker = next(iter(read.timelines[timeline_id].components))
        tls.get_timeline(timeline_id).set_component_data(marker, "label", "edited")
        record()

        with patch.object(tla, "write", wraps=tla.write) as write:
            assert save()

        assert write.call_args.args[1] is read
        assert the_document(tilia) is read
        assert read.fingerprint == tla.fingerprint(every_kind)

    def test_a_save_writes_nothing_but_the_file(self, every_kind, tilia, tmp_path):
        assert save()

        assert sorted(path.name for path in tmp_path.iterdir()) == ["file.tla"]


class TestSync:
    """The document follows TiLiA at each action, after each command line command,
    after each undo and redo, and before each write."""

    @staticmethod
    def label(tilia, timeline_id, marker_id):
        return (
            the_document(tilia)
            .timelines[timeline_id]
            .components[marker_id]
            .attrs.get("label")
        )

    @staticmethod
    def a_marker(tilia):
        timeline = first_of_kind(the_document(tilia), "marker")
        return timeline.id, next(iter(timeline.components))

    def test_at_each_action(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.a_marker(tilia)

        tls.get_timeline(timeline_id).set_component_data(marker_id, "label", "edited")
        record()

        assert self.label(tilia, timeline_id, marker_id) == "edited"

    def test_at_the_end_of_a_command_line_command(self, every_kind, tilia):
        post(Post.MEDIA_METADATA_FIELD_SET, "composer", "F. Schubert")
        assert the_document(tilia).metadata["composer"] == "Franz Schubert"

        post(Post.APP_EDIT_DONE)

        assert the_document(tilia).metadata["composer"] == "F. Schubert"

    def test_before_a_write(self, every_kind, tilia):
        post(Post.MEDIA_METADATA_FIELD_SET, "composer", "F. Schubert")

        assert save()

        assert tla.read(every_kind).metadata["composer"] == "F. Schubert"

    def test_after_each_undo_and_redo_once_as_neither_is_a_person_s_edit(
        self, every_kind, tilia, tls
    ):
        timeline_id, marker_id = self.a_marker(tilia)
        timeline = tls.get_timeline(timeline_id)
        before = self.label(tilia, timeline_id, marker_id)
        for label in ("first", "second"):
            timeline.set_component_data(marker_id, "label", label)
            record()

        with patch.object(
            tla_bridge, "apply_changes", wraps=tla_bridge.apply_changes
        ) as apply:
            for command, expected in (
                ("edit.undo", "first"),
                ("edit.undo", before),
                ("edit.redo", "first"),
            ):
                apply.reset_mock()
                commands.execute(command)
                assert apply.call_count == 1
                assert apply.call_args.kwargs["by_person"] is False
                assert self.label(tilia, timeline_id, marker_id) == expected

    def test_an_action_is_a_person_s_edit(self, every_kind, tilia, tls):
        timeline_id, marker_id = self.a_marker(tilia)
        with patch.object(
            tla_bridge, "apply_changes", wraps=tla_bridge.apply_changes
        ) as apply:
            tls.get_timeline(timeline_id).set_component_data(
                marker_id, "label", "edited"
            )
            record()

        assert apply.call_count == 1
        assert apply.call_args.kwargs["by_person"] is True

    def test_a_record_posted_while_an_undo_restores_isn_t_a_person_s_edit(
        self, every_kind, tilia, tls
    ):
        # While a state is restored, the undo manager doesn't record: the undo
        # syncs once it is restored, never part-way as a person's edit.
        timeline_id, marker_id = self.a_marker(tilia)
        tls.get_timeline(timeline_id).set_component_data(marker_id, "label", "edited")
        record()
        restore = tilia.timelines.restore_state

        def restore_and_record(states):
            restore(states)
            record()

        with (
            patch.object(
                tilia.timelines, "restore_state", side_effect=restore_and_record
            ),
            patch.object(
                tla_bridge, "apply_changes", wraps=tla_bridge.apply_changes
            ) as apply,
        ):
            commands.execute("edit.undo")

        assert [call.kwargs["by_person"] for call in apply.call_args_list] == [False]

    def test_the_notes_it_gives_are_logged(self, every_kind, tilia, tls):
        # As #538 (the rule that keeps measure marks) asked.
        timeline_id, marker_id = self.a_marker(tilia)
        tls.get_timeline(timeline_id).set_component_data(marker_id, "label", "edited")
        with (
            patch.object(
                tla_bridge, "apply_changes", return_value=["a mark left the file"]
            ),
            patch.object(open_document.logger, "warning") as warning,
        ):
            record()

        warning.assert_called_once_with("a mark left the file")

    def test_a_recovery_keeps_the_document(self, every_kind, tilia, tls):
        # After a command fails, TiLiA goes back to the state before it: the file
        # open stays the one read.
        file = tilia.file_manager.file
        read = file.document
        before = every_kind.read_bytes()
        timeline_id, marker_id = self.a_marker(tilia)
        state = tilia.get_app_state()
        tls.get_timeline(timeline_id).set_component_data(marker_id, "label", "failed")

        # Its timelines are made again: TiLiA looks for the PDF again too.
        with Serve(Get.FROM_USER_RETRY_PDF_PATH, False):
            post(Post.APP_STATE_RECOVER, state)

        assert tilia.file_manager.file is file
        assert file.document is read
        assert Path(file.file_path) == every_kind
        assert self.label(tilia, timeline_id, marker_id) != "failed"
        assert save()
        assert every_kind.read_bytes() == before


_STATE_OF = tla_bridge.state_of
SHOWN = 120  # a height TiLiA could show instead of the one stored


def as_desktop_895_loads(doc: tla.Document) -> dict:
    """What TiLiA builds from `doc` once TimeLineAnnotator/desktop#895 is in: a range
    or score timeline whose stored height is below 10 shows TiLiA's default height."""
    state = _STATE_OF(doc)
    for timeline in state.values():
        if timeline["kind"] in ("Range", "Score") and (timeline["height"] or 0) < 10:
            timeline["height"] = SHOWN
    return state


class TestAHeightTiLiAShowsInsteadOfTheStoredOne:
    """TiLiA saved range and score timelines with height 1. Once TiLiA shows them at
    its default height (TimeLineAnnotator/desktop#895), the file keeps the stored
    height until the height is edited, as for what TiLiA fills in (FR-003, #524)."""

    @staticmethod
    def stored_at_1(doc):
        for timeline in doc.timelines.values():
            if timeline.kind in ("range", "score"):
                timeline.attrs["height"] = 1

    @staticmethod
    def low(tilia) -> list[str]:
        return [
            timeline.id
            for timeline in the_document(tilia).timelines.values()
            if timeline.kind in ("range", "score")
        ]

    def test_is_written_only_once_edited(self, qtui, tilia, tls, tmp_path):
        path = written_by_the_core(EVERY_KIND, tmp_path, self.stored_at_1)
        before = path.read_bytes()
        with patch.object(tla_bridge, "state_of", side_effect=as_desktop_895_loads):
            assert open_file(path)
        low = self.low(tilia)
        assert len(low) == 2
        assert {tls.get_timeline(id).get_data("height") for id in low} == {SHOWN}

        assert save()
        assert path.read_bytes() == before

        # Another edit of the range timeline leaves its height; an edit of the
        # score timeline's height writes it.
        score = first_of_kind(the_document(tilia), "score").id
        ranges = first_of_kind(the_document(tilia), "range").id
        tls.set_timeline_data(ranges, "name", "Renamed")
        tls.set_timeline_data(score, "height", SHOWN + 10)
        record()
        assert save()
        saved = json.loads(path.read_bytes())["timelines"]
        assert saved[score]["height"] == SHOWN + 10
        assert saved[ranges]["name"] == "Renamed"
        assert saved[ranges]["height"] == 1

    def test_without_an_edit_the_file_keeps_it(self, qtui, tilia, tls, tmp_path):
        # As TiLiA loads it here: before desktop#895 at 1, after it at its default.
        path = written_by_the_core(EVERY_KIND, tmp_path, self.stored_at_1)
        before = path.read_bytes()
        assert open_file(path)

        assert save()

        assert path.read_bytes() == before


class TestAFailedSave:
    def test_leaves_the_file_and_the_changes_unsaved(
        self, every_kind, tilia, tls, tilia_errors, tmp_path
    ):
        timeline_id = first_of_kind(the_document(tilia), "marker").id
        tls.set_timeline_data(timeline_id, "name", "Renamed")
        record()

        assert not save_as(tmp_path / "not there" / "file.tla")

        tilia_errors.assert_error()
        assert tilia.is_file_modified()
        assert Path(tilia.file_manager.file.file_path) == every_kind

    def test_a_new_rule_breach_writes_nothing(
        self, every_kind, tilia, tls, tilia_errors
    ):
        # A marker at the time of another, which TiLiA's creation checks would
        # refuse: the core refuses to write it (`BrokenRules`).
        timeline = first_of_kind(the_document(tilia), "marker")
        time = next(iter(timeline.components.values())).attrs["time"]
        before = every_kind.read_bytes()
        tls.get_timeline(timeline.id).create_component(
            ComponentKind.MARKER, time=time, checked=False
        )
        record()

        assert not save()

        tilia_errors.assert_error()
        assert every_kind.read_bytes() == before
        assert tilia.is_file_modified()


class TestAProblemTheFileCameWith:
    @staticmethod
    def two_markers_at_one_time(tmp_path) -> tuple[Path, str, str, float]:
        """WP3's file of every kind, with a second marker at the first's time: a
        problem the reader keeps, with a warning."""
        doc = tla.read(EVERY_KIND)
        markers = first_of_kind(doc, "marker")
        time = next(iter(markers.components.values())).attrs["time"]
        markers.components[NEW] = tla.Component(
            id=NEW, kind="marker", attrs={"time": time}
        )
        path = tmp_path / "file.tla"
        # `write` would refuse the problem; the file is laid out as it would be.
        path.write_bytes(tla.canonical_bytes(doc))
        return path, markers.id, NEW, time

    def test_stays_while_its_component_is_unchanged(self, qtui, tilia, tls, tmp_path):
        path, timeline_id, _, _ = self.two_markers_at_one_time(tmp_path)
        before = path.read_bytes()
        assert open_file(path)
        tls.set_timeline_data(timeline_id, "name", "Renamed")
        record()

        assert save()

        assert (
            json.loads(path.read_bytes())["timelines"][timeline_id]["components"][NEW]
            == json.loads(before)["timelines"][timeline_id]["components"][NEW]
        )

    @pytest.mark.xfail(
        strict=True,
        reason="the core refuses a problem a file came with once a save wrote the"
        " file without it, until TimeLineAnnotator/project-management#569",
    )
    def test_comes_back_with_an_undo_past_a_save(self, qtui, tilia, tls, tmp_path):
        # #562: an undo back past a save, to a problem the file came with, must not
        # be refused.
        path, timeline_id, marker_id, time = self.two_markers_at_one_time(tmp_path)
        before = path.read_bytes()
        assert open_file(path)
        tls.get_timeline(timeline_id).set_component_data(marker_id, "time", time + 1)
        record()
        assert save()

        commands.execute("edit.undo")

        assert save()
        assert path.read_bytes() == before


class TestAutosave:
    def test_writes_a_copy_and_leaves_the_document_open(
        self, every_kind, tilia, tls, tmp_path
    ):
        # #555: a write makes the document it is given follow the file written, and
        # the first save of an old file keeps what its migration kept absolute, so an
        # autosave never writes the document open.
        file = tilia.file_manager.file
        read = file.document
        origin, fingerprint = read.origin, read.fingerprint
        timeline_id = first_of_kind(read, "marker").id
        tls.set_timeline_data(timeline_id, "name", "Renamed")
        record()
        (tmp_path / "autosaves").mkdir()
        autosave_path = tmp_path / "autosaves" / "autosave.tla"

        with (
            patch.object(autosave, "get_autosave_path", return_value=autosave_path),
            patch.object(autosave, "make_room_for_new_autosave"),
        ):
            autosave.autosave(file.copy_for_writing())

        assert (read.origin, read.fingerprint) == (origin, fingerprint)
        assert tla.read(autosave_path).timelines[timeline_id].name == "Renamed"


class TestTheOldWriterIsGone:
    def test_write_tilia_file_to_disk_and_tilia_file_are_gone(self):
        assert not hasattr(tilia.file.common, "write_tilia_file_to_disk")
        assert importlib.util.find_spec("tilia.file.tilia_file") is None

    def test_the_app_s_state_holds_no_version_app_name_or_file_path(self, tilia):
        assert set(tilia.get_app_state()) == {
            "media_metadata",
            "media_path",
            "timelines",
            "timelines_hash",
        }
