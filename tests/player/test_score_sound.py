import io

import numpy as np
import pytest
import soundfile
from PySide6.QtMultimedia import QMediaPlayer

from tests.constants import (
    EXAMPLE_MEDIA_PATH,
    EXAMPLE_MUSICXML_PATH,
    EXAMPLE_QUARTER_TONES_MUSICXML_PATH,
)
from tests.mock import PatchPost, Serve, patch_yes_or_no_dialog
from tests.utils import save_and_reopen, wait_until
from tilia.media import synth
from tilia.requests import Get, Post, get, post
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui import commands


def import_score(path: str = EXAMPLE_MUSICXML_PATH):
    assert commands.execute("timelines.import.score_with_beats", path=path)
    return get(Get.TIMELINE_UI_BY_ATTR, "timeline_class", ScoreTimeline)


def import_second_score():
    assert commands.execute(
        "timelines.import.score_with_beats", path=EXAMPLE_QUARTER_TONES_MUSICXML_PATH
    )


def play():
    commands.execute("media.toggle_play", True)


def pause():
    commands.execute("media.toggle_play", False)


def load_recording():
    # Neither scale nor crop the score to it.
    with Serve(Get.FROM_USER_YES_OR_NO, False):
        post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH, scale_timelines="no")


@pytest.fixture
def score(tluis, tilia_state):
    tilia_state.duration = 0
    return import_score()


@pytest.fixture
def renders(monkeypatch):
    """How many times the sound has been rendered."""
    calls = []
    render = synth.render

    def spy(*args, **kwargs):
        calls.append(args)
        return render(*args, **kwargs)

    monkeypatch.setattr(synth, "render", spy)
    return calls


class TestControls:
    def test_enabled_by_importing_a_score(self, qtui, tluis, tilia_state):
        tilia_state.duration = 0
        import_score()
        assert qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_disabled_without_a_score(self, qtui, tluis):
        assert not qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_disabled_by_a_score_with_no_notes(self, qtui, tluis, tilia_state):
        tilia_state.duration = 10
        commands.execute("timelines.add.score", name="Empty")
        assert not qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_disabled_by_deleting_the_score(self, qtui, tluis, tilia_state, score):
        commands.execute("timeline.delete", score, confirm=False)
        assert not qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_disabled_by_clearing_the_score(self, qtui, tluis, tilia_state, score):
        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", score)
        assert not qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_enabled_after_reopening(self, qtui, tluis, score, tmp_path):
        save_and_reopen(tmp_path)
        assert qtui.player_toolbar.play_toggle_action.isEnabled()

    def test_not_enabled_again_by_a_score_change(self, tluis, score):
        with PatchPost("tilia.media.player.base", Post.PLAYER_UPDATE_CONTROLS) as mock:
            post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, score.id)
        mock.assert_not_called()


class TestPlay:
    def test_plays_without_a_media_file(self, tilia, score):
        play()

        assert tilia.player.is_playing
        assert tilia.player.player.playbackState() == (
            QMediaPlayer.PlaybackState.PlayingState
        )
        pause()

    def test_lasts_as_long_as_the_file(self, tilia, score):
        play()
        pause()

        assert tilia.player.duration == pytest.approx(get(Get.MEDIA_DURATION), abs=1e-2)

    def test_is_not_media(self, tilia, score, tmp_path):
        with PatchPost("tilia.media.player.base", Post.PLAYER_URL_CHANGED) as mock:
            play()
            pause()

        mock.assert_not_called()
        assert get(Get.MEDIA_PATH) == ""
        assert get(Get.APP_STATE)["media_path"] == ""

    def test_keeps_the_duration_and_the_notes(self, tilia, score):
        duration = get(Get.MEDIA_DURATION)
        before = synth.get_score_notes()
        with PatchPost(
            "tilia.media.player.base", Post.PLAYER_DURATION_AVAILABLE
        ) as mock:
            play()
            pause()

        mock.assert_not_called()
        assert get(Get.MEDIA_DURATION) == duration
        assert synth.get_score_notes() == before

    def test_starts_where_the_player_was_seeked_to(self, tilia, score):
        commands.execute("media.seek", 1.5)
        play()
        pause()

        assert tilia.player.player.position() >= 1400

    def test_seeks_after_playing(self, tilia, score):
        play()
        pause()
        commands.execute("media.seek", 1.5)

        assert tilia.player.player.position() == pytest.approx(1500, abs=100)

    def test_reaches_the_end(self, tilia, score):
        play()
        commands.execute("media.seek", tilia.player.duration)
        assert wait_until(lambda: not tilia.player.is_playing)

    def test_file_modified_state_is_unchanged(self, score):
        modified = get(Get.IS_FILE_MODIFIED)
        play()
        pause()

        assert get(Get.IS_FILE_MODIFIED) == modified


