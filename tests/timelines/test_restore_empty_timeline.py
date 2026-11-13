"""An undo brings back a timeline that had no components without any.

Opening a file, by contrast, still fills in what a new timeline starts with.
"""

from tests.utils import undoable
from tilia.ui import commands


def test_undo_deleting_a_pdf_timeline_with_no_markers(pdf_tlui, tls):
    timeline_id = pdf_tlui.timeline.id
    assert len(pdf_tlui.timeline) == 0

    with undoable():
        commands.execute("timeline.delete", pdf_tlui, confirm=False)
    commands.execute("edit.undo")

    assert len(tls.get_timeline(timeline_id)) == 0


def test_undo_deleting_a_hierarchy_timeline_with_no_units(hierarchy_tlui, tls):
    timeline_id = hierarchy_tlui.timeline.id
    assert len(hierarchy_tlui.timeline) == 0

    with undoable():
        commands.execute("timeline.delete", hierarchy_tlui, confirm=False)
    commands.execute("edit.undo")

    assert len(tls.get_timeline(timeline_id)) == 0


def test_loading_a_pdf_timeline_with_no_markers_fills_in_page_one(pdf_tlui, tls):
    # Timelines.deserialize_timelines is what App.on_file_load calls.
    timeline_id = pdf_tlui.timeline.id
    data = {timeline_id: pdf_tlui.timeline.get_state()}
    tls.clear()

    tls.deserialize_timelines(data)

    markers = list(tls.get_timeline(timeline_id))
    assert [(m.get_data("time"), m.get_data("page_number")) for m in markers] == [
        (0, 1)
    ]
