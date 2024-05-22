from tilia.ui.actions import TiliaAction


class TestActions:
    def test_copy_paste(self, audiowave_tlui, actions):
        aw1, ui1 = audiowave_tlui.create_amplitudebar(0, 1, 1)
        aw2, ui2 = audiowave_tlui.create_amplitudebar(1, 2, 0)

        audiowave_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        audiowave_tlui.deselect_element(ui1)

        audiowave_tlui.select_element(ui2)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert aw2.get_data('start') != 0
        
    def test_delete(self, audiowave_tlui, actions):
        _, ui1 = audiowave_tlui.create_amplitudebar(0, 1, 1)

        audiowave_tlui.select_element(ui1)
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(audiowave_tlui) == 1
