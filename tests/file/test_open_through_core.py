"""Opening a `.tla` file through the core.

Every file opens through `tla.read`. A file the core refuses leaves the file open
before as it was, and every component the reader keeps is kept and drawn, even one
that breaks a rule. WP3's files are read in place; the files that break a rule are
made with WP3's own `make_broken.py`, as its tests make them.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QImage, QPainter

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tilia.file import tla_bridge
from tilia.media.player import QtAudioPlayer
from tilia.requests import Get, Post, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia_core import tla

FILES = Path(__file__).parents[2] / "packages" / "tilia-core" / "tests" / "tla"
BROKEN = sorted((FILES / "broken").glob("*.tla"))
GOLDEN = [FILES / "golden" / "every-kind.tla", FILES / "golden" / "empty.tla"]
OLD = sorted((FILES / "old").glob("*.tla"))
IN_QUARTERS = FILES / "golden" / "unknown.tla"


def _load_make_broken():
    spec = importlib.util.spec_from_file_location(
        "make_broken", FILES / "broken" / "make_broken.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_broken = _load_make_broken()
IDS = make_broken.IDS
FORM, CADENCES, BEATS = IDS["form"], IDS["cadences"], IDS["beats"]
FIRST, SECOND = make_broken.make_id(100), make_broken.make_id(101)
LYRICS = make_broken.make_id(102)
HARMONIES = make_broken.make_id(103)


def names(paths):
    return [path.name for path in paths]


def a_file(tmp_path: Path, change=None, name: str = "file.tla") -> Path:
    """WP3's valid file, with `change` made to its content."""
    content = copy.deepcopy(make_broken.base())
    if change is not None:
        change(content)
    path = tmp_path / name
    path.write_text(make_broken.text_of(content), encoding="utf-8")
    return path


def hierarchies(*components):
    def change(content):
        content["timelines"][FORM]["components"] = {
            id: {"kind": "HIERARCHY", **attrs} for id, attrs in components
        }

    return change


def markers(*components):
    def change(content):
        content["timelines"][CADENCES]["components"] = {
            id: {"kind": "MARKER", **attrs} for id, attrs in components
        }

    return change


def with_media_length(length):
    def change(content):
        content["media"]["length"] = length

    return change


def together(*changes):
    def change(content):
        for one in changes:
            one(content)

    return change


def with_lyrics_in_the_middle(content):
    """A timeline of a kind TiLiA doesn't know, between two it knows."""
    content["timelines"][CADENCES]["ordinal"] = 6
    content["timelines"][LYRICS] = {
        "kind": "Lyrics",
        "name": "Lyrics",
        "ordinal": 3,
        "components": {},
    }


def open_file(path) -> bool:
    """Opens `path`, as the File menu does, declining to look for media or PDFs
    that aren't there."""
    with (
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
    ):
        return commands.execute("file.open", path)


