from unittest.mock import patch
from PyQt6.QtGui import QColor

from tests.mock import PatchGet, Serve
from tilia.requests import Post, Get, post
from tilia.timelines.audiowave.components import AudioWave
from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.audiowave import AudioWaveUI


class TestActions:
    def test_copy_paste(self, audiowave_tlui, actions):
        aw1, ui1 = audiowave_tlui.create_audiowave(0, 1, 1)
        aw2, ui2 = audiowave_tlui.create_audiowave(1, 2, 0)

        audiowave_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        audiowave_tlui.deselect_element(ui1)

        audiowave_tlui.select_element(ui2)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert aw2.get_data('start') != 0
        
    def test_delete(self, audiowave_tlui, actions):
        aw1, ui1 = audiowave_tlui.create_audiowave(0, 1, 1)

        audiowave_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(audiowave_tlui) == 1
