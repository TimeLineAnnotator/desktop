import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest
import soundfile
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer

from tests.constants import (
    EXAMPLE_MEDIA_PATH,
    EXAMPLE_MUSICXML_PATH,
    EXAMPLE_QUARTER_TONES_MUSICXML_PATH,
)
from tests.mock import PatchPost, Serve, patch_yes_or_no_dialog
from tests.utils import save_and_reopen, save_tilia_to_tmp_path, wait_until
from tilia.media import audition, synth
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

    def test_stops_at_the_end_of_a_reopened_file(self, tilia, score, tmp_path):
        save_and_reopen(tmp_path)
        play()
        commands.execute("media.seek", get(Get.MEDIA_DURATION) - 0.2)

        assert wait_until(lambda: not tilia.player.is_playing)
        assert tilia.player.current_time == 0

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

        assert_tie_is_one_note(notes)

    def test_ties_are_kept_by_files(self, tluis, tilia_state, tmp_path):
        tilia_state.duration = 0
        path = tmp_path / "tied.musicxml"
        path.write_text(TIED_SCORE)
        import_score(str(path))

        save_and_reopen(tmp_path)

        assert_tie_is_one_note(synth.get_score_notes())
        assert not get(Get.IS_FILE_MODIFIED)

    def test_file_without_ties_opens_with_notes_struck(
        self, tluis, tilia_state, tmp_path
    ):
        tilia_state.duration = 0
        path = tmp_path / "tied.musicxml"
        path.write_text(TIED_SCORE)
        import_score(str(path))
        file_path = Path(save_tilia_to_tmp_path(tmp_path, "old"))
        data = json.loads(file_path.read_text())
        for timeline in data["timelines"].values():
            for component in timeline["components"].values():
                component.pop("tie", None)
        file_path.write_text(json.dumps(data))
        post(Post.APP_CLEAR)

        commands.execute("file.open", path=file_path)

        assert len(synth.get_score_notes()) == 3
        assert not get(Get.IS_FILE_MODIFIED)


def assert_tie_is_one_note(notes):
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


class TestTones:
    @pytest.mark.parametrize(
        "pitch, frequency", [(69, 440), (69.5, 452.9), (60, 261.6)]
    )
    def test_exact_pitch(self, pitch, frequency):
        samples = np.frombuffer(
            audition.render_tones([pitch], audition.get_mono_format()), dtype=np.int16
        )

        spectrum = np.abs(np.fft.rfft(samples))
        peak = np.fft.rfftfreq(len(samples), 1 / synth.SAMPLE_RATE)[spectrum.argmax()]

        assert peak == pytest.approx(frequency, abs=1.5)

    def test_chord_does_not_clip(self):
        samples = np.frombuffer(
            audition.render_tones([60, 64, 67, 71, 74, 77], audition.get_mono_format()),
            dtype=np.int16,
        )
        assert np.abs(samples).max() < np.iinfo(np.int16).max

    @pytest.mark.parametrize(
        "sample_format, dtype, scale",
        [
            (QAudioFormat.SampleFormat.Int16, np.int16, 2**15),
            (QAudioFormat.SampleFormat.Int32, np.int32, 2**31),
            (QAudioFormat.SampleFormat.Float, np.float32, 1),
        ],
    )
    def test_exact_pitch_in_other_formats(self, sample_format, dtype, scale):
        audio_format = QAudioFormat()
        audio_format.setSampleRate(48000)
        audio_format.setChannelCount(2)
        audio_format.setSampleFormat(sample_format)

        samples = np.frombuffer(audition.render_tones([69], audio_format), dtype=dtype)

        left, right = samples[::2], samples[1::2]
        assert np.array_equal(left, right)
        assert 0.1 < np.abs(left).max() / scale <= 1
        spectrum = np.abs(np.fft.rfft(left))
        assert np.fft.rfftfreq(len(left), 1 / 48000)[spectrum.argmax()] == (
            pytest.approx(440, abs=1.5)
        )

    def test_unsigned_samples_center_on_the_middle(self):
        audio_format = audition.get_mono_format()
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.UInt8)

        samples = np.frombuffer(
            audition.render_tones([69], audio_format), dtype=np.uint8
        )

        assert samples.mean() == pytest.approx(127.5, abs=1)

    @pytest.mark.parametrize(
        "is_mono_supported, preferred_channels, channels",
        [(True, 2, 1), (False, 2, 2), (False, 0, 1)],
    )
    def test_format_follows_the_output(
        self, is_mono_supported, preferred_channels, channels
    ):
        preferred = QAudioFormat()
        if preferred_channels:
            preferred.setSampleRate(48000)
            preferred.setChannelCount(preferred_channels)
            preferred.setSampleFormat(QAudioFormat.SampleFormat.Float)
        device = Mock()
        device.isFormatSupported.return_value = is_mono_supported
        device.preferredFormat.return_value = preferred

        with patch.object(audition.QMediaDevices, "defaultAudioOutput") as output:
            output.return_value = device
            assert audition.get_output_format().channelCount() == channels


class TestAuditionCommand:
    PITCHES = [60.0, 64.5]

    def test_heard(self, tilia, auditioned):
        commands.execute("media.audition", self.PITCHES)
        assert auditioned == [self.PITCHES]

    def test_nothing_to_hear(self, tilia, auditioned):
        commands.execute("media.audition", [])
        assert not auditioned

    def test_silent_while_playing(self, tilia, score, auditioned):
        play()
        commands.execute("media.audition", self.PITCHES)
        pause()
        assert not auditioned

    def test_heard_again_after_pausing(self, tilia, score, auditioned):
        play()
        pause()
        commands.execute("media.audition", self.PITCHES)
        assert auditioned == [self.PITCHES]

    def test_silent_when_muted(self, tilia, auditioned):
        commands.execute("media.volume.mute", True)
        commands.execute("media.audition", self.PITCHES)
        commands.execute("media.volume.mute", False)
        assert not auditioned

    def test_silent_when_turned_off(self, tilia, auditioned):
        commands.execute("media.audition.toggle")
        commands.execute("media.audition", self.PITCHES)
        assert not auditioned

    def test_turned_on_again(self, tilia, auditioned):
        commands.execute("media.audition.toggle")
        commands.execute("media.audition.toggle")
        commands.execute("media.audition", self.PITCHES)
        assert auditioned == [self.PITCHES]

    def test_does_not_move_the_player(self, tilia, tilia_state, score):
        commands.execute("media.seek", 1.0)
        commands.execute("media.audition", self.PITCHES)
        assert tilia_state.current_time == 1.0
        assert tilia.player.is_playing is False
