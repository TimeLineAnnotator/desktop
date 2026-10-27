import re

from tests.ui.timelines.interact import click_timeline_ui_view
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.windows.kinds import WindowKind


def _click_element_ui(element, button, modifier, double):
    click_timeline_ui_view(
        element.timeline_ui.view,
        button,
        time_x_converter.get_x_by_time(element.get_data("time")),
        element.timeline_ui.get_data("height") / 2,
        element.body,
        modifier,
        double,
    )


def click_harmony_ui(harmony_ui, button="left", modifier=None, double=False):
    _click_element_ui(harmony_ui, button, modifier, double)


def click_mode_ui(mode_ui, button="left", modifier=None, double=False):
    _click_element_ui(mode_ui, button, modifier, double)


def open_inspector_for(element_ui, qtui):
    """Click the harmony or mode, inspect it, and return the Inspector."""
    _click_element_ui(element_ui, "left", None, False)
    commands.execute("timeline.element.inspect")
    return qtui._windows[WindowKind.INSPECT]


def numeral_part(label: str) -> str:
    """The label's accidental and numeral, without its figures and quality."""
    return re.match(r"(?:`[b#x])*[IViv]+", label).group(0)


# The accidentals that start a Roman-numeral label are drawn as MusAnalysis
# markup, and are typed as plain "#" and "b".
_LABEL_ACCIDENTAL_TO_TYPED = {"`b": "b", "`#": "#", "`x": "##"}


def label_as_typed(label: str) -> str:
    """What a user types to get a label: its leading accidentals, as typed."""
    typed = ""
    while label[:2] in _LABEL_ACCIDENTAL_TO_TYPED:
        typed += _LABEL_ACCIDENTAL_TO_TYPED[label[:2]]
        label = label[2:]
    return typed + label
