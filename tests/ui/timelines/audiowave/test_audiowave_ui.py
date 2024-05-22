from unittest.mock import Mock

from tests.mock import PatchPost
from tilia.requests import Post

class TestAudioWaveUI:
    def test_create(self, audiowave_tlui):
        _, aui = audiowave_tlui.create_audiowave(0, 1, 1)
        assert aui

class TestDoubleClick:
    def test_amplitudebar_seek(self, audiowave_tlui):
        audiowave_tlui.create_audiowave(10, 15, 1)
        with PatchPost(
            "tilia.ui.timelines.audiowave.element", Post.PLAYER_SEEK
        ) as mock:
            audiowave_tlui[0].on_double_left_click(None)

        mock.assert_called_with(Post.PLAYER_SEEK, 10)

    def test_does_not_trigger_drag(self, audiowave_tlui):
        audiowave_tlui.create_audiowave(0, 1, 1)
        mock = Mock()
        audiowave_tlui[0].setup_drag = mock
        audiowave_tlui[0].on_double_left_click(None)

        mock.assert_not_called()