def draw(timeline_ui) -> None:
    """Paints every item of a timeline, offscreen, as the screen would."""
    scene = timeline_ui.scene
    image = QImage(800, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        scene.render(painter)
    finally:
        painter.end()


class ServeRecording(Serve):
    """Serves a request, keeping what it was asked with."""

    args: tuple = ()

    def _callback(self, *args, **kwargs):
        self.args = args
        return super()._callback(*args, **kwargs)


class OpenBefore:
    """What a refused file must leave as it was: the file open before."""

    def __init__(self, tilia):
        self.tilia = tilia
        self.file = tilia.file_manager.file
        self.state = tilia.get_app_state()
        self.recent_files = settings.get_recent_files()

    def assert_unchanged(self):
        assert self.tilia.file_manager.file is self.file
        assert self.tilia.get_app_state() == self.state
        assert settings.get_recent_files() == self.recent_files


@pytest.fixture
def open_before(qtui, tilia, tls, tmp_path):
    path = a_file(tmp_path, name="before.tla")
    assert open_file(path)
    return OpenBefore(tilia)


def the_core_s_reason(path: Path) -> str:
    with pytest.raises(tla.UnreadableFile) as error:
        tla.read(path)
    if error.value.line is None:
        return error.value.message
    return f"line {error.value.line}: {error.value.message}"


class TestRefused:
    @pytest.mark.parametrize("path", BROKEN, ids=names(BROKEN))
    def test_a_file_the_core_refuses_gives_its_message_and_changes_nothing(
        self, open_before, tilia_errors, path
    ):

        assert not open_file(path)

        assert len(tilia_errors.errors) == 1
        error = tilia_errors.errors[0]
        if path.name == "newer-format.tla":
            assert error == {
                "title": "Open file",
                "message": "'newer-format.tla' was written by a newer version of"
                " TiLiA (format 2.0.0). Update TiLiA to open it.",
            }
        elif path.name == "older-draft.tla":
            assert error == {
                "title": "Open file",
                "message": "'older-draft.tla' is in a draft of TiLiA's file format"
                " (1.0.0-draft.0), which this version can't open. Convert it again"
                " from its sources.",
            }
        else:
            assert error == {
                "title": "Invalid file type",
                "message": f"File '{path.name}' is not a valid .tla file."
                f" {the_core_s_reason(path)}",
            }
        open_before.assert_unchanged()

    def test_the_core_s_reason_names_the_line(self, open_before, tilia_errors):

        open_file(FILES / "broken" / "not-json.tla")

        assert tilia_errors.errors[0]["message"] == (
            "File 'not-json.tla' is not a valid .tla file."
            " line 6: not valid JSON (Expecting ',' delimiter)"
        )

    def test_a_file_in_quarter_notes_is_refused(self, open_before, tilia_errors):

        assert not open_file(IN_QUARTERS)

        assert tilia_errors.errors == [
            {
                "title": "Open file",
                "message": "'unknown.tla' measures its times in quarter notes, which"
                " this version of TiLiA can't show yet.",
            }
        ]
        open_before.assert_unchanged()

    def test_a_file_that_isnt_there_gives_today_s_message(
        self, open_before, tilia_errors, tmp_path
    ):
        path = tmp_path / "nothing here.tla"

        assert not open_file(path)

        assert tilia_errors.errors == [
            {"title": "File not found", "message": f"File '{path}' not found."}
        ]
        open_before.assert_unchanged()

    def test_a_file_the_system_cant_open_gives_the_system_s_error(
        self, open_before, tilia_errors, tmp_path
    ):
        path = tmp_path / "a folder.tla"
        path.mkdir()
        with pytest.raises(OSError) as system_error:
            path.open("rb")

        assert not open_file(path)

        assert len(tilia_errors.errors) == 1
        assert tilia_errors.errors[0]["title"] == "Load file error"
        assert str(path) in tilia_errors.errors[0]["message"]
        assert system_error.value.strerror in tilia_errors.errors[0]["message"]
        open_before.assert_unchanged()

    def test_cancelling_the_question_on_unknown_kinds_changes_nothing(
        self, open_before, tilia_errors, tmp_path
    ):
        path = a_file(tmp_path, with_lyrics_in_the_middle)

        with Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (False, False)):
            assert not commands.execute("file.open", path)

        tilia_errors.assert_no_error()
        open_before.assert_unchanged()

    def test_a_file_that_fails_to_load_leaves_the_one_open(
        self, open_before, tilia, tilia_errors, tmp_path
    ):
        path = a_file(tmp_path)
        cur_file_path = tilia.cur_file_path

        with patch.object(tla_bridge, "state_of", side_effect=RuntimeError):
            assert not open_file(path)

        assert tilia_errors.errors[0]["title"] == "Load file error"
        assert tilia.cur_file_path == cur_file_path
        open_before.assert_unchanged()


def expected_timelines(path: Path) -> dict:
    return tla_bridge.state_of(tla.read(path))


def digests(components: dict) -> dict:
    return {id: component["hash"] for id, component in components.items()}


