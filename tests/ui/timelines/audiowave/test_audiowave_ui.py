from PySide6.QtCore import Qt

from tests.mock import PatchPost
from tilia.requests import Post


class TestWaveformElement:
    def test_create_via_set_peaks(self, audiowave_tlui):
        audiowave_tlui.set_peaks_for_test()
        assert len(audiowave_tlui) == 1


class TestClickToSeek:
    def test_click_seeks_to_clicked_time(self, audiowave_tlui, waveform_element):
        with PatchPost(
            "tilia.ui.timelines.audiowave.timeline", Post.PLAYER_SEEK_IF_NOT_PLAYING
        ) as mock:
            audiowave_tlui.on_left_click(
                waveform_element.body,
                Qt.KeyboardModifier.NoModifier,
                False,
                100,
                10,
            )
        assert mock.called

    def test_click_outside_waveform_is_noop(self, audiowave_tlui, waveform_element):
        with PatchPost(
            "tilia.ui.timelines.audiowave.timeline", Post.PLAYER_SEEK_IF_NOT_PLAYING
        ) as mock:
            audiowave_tlui.on_left_click(
                None,
                Qt.KeyboardModifier.NoModifier,
                False,
                100,
                10,
            )
        mock.assert_not_called()