class TestRender:
    def test_not_before_playing(self, tluis, tilia_state, renders):
        tilia_state.duration = 0
        import_score()
        assert not renders

    def test_once(self, score, renders):
        play()
        pause()
        play()
        pause()
        assert len(renders) == 1

    def test_again_when_the_notes_change(self, tilia, tluis, renders, score):
        play()
        pause()
        import_second_score()
        play()
        pause()
        assert len(renders) == 2

    def test_not_with_a_recording(self, tilia, score, renders):
        load_recording()
        assert wait_until(lambda: get(Get.MEDIA_PATH))
        play()
        pause()
        assert not renders


class TestRecordingTakesPriority:
    def test_replaces_the_sound(self, tilia, score):
        play()
        pause()
        load_recording()

        assert wait_until(lambda: get(Get.MEDIA_PATH) == EXAMPLE_MEDIA_PATH)
        assert tilia.player.player.source().isLocalFile()

    def test_sound_returns_when_the_recording_goes(self, qtui, tilia, score):
        load_recording()
        assert wait_until(lambda: get(Get.MEDIA_PATH))
        commands.execute("edit.undo")

        assert wait_until(lambda: not get(Get.MEDIA_PATH))
        assert qtui.player_toolbar.play_toggle_action.isEnabled()
        play()
        assert tilia.player.is_playing
        pause()

    def test_undoing_the_first_load_asks_nothing(self, qtui, tilia, score):
        notes = synth.get_score_notes()
        load_recording()
        assert wait_until(lambda: get(Get.MEDIA_PATH))
        commands.execute("edit.undo")

        assert wait_until(lambda: not get(Get.MEDIA_PATH))
        assert synth.get_score_notes() == notes


class TestExportAudio:
    def test_needs_a_file(self, tilia_errors, score):
        commands.execute("media.export_audio", "x", 0.0, 1.0)
        tilia_errors.assert_error()


class TestSynth:
    def test_to_wav(self):
        samples = np.full(100, 0.5, dtype=np.float32)

        audio, rate = soundfile.read(io.BytesIO(synth.to_wav(samples)))

        assert rate == synth.SAMPLE_RATE
        assert len(audio) == 100
        assert audio[0] == pytest.approx(0.5, abs=1e-3)

    def test_quarter_tones_sound_at_their_pitch(self, tluis, tilia_state):
        tilia_state.duration = 0
        import_score(EXAMPLE_QUARTER_TONES_MUSICXML_PATH)

        assert any(note.pitch % 1 == 0.5 for note in synth.get_score_notes())

    def test_all_scores_sound_together(self, score):
        notes = synth.get_score_notes()
        import_second_score()
        assert len(synth.get_score_notes()) > len(notes)

    def test_tied_notes_sound_as_one(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        path = tmp_path / "tied.musicxml"
        path.write_text(TIED_SCORE)
        import_score(str(path))

        notes = synth.get_score_notes()

        # The tied pair is one note; the last C is struck again.
        assert len(notes) == 2
        assert notes[0].end == pytest.approx(notes[1].start)
        assert notes[0].pitch == notes[1].pitch == 60


TIED_SCORE = (
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
