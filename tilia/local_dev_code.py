import time
from typing import TYPE_CHECKING

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

# select first element from first timeline
tlui = TIMELINEUI_COLLECTION._display_order[1]
elements = list(tlui.element_manager._elements)
ordered_elements = sorted(elements, key=lambda c: (c.level, c.start_x))
# ordered_elements = sorted(elements, key=lambda c: c.time)
tlui.select_element(ordered_elements[0])

# zoom and scroll to time
time = 10.0
width = 4000
TLUIC.timeline_width = width
TLUIC.scroll_to_x(TLUIC.get_x_by_time(time))
"""


# noinspection PyProtectedMember
def func(tilia) -> None:
    """
    This function will be called right befor the ui mainloop on every startup.
    Use this function to run code for development purposes.
    Changes to this file should bot be commited.
    """
    pass
