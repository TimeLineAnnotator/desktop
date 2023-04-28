import time
from typing import TYPE_CHECKING

from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia._tilia import TiLiA

from tilia import events
from tilia.events import Event

from tilia.timelines.collection import TimelineCollection
from tilia.timelines.timeline_kinds import TimelineKind
import logging

from tilia.ui.timelines.collection import TimelineUICollection

logger = logging.getLogger(__name__)

"""
Some useful snippets:

### select first element from first timeline
tlui = TIMELINEUI_COLLECTION._display_order[1]
elements = list(tlui.element_manager._elements)
ordered_elements = sorted(elements, key=lambda c: (c.level, c.start_x))
# ordered_elements = sorted(elements, key=lambda c: c.time)
tlui.select_element(ordered_elements[0])


### zoom and scroll to time
time = 10.0
width = 4000
TLUIC.timeline_width = width
TLUIC.scroll_to_x(TLUIC.get_x_by_time(time))


### create hierarchy on first timeline
events.post(Event.REQUEST_ADD_TIMELINE, kind=TimelineKind.HIERARCHY_TIMELINE, name='HRC1')

tlui = TIMELINEUI_COLLECTION._display_order[1]
elements = list(tlui.element_manager._elements)
ordered_elements = sorted(elements, key=lambda c: (c.level, c.start_x))
# ordered_elements = sorted(elements, key=lambda c: c.time)
tlui.select_element(ordered_elements[0])

events.post(Event.KEY_PRESS_DELETE)

tlui.timeline.create_timeline_component(
    kind=ComponentKind.HIERARCHY,
    label='first',
    start=0.2,
    pre_start=0.1,
    end=0.4,
    level=1,
)
"""

# noinspection PyProtectedMember
def func(tilia) -> None:
    """
    This function will be called right before the ui mainloop on every startup.
    Use this function to run code for development purposes.
    Changes to this file should bot be commited.
    """

    # setup convenience constants
    TIMELINE_COLLECTION = TLC = tilia._timeline_collection
    TIMELINEUI_COLLECTION = TLUIC = tilia._timeline_ui_collection

    # # delete existing slider timeline
    # TLC.delete_timeline(TLC._timelines[0])

    # # load file
    # FILE_PATH = r"C:\prog\TiLiA-devresources\audio_1hrc.tla"
    # tilia._file_manager.open_file_by_path(FILE_PATH)

    events.post(
        Event.REQUEST_ADD_TIMELINE, kind=TimelineKind.HIERARCHY_TIMELINE, name="HRC1"
    )

    tlui = TIMELINEUI_COLLECTION._display_order[1]
    elements = list(tlui.element_manager._elements)
    ordered_elements = sorted(elements, key=lambda c: (c.level, c.start_x))
    # ordered_elements = sorted(elements, key=lambda c: c.time)
    tlui.select_element(ordered_elements[0])

    events.post(Event.KEY_PRESS_DELETE)

    tlui.timeline.create_timeline_component(
        kind=ComponentKind.HIERARCHY,
        label="first",
        start=0.2,
        pre_start=0.1,
        end=0.4,
        post_end=0.5,
        level=1,
    )

    tlui.timeline.create_timeline_component(
        kind=ComponentKind.HIERARCHY,
        label="second",
        start=0.6,
        pre_start=0.5,
        end=0.8,
        level=1,
    )
