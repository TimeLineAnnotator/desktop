import numpy as np
import pytest
import soundfile

from tests.constants import EXAMPLE_MUSICXML_PATH, EXAMPLE_QUARTER_TONES_MUSICXML_PATH
from tests.mock import Serve
from tests.utils import (
    get_command_action,
    get_command_names,
    get_main_window_menu,
    get_submenu,
    wait_until,
)
from tilia.media import synth
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands


def import_with_beats(path: str = EXAMPLE_MUSICXML_PATH):
    assert commands.execute("timelines.import.score_with_beats", path=path)
    return get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)


def note_times(score_tlui):
    return sorted(
        (c.start, c.end)
        for c in score_tlui.timeline.component_manager.get_components()
        if c.KIND == ComponentKind.NOTE
    )


class TestSynthesizeAudio:
    def test_writes_audio_as_long_as_the_media(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        import_with_beats()
        duration = get(Get.MEDIA_DURATION)
        path = tmp_path / "score.wav"

        assert commands.execute("timeline.score.synthesize_audio", path=str(path))

        audio, rate = soundfile.read(path)
        assert rate == synth.SAMPLE_RATE
        assert len(audio) / rate == pytest.approx(duration, abs=1e-3)
        assert np.abs(audio).max() > 0.5

    def test_loads_audio_as_media_without_moving_notes(
        self, tluis, tilia_state, tmp_path
    ):
        tilia_state.duration = 0
        score_tlui = import_with_beats()
        before = note_times(score_tlui)
        path = tmp_path / "score.wav"

        commands.execute("timeline.score.synthesize_audio", path=str(path))

        assert wait_until(lambda: get(Get.MEDIA_PATH) == str(path))
        assert note_times(score_tlui) == before

    def test_asks_where_to_save(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        import_with_beats()
        path = tmp_path / "chosen"

        with Serve(Get.FROM_USER_SAVE_PATH, (True, str(path))):
            commands.execute("timeline.score.synthesize_audio")

        assert (tmp_path / "chosen.wav").exists()

    def test_cancelled_save_writes_nothing(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        import_with_beats()

        with Serve(Get.FROM_USER_SAVE_PATH, (False, "")):
            assert not commands.execute("timeline.score.synthesize_audio")

        assert not list(tmp_path.iterdir())

    def test_undo_unloads_the_audio(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        import_with_beats()
        path = tmp_path / "score.wav"

        commands.execute("timeline.score.synthesize_audio", path=str(path))
        assert wait_until(lambda: get(Get.MEDIA_PATH) == str(path))
        commands.execute("edit.undo")

        assert wait_until(lambda: get(Get.MEDIA_PATH) != str(path))

    def test_quarter_tones_sound_at_their_pitch(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        score_tlui = import_with_beats(EXAMPLE_QUARTER_TONES_MUSICXML_PATH)
        notes = synth.score_notes(
            c
            for c in score_tlui.timeline.component_manager.get_components()
            if c.KIND == ComponentKind.NOTE
        )

        assert any(note.pitch % 1 == 0.5 for note in notes)

    def test_without_score_timeline_shows_error(self, tluis, tilia_errors, tmp_path):
        path = tmp_path / "x.wav"

        assert not commands.execute("timeline.score.synthesize_audio", path=str(path))

        tilia_errors.assert_error()
        assert not path.exists()

    def test_plays_the_given_score_timeline(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        import_with_beats()
        commands.execute("timelines.add.score", name="Empty")
        empty = next(t for t in tluis if t.get_data("name") == "Empty")

        assert not commands.execute(
            "timeline.score.synthesize_audio", empty, path=str(tmp_path / "x.wav")
        )


class TestTies:
    def test_tied_notes_sound_as_one(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        path = tmp_path / "tied.musicxml"
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0">'
            '<part-list><score-part id="P1"><part-name>P</part-name></score-part>'
            '</part-list><part id="P1">'
            '<measure number="1"><attributes><divisions>1</divisions>'
            "<time><beats>2</beats><beat-type>4</beat-type></time></attributes>"
            "<note><rest/><duration>1</duration></note>"
            "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
            '<tie type="start"/></note></measure>'
            '<measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>1</duration><tie type="stop"/></note>'
            "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
            "</note></measure></part></score-partwise>"
        )
        score_tlui = import_with_beats(str(path))

        notes = synth.score_notes(
            c
            for c in score_tlui.timeline.component_manager.get_components()
            if c.KIND == ComponentKind.NOTE
        )

        # The tied pair is one note; the last C is struck again.
        assert len(notes) == 2
        assert notes[0].end == pytest.approx(notes[1].start)
        assert notes[0].pitch == notes[1].pitch == 60


class TestMenus:
    def test_in_score_timeline_context_menu(self, tluis, tilia_state):
        tilia_state.duration = 0
        score_tlui = import_with_beats()

        menu = score_tlui.CONTEXT_MENU_CLASS(score_tlui, 0, 0)

        assert "timeline.score.synthesize_audio" in get_command_names(menu)

    def test_context_menu_synthesizes_audio(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        score_tlui = import_with_beats()
        menu = score_tlui.CONTEXT_MENU_CLASS(score_tlui, 0, 0)
        path = tmp_path / "score.wav"

        with Serve(Get.FROM_USER_SAVE_PATH, (True, str(path))):
            get_command_action(menu, "timeline.score.synthesize_audio").trigger()

        assert wait_until(lambda: get(Get.MEDIA_PATH) == str(path))

    def test_in_load_media_menu(self, qtui):
        load_media = get_submenu(get_main_window_menu(qtui, "File"), "Load media")

        assert "timeline.score.synthesize_audio" in get_command_names(load_media)