class TestOpened:
    @pytest.mark.parametrize("path", GOLDEN + OLD, ids=names(GOLDEN + OLD))
    def test_opens_with_its_timelines_and_components(self, qtui, tilia, tls, path):
        expected = expected_timelines(path)

        assert open_file(path)

        state = tilia.get_app_state()["timelines"]
        for id, timeline in expected.items():
            assert state[id]["kind"] == timeline["kind"]
            if timeline["kind"] == "AudioWave":
                continue  # its bars are computed from the media
            assert digests(state[id]["components"]) == digests(timeline["components"])
        # The slider timeline TiLiA shows when the file has none.
        assert {state[id]["kind"] for id in state.keys() - expected.keys()} <= {
            "Slider"
        }
        assert not tilia.is_file_modified()

    def test_an_edit_of_a_component_alone_reads_as_modified(
        self, qtui, tilia, tls, tmp_path
    ):
        open_file(a_file(tmp_path))

        tls.get_timeline(CADENCES).set_component_data(IDS["cadence"], "label", "HC")

        assert tilia.is_file_modified()

    def test_a_file_of_kinds_tilia_knows_asks_nothing(self, qtui, tilia, tls):
        with (
            Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
            Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
            ServeRecording(
                Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)
            ) as asked,
        ):
            commands.execute("file.open", FILES / "golden" / "every-kind.tla")

        assert not asked.called

    def test_saved_before_tilia_saves_through_the_core_it_opens_again(
        self, qtui, tilia, tls, tmp_path, tilia_errors
    ):
        # TiLiA 0.7's format, which TiLiA writes until it saves through the core,
        # has no measure table, measure source or fields, and the core refuses an
        # old file with the first two.
        def change(content):
            content["timelines"][BEATS]["measure_source"] = "tapped"
            content["timelines"][FORM]["metadata"] = {"vocabulary": "form@1"}

        open_file(a_file(tmp_path, change))
        saved = tmp_path / "saved.tla"
        commands.execute("file.save_as", str(saved))

        assert open_file(saved)
        tilia_errors.assert_no_error()
        assert {tl.get_data("name") for tl in tls} >= {"Beats", "Form", "Cadences"}

    @pytest.mark.parametrize("path", GOLDEN, ids=names(GOLDEN))
    def test_keeps_the_ids_of_a_file_in_the_current_format(
        self, qtui, tilia, tls, path
    ):
        doc = tla.read(path)

        open_file(path)

        state = tilia.get_app_state()["timelines"]
        for timeline in doc.timelines.values():
            if timeline.kind in ("audiowave",):
                continue
            assert timeline.id in state
            in_a_measure = expected_timelines(path)[timeline.id]["components"]
            assert set(state[timeline.id]["components"]) == set(in_a_measure)

    def test_keeps_the_document_it_read(self, qtui, tilia, tls):
        path = FILES / "golden" / "every-kind.tla"

        open_file(path)

        file = tilia.file_manager.file
        assert isinstance(file.document, tla.Document)
        assert file.document.fingerprint == tla.fingerprint(path)
        assert file.document.document_id == tla.read(path).document_id

    def test_the_file_s_path_is_the_one_opened(self, qtui, tilia, tls, tmp_path):
        path = a_file(tmp_path)

        open_file(path)

        assert tilia.file_manager.file.file_path == str(path.resolve())
        assert Path(settings.get_recent_files()[0]) == path.resolve()

    def test_media_is_found_through_the_core(self, qtui, tilia, tls, tmp_path):
        (tmp_path / "media").mkdir()
        media = tmp_path / "media" / "example.mp3"
        media.write_bytes(Path(EXAMPLE_MEDIA_PATH).read_bytes())

        def change(content):
            content["media"] = {"path": "media/example.mp3", "length": 9.952}

        path = a_file(tmp_path, change)

        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
            open_file(path)

        assert Path(tilia.player.media_path) == media
        assert tilia.file_manager.file.document.media_path == "media/example.mp3"
        assert not tilia.is_file_modified()

    def test_fields_and_tables_are_the_timelines(self, qtui, tilia, tls, tmp_path):
        def change(content):
            content["timelines"][FORM]["metadata"] = {"vocabulary": "form@1"}
            content["timelines"][BEATS]["measure_source"] = "tapped"

        open_file(a_file(tmp_path, change))

        assert tls.get_timeline(FORM).get_data("fields") == {"vocabulary": "form@1"}
        assert tls.get_timeline(CADENCES).get_data("measure_table") == BEATS
        assert tls.get_timeline(BEATS).get_data("measure_source") == "tapped"
        assert tls.get_timeline(FORM).get_data("measure_table") is None
        # In the state, so that undo gives them back and the digest covers them.
        state = tilia.get_app_state()["timelines"]
        assert state[FORM]["fields"] == {"vocabulary": "form@1"}
        assert state[CADENCES]["measure_table"] == BEATS
        assert state[BEATS]["measure_source"] == "tapped"

    def test_the_new_attributes_come_back_with_an_undo(
        self, qtui, tilia, tls, tmp_path
    ):
        def change(content):
            content["timelines"][FORM]["metadata"] = {"vocabulary": "form@1"}

        open_file(a_file(tmp_path, change))
        form = tls.get_timeline(FORM)
        tls.set_timeline_data(FORM, "fields", {})
        tls.set_timeline_data(FORM, "measure_table", BEATS)
        post(Post.APP_STATE_RECORD, "test")

        commands.execute("edit.undo")

        assert form.get_data("fields") == {"vocabulary": "form@1"}
        assert form.get_data("measure_table") is None

    def test_a_lone_surrogate_in_a_label_opens_and_is_drawn(
        self, qtui, tilia, tls, tmp_path, tilia_errors
    ):
        content = copy.deepcopy(make_broken.base())
        content["timelines"][CADENCES]["components"][IDS["cadence"]]["label"] = "\ud83d"
        path = tmp_path / "surrogate.tla"
        path.write_text(json.dumps(content, indent=2) + "\n", encoding="ascii")

        assert open_file(path)

        assert tls.get_timeline(CADENCES)[0].get_data("label") == "\ud83d"
        draw(qtui.timeline_uis.get_timeline_ui(CADENCES))
        assert not tilia.is_file_modified()


