import pytest

from tilia.requests import Post, post
from tilia.timelines.component_kinds import ComponentKind


@pytest.fixture(params=['marker', 'harmony', 'beat', 'hierarchy'])
def tlui(request, marker_tlui, harmony_tlui, beat_tlui, hierarchy_tlui):
    return {"marker": marker_tlui, "harmony": harmony_tlui, "beat": beat_tlui, 'hierarchy': hierarchy_tlui}[
        request.param
    ]


@pytest.mark.parametrize(
    "tlui,component_kind",
    [
        ("harmony", ComponentKind.HARMONY),
        ("harmony", ComponentKind.MODE),
        ("marker", ComponentKind.MARKER),
        ("beat", ComponentKind.BEAT),
        ('hierarchy', ComponentKind.HIERARCHY)
    ],
    indirect=["tlui"],
)
class TestArrowSelection:
    def test_clicking_right_arrow_selects_next_element(self, tlui, component_kind):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        tlui.select_element(ui1)

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert ui2.is_selected()

    def test_clicking_right_arrow_with_multiple_selected_selects_next_element(
        self, tlui, component_kind
    ):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        _, ui3 = tlui.create_component(component_kind, 20)
        _, ui4 = tlui.create_component(component_kind, 30)
        tlui.select_element(ui1)
        tlui.select_element(ui2)
        tlui.select_element(ui3)

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert not ui2.is_selected()
        assert not ui3.is_selected()
        assert ui4.is_selected()

    def test_clicking_right_arrow_does_nothing_if_last_element_is_selected(
        self, tlui, component_kind
    ):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        tlui.select_element(ui2)

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert ui2.is_selected()

    def test_clicking_left_arrow_selects_previous_element(self, tlui, component_kind):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        tlui.select_element(ui2)

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()

    def test_clicking_left_arrow_with_multiple_selected_selects_previous_element(
        self, tlui, component_kind
    ):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        _, ui3 = tlui.create_component(component_kind, 20)
        _, ui4 = tlui.create_component(component_kind, 30)
        tlui.select_element(ui2)
        tlui.select_element(ui3)
        tlui.select_element(ui4)

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()
        assert not ui3.is_selected()
        assert not ui4.is_selected()

    def test_clicking_left_arrow_does_nothing_if_first_element_is_selected(
        self, tlui, component_kind
    ):
        _, ui1 = tlui.create_component(component_kind, 0)
        _, ui2 = tlui.create_component(component_kind, 10)
        tlui.select_element(ui1)

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()
