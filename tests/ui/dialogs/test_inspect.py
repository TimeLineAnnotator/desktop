import pytest

from tests.conftest import parametrize_ui_element
from tilia.requests import Post, post
from tilia.ui import commands
from tilia.ui.timelines.beat import BeatUI
from tilia.ui.windows.kinds import WindowKind


@parametrize_ui_element
def test_inspect_elements(tluis, element, request):
    element = request.getfixturevalue(element)
    element.timeline_ui.select_element(element)

    commands.execute("timeline.element.inspect")


@parametrize_ui_element
def test_inspect_elements_with_beat_timeline(element, beat_tlui, request):
    # some properties are only displayed if a beat timeline is present
    element = request.getfixturevalue(element)
    if not isinstance(element, BeatUI):
        for i in range(10):
            beat_tlui.create_beat(i)

    element.timeline_ui.select_element(element)

    commands.execute("timeline.element.inspect")


class TestInspectComboBox:
    @pytest.fixture(autouse=True)
    def close_inspector(self):
        yield
        post(Post.WINDOW_CLOSE, WindowKind.INSPECT)

    def open_inspector_for(self, tlui, element_ui, qtui):
        tlui.select_element(element_ui)
        commands.execute("timeline.element.inspect")
        return qtui._windows[WindowKind.INSPECT]

    def test_combobox_sends_data_not_index(self, qtui, harmony_tlui):
        harmony, _ = harmony_tlui.create_harmony(accidental=0)
        harmony_ui = harmony_tlui.get_element(harmony.id)
        inspector = self.open_inspector_for(harmony_tlui, harmony_ui, qtui)

        inspector.field_name_to_widgets["Accidental"][1].setCurrentIndex(2)

        assert harmony_ui.get_data("accidental") == -1

    def test_combobox_displays_correct_item_for_current_value(self, qtui, harmony_tlui):
        # When accidental=-1 ("♭"), the combobox must show index 2, not index 1.
        harmony, _ = harmony_tlui.create_harmony(accidental=-1)
        harmony_ui = harmony_tlui.get_element(harmony.id)
        inspector = self.open_inspector_for(harmony_tlui, harmony_ui, qtui)

        assert inspector.field_name_to_widgets["Accidental"][1].currentData() == -1