# WP3's cases of components that break a rule (tilia-core's test_tla_rules.py).
LEVEL_0 = hierarchies((FIRST, {"start": 0.0, "end": 2.0, "level": 0}))
BEFORE_0 = hierarchies((FIRST, {"start": -1.0, "end": 2.0, "level": 1}))
CROSSING = hierarchies(
    (FIRST, {"start": 0.0, "end": 2.0, "level": 1}),
    (SECOND, {"start": 1.0, "end": 3.0, "level": 1}),
)
PAST_THE_END = together(with_media_length(10.0), markers((FIRST, {"time": 12.0})))
AT_ONE_TIME = markers((FIRST, {"time": 1.0}), (SECOND, {"time": 1.0}))
BREAKING = {
    "a level of 0": LEVEL_0,
    "a start before 0": BEFORE_0,
    "crossing hierarchies": CROSSING,
    "a marker past the end": PAST_THE_END,
    "two markers at one time": AT_ONE_TIME,
}


class TestComponentsThatBreakARule:
    @pytest.mark.parametrize("change", BREAKING.values(), ids=BREAKING.keys())
    def test_open_and_draw_with_every_component_kept(
        self, qtui, tilia, tls, tilia_errors, tmp_path, change
    ):
        path = a_file(tmp_path, change)
        doc = tla.read(path)
        assert doc.warnings  # the reader keeps them, with a warning

        assert open_file(path)

        tilia_errors.assert_no_error()
        for timeline in doc.timelines.values():
            live = tls.get_timeline(timeline.id)
            if timeline.kind in ("hierarchy", "marker"):
                assert {c.id for c in live} == set(timeline.components)
                for component in live:
                    stored = timeline.components[component.id].attrs
                    for attr in ("time", "start", "end", "level"):
                        if attr in stored:
                            assert component.get_data(attr) == stored[attr]
            draw(qtui.timeline_uis.get_timeline_ui(timeline.id))
        assert not tilia.is_file_modified()

    def test_a_marker_a_second_past_the_media_s_end_keeps_its_time(
        self, qtui, tilia, tls, tmp_path
    ):
        path = a_file(
            tmp_path,
            together(with_media_length(10.0), markers((FIRST, {"time": 11.0}))),
        )

        open_file(path)

        assert tls.get_timeline(CADENCES).get_component(FIRST).get_data("time") == 11.0

    def test_a_mode_loaded_after_a_harmony_leaves_it_as_stored(
        self, qtui, tilia, tls, tmp_path
    ):
        # Created in id order, the mode comes after the harmony it governs: as when
        # restoring a state, its values are final, and creating the mode mustn't
        # change the harmony's applied_to.
        def change(content):
            content["timelines"][HARMONIES] = {
                "kind": "Harmony",
                "name": "Keys",
                "ordinal": 6,
                "components": {
                    FIRST: {"kind": "HARMONY", "time": 4.0, "step": 2, "applied_to": 4},
                    SECOND: {"kind": "MODE", "time": 0.0, "step": 3},
                },
            }

        open_file(a_file(tmp_path, change))

        harmony = tls.get_timeline(HARMONIES).get_component(FIRST)
        assert harmony.get_data("applied_to") == 4
        assert not tilia.is_file_modified()

    def test_two_beats_at_one_time_both_load(self, qtui, tilia, tls, tmp_path):
        def change(content):
            beats = content["timelines"][BEATS]["components"]
            beats[IDS["beat_2"]]["time"] = 0.0

        open_file(a_file(tmp_path, change))

        beats = tls.get_timeline(BEATS)
        assert {beat.id for beat in beats} == {IDS["beat_1"], IDS["beat_2"]}
        assert [beat.get_data("time") for beat in beats] == [0.0, 0.0]
        draw(qtui.timeline_uis.get_timeline_ui(BEATS))


