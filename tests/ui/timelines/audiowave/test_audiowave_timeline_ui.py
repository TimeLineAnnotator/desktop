from tilia.requests import post, Post


def test_undo_redo(audiowave_tlui, marker_tlui, user_actions):

    post(Post.APP_RECORD_STATE, "test state")

    # using marker tl to trigger an actions that can be undone
    user_actions.trigger("marker_add")

    post(Post.EDIT_UNDO)
    assert len(marker_tlui) == 0

    post(Post.EDIT_REDO)
    assert len(marker_tlui) == 1


class TestActions:
    def test_copy_paste(self, audiowave_tlui, user_actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)
        audiowave_tlui.create_amplitudebar(1, 2, 0)

        audiowave_tlui.select_element(audiowave_tlui[0])
        user_actions.trigger("timeline_element_copy")
        audiowave_tlui.deselect_element(0)

        audiowave_tlui.select_element(audiowave_tlui[1])
        user_actions.trigger("timeline_element_paste")

        assert audiowave_tlui[1].get_data("start") != 0

    def test_delete(self, audiowave_tlui, user_actions):
        audiowave_tlui.create_amplitudebar(0, 1, 1)

        audiowave_tlui.select_element(audiowave_tlui[0])
        user_actions.trigger("timeline_element_delete")

        assert len(audiowave_tlui) == 1
