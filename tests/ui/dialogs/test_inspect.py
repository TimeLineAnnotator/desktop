from tests.conftest import parametrize_ui_element
from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.beat import BeatUI


@parametrize_ui_element
def test_inspect_elements(tluis, element, user_actions, request):
    element = request.getfixturevalue(element)
    element.timeline_ui.select_element(element)

    user_actions.trigger(TiliaAction.TIMELINE_ELEMENT_INSPECT)


@parametrize_ui_element
def test_inspect_elements_with_beat_timeline(element, beat_tlui, user_actions, request):
    # some properties are only displayed if a beat timeline is present
    element = request.getfixturevalue(element)
    if not isinstance(element, BeatUI):
        for i in range(10):
            beat_tlui.create_beat(i)

    element.timeline_ui.select_element(element)

    user_actions.trigger(TiliaAction.TIMELINE_ELEMENT_INSPECT)