class TestUnknownKinds:
    def test_keep_leaves_them_in_the_document_in_their_place(
        self, qtui, tilia, tls, tmp_path, tilia_errors
    ):
        path = a_file(tmp_path, with_lyrics_in_the_middle)

        with Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)) as asked:
            assert commands.execute("file.open", path)

        assert asked.called
        tilia_errors.assert_no_error()
        assert tls.get_timeline(LYRICS) is None
        document = tilia.file_manager.file.document
        assert document.timelines[LYRICS].ordinal == 3
        assert document.timelines[LYRICS].raw == tla.read(path).timelines[LYRICS].raw
        assert not tilia.is_file_modified()

    def test_the_known_ones_keep_their_order_around_them(
        self, qtui, tilia, tls, tmp_path
    ):
        path = a_file(tmp_path, with_lyrics_in_the_middle)

        open_file(path)

        named = [
            tl.get_data("name") for tl in tls.get_timelines() if tl.get_data("name")
        ]
        assert named == ["Beats", "Form", "Texture", "Score", "Cadences"]

    def test_discard_removes_them_from_the_document_and_marks_the_file_changed(
        self, qtui, tilia, tls, tmp_path, tilia_errors
    ):
        path = a_file(tmp_path, with_lyrics_in_the_middle)

        with Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, True)):
            assert commands.execute("file.open", path)

        tilia_errors.assert_no_error()
        assert tls.get_timeline(LYRICS) is None
        assert LYRICS not in tilia.file_manager.file.document.timelines
        assert tilia.is_file_modified()

    def test_the_question_names_their_kinds(self, qtui, tilia, tls, tmp_path):
        path = a_file(tmp_path, with_lyrics_in_the_middle)

        with ServeRecording(
            Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)
        ) as asked:
            commands.execute("file.open", path)

        assert asked.args == (["Lyrics"],)


class TestAudioWave:
    def test_its_bars_are_no_change(self, qtui, tilia, tls):
        open_file(FILES / "golden" / "every-kind.tla")
        audiowave = next(tl for tl in tls if type(tl).type_name() == "AudioWave")

        audiowave.create_component(
            ComponentKind.AUDIOWAVE, start=0.0, end=1.0, amplitude=0.5
        )

        assert len(audiowave) == 1
        assert not tilia.is_file_modified()
