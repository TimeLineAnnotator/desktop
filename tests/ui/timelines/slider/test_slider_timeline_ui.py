from tilia.requests import post, Post


def test_undo_redo(slider_tlui, marker_tlui, user_actions):

    post(Post.APP_RECORD_STATE, "test state")

    # using marker tl to trigger an actions that can be undone
    user_actions.execute("marker_add")

    post(Post.EDIT_UNDO)
    assert len(marker_tlui) == 0

    post(Post.EDIT_REDO)
    assert len(marker_tlui) == 1
