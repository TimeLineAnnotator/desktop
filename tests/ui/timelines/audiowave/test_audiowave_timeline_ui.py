from tilia.requests import post, Post
from tilia.ui.actions import TiliaAction


def test_undo_redo(audiowave_tlui, marker_tlui, user_actions):
    audiowave_state_0 = audiowave_tlui.timeline.get_state()

    post(Post.APP_RECORD_STATE, "test state")

    # using marker tl to trigger an actions that can be undone,
    # as audiowave timeline has no undoable actions
    user_actions.trigger(TiliaAction.MARKER_ADD)
    marker_state_0 = marker_tlui.timeline.get_state()

    post(Post.EDIT_UNDO)
    assert len(marker_tlui) == 0
    assert marker_tlui.timeline.get_state() != marker_state_0
    assert audiowave_tlui.timeline.get_state() == audiowave_state_0

    post(Post.EDIT_REDO)
    assert len(marker_tlui) == 1
    assert marker_tlui.timeline.get_state() == marker_state_0
    assert audiowave_tlui.timeline.get_state() == audiowave_state_0


class TestActions:
    def test_copy_paste(self, audiowave_tlui, user_actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)
        audiowave_tlui.create_amplitudebar(1, 2, 0)

        audiowave_tlui.select_element(audiowave_tlui[0])
        user_actions.trigger(TiliaAction.TIMELINE_ELEMENT_COPY)
        audiowave_tlui.deselect_element(0)

        audiowave_tlui.select_element(audiowave_tlui[1])
        user_actions.trigger(TiliaAction.TIMELINE_ELEMENT_PASTE)

        assert audiowave_tlui[1].get_data("start") != 0

    def test_delete(self, audiowave_tlui, user_actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)

        audiowave_tlui.select_element(audiowave_tlui[0])
        user_actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)

        assert len(audiowave_tlui) == 1
