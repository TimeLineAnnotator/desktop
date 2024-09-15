from tilia.ui.actions import TiliaAction


class TestActions:
    def test_copy_paste(self, audiowave_tlui, actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)
        audiowave_tlui.create_amplitudebar(1, 2, 0)

        audiowave_tlui.select_element(audiowave_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        audiowave_tlui.deselect_element(0)

        audiowave_tlui.select_element(audiowave_tlui[1])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert audiowave_tlui[1].get_data('start') != 0
        
    def test_delete(self, audiowave_tlui, actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)

        audiowave_tlui.select_element(audiowave_tlui[0])
        actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(audiowave_tlui) == 1
