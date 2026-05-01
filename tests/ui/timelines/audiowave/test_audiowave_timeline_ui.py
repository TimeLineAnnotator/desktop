from tilia.ui import commands


def test_undo_redo(audiowave_tlui, marker_tlui):
    # using marker tl to trigger an action that can be undone;
    # audiowave_tlui is just an inactive participant.
    commands.execute("timeline.marker.add")

    commands.execute("edit.undo")
    assert len(marker_tlui) == 0

    commands.execute("edit.redo")
    assert len(marker_tlui) == 1
