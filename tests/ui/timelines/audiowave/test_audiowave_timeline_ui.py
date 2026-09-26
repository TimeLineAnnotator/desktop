from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QInputDialog

import tilia.errors
from tests.mock import Serve
from tests.utils import (
    EXAMPLE_VIDEO_FILENAME,
    get_command_action,
    load_local_media,
    load_youtube_media,
    undoable,
)
from tilia.requests import Get
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.ui import commands


def test_undo_redo(audiowave_tlui, marker_tlui):

    # using marker tl to trigger an actions that can be undone
    commands.execute("timeline.marker.add")

    commands.execute("edit.undo")
    assert len(marker_tlui) == 0

    commands.execute("edit.redo")
    assert len(marker_tlui) == 1


class TestActions:
    def test_copy_paste(self, audiowave_tlui):
        audiowave_tlui.create_amplitudebar(0, 1, 1)
        audiowave_tlui.create_amplitudebar(1, 2, 0)

        audiowave_tlui.select_element(audiowave_tlui[0])
        commands.execute("timeline.component.copy")
        audiowave_tlui.deselect_element(0)

        audiowave_tlui.select_element(audiowave_tlui[1])
        commands.execute("timeline.component.paste")

        assert audiowave_tlui[1].get_data("start") != 0

    def test_delete(self, audiowave_tlui):
        audiowave_tlui.create_amplitudebar(0, 1, 1)

        audiowave_tlui.select_element(audiowave_tlui[0])
        commands.execute("timeline.component.delete")

        assert len(audiowave_tlui) == 1


class TestTimelineHeight:
    """Increase/decrease the audiowave timeline's height via its
    context menu (audiowave uses the base TimelineUIContextMenu unchanged,
    so "timeline.set_height" is present -- see TestTimelineUIContextMenu in
    the beat/marker/pdf/harmony test files, where it is absent)."""

    @staticmethod
    def get_context_menu(audiowave_tlui):
        return audiowave_tlui.CONTEXT_MENU_CLASS(audiowave_tlui, 0, 0)

    def _set_height(self, audiowave_tlui, value):
        context_menu = self.get_context_menu(audiowave_tlui)
        action = get_command_action(context_menu, "timeline.set_height")
        with Serve(Get.FROM_USER_INT, (True, value)):
            action.trigger()

    def test_increase(self, audiowave_tlui, tluis):
        original = audiowave_tlui.get_data("height")

        with undoable():
            self._set_height(audiowave_tlui, original + 50)

        assert audiowave_tlui.get_data("height") == original + 50

    def test_increase_with_several_timelines_moves_ones_below_down(
        self, audiowave_tlui, tluis
    ):
        # The audiowave_tlui fixture creates the timeline with no media
        # loaded, so its one real refresh() (before tests stub it out)
        # hides it as an invalid file; force it visible so it contributes
        # its height to the layout, like it would with media loaded.
        commands.execute("timeline.set_is_visible", audiowave_tlui, True)
        commands.execute("timelines.add.marker", name="")
        marker_tlui = tluis[1]
        y_before = marker_tlui.view.y()
        original = audiowave_tlui.get_data("height")

        self._set_height(audiowave_tlui, original + 50)

        assert marker_tlui.view.y() == pytest.approx(y_before + 50)

    def test_decrease_with_several_timelines_moves_ones_below_up(
        self, audiowave_tlui, tluis
    ):
        commands.execute("timeline.set_is_visible", audiowave_tlui, True)
        commands.execute("timelines.add.marker", name="")
        marker_tlui = tluis[1]
        original = audiowave_tlui.get_data("height")
        y_before = marker_tlui.view.y()

        self._set_height(audiowave_tlui, original - 20)

        assert marker_tlui.view.y() == pytest.approx(y_before - 20)

    def test_minimum_height_is_ten(self, audiowave_tlui, tluis):
        context_menu = self.get_context_menu(audiowave_tlui)
        action = get_command_action(context_menu, "timeline.set_height")

        with patch.object(
            QInputDialog, "getInt", return_value=(20, True)
        ) as mock_get_int:
            action.trigger()

        assert mock_get_int.call_args.kwargs["minValue"] == 10


class TestMediaLoadInteraction:
    """Adding an audiowave timeline while media is already loaded, or
    loading new media while one exists."""

    def test_add_while_youtube_loaded_shows_error(self, qtui, tluis, tilia_errors):
        load_youtube_media()

        commands.execute("timelines.add.audiowave", name="")

        tilia_errors.assert_error()

    def test_loading_video_while_media_loaded_refreshes_waveform(
        self, qtui, tluis, resources
    ):
        load_local_media((resources / "example.mp4").resolve())
        commands.execute("timelines.add.audiowave", name="")

        with patch.object(AudioWaveTimeline, "refresh", autospec=True) as mock_refresh:
            load_local_media((resources / "example2.mp4").resolve())

        mock_refresh.assert_called()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Creating/refreshing an AudioWave timeline over a loaded"
            " audio file raises TypeError. In"
            " AudioWaveTimeline._get_normalised_amplitudes,"
            " `self.audio.blocks(self.audio.frames // divisions)` -- `divisions`"
            " is `min(PLAYBACK_AREA_WIDTH,"
            " max_divisions, frames)`, and PLAYBACK_AREA_WIDTH is a float, so when"
            " it is the smallest of the three the `//` result stays a float and"
            " soundfile.blocks() rejects it as a blocksize."
        ),
    )
    def test_loading_audio_while_media_loaded_refreshes_waveform(
        self, qtui, tluis, resources
    ):
        load_local_media((resources / "example.wav").resolve())
        commands.execute("timelines.add.audiowave", name="")

        with patch.object(AudioWaveTimeline, "refresh", autospec=True) as mock_refresh:
            load_local_media((resources / "example.mp3").resolve())

        mock_refresh.assert_called()


class TestAddTimeline:
    def test_add_with_local_video_loaded(self, tluis, tls, tilia_errors, resources):
        """Adding an AudioWave timeline while a local video is loaded
        should warn (soundfile can't read the video container) and leave
        the timeline hidden, instead of crashing. Extracting audio from the
        video file to display it anyway is out of scope."""
        load_local_media((resources / EXAMPLE_VIDEO_FILENAME).resolve())

        commands.execute("timelines.add.audiowave", name="AudioWave")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_title(tilia.errors.AUDIOWAVE_INVALID_FILE.title)

        tl = tls.get_timeline_by_type(AudioWaveTimeline)
        assert tl is not None
        assert tl.get_data("is_visible") is False
