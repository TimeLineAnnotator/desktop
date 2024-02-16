import pytest

from tests.ui.timelines.harmony.interact import click_harmony_ui
from tilia.requests import Post, post
from tilia.timelines.component_kinds import ComponentKind


@pytest.mark.parametrize("component_kind", [ComponentKind.HARMONY, ComponentKind.MODE])
class TestArrowSelection:
    def test_clicking_right_arrow_selects_next_element(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        click_harmony_ui(ui1)

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert ui2.is_selected()

    def test_clicking_right_arrow_with_multiple_selected_selects_next_element(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        _, ui3 = harmony_tlui.create_component(component_kind, 20)
        _, ui4 = harmony_tlui.create_component(component_kind, 30)
        click_harmony_ui(ui1)
        click_harmony_ui(ui2, modifier='shift')
        click_harmony_ui(ui3, modifier='shift')

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert not ui2.is_selected()
        assert not ui3.is_selected()
        assert ui4.is_selected()

    def test_clicking_right_arrow_does_nothing_if_last_element_is_selected(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        click_harmony_ui(ui2)

        post(Post.TIMELINE_KEY_PRESS_RIGHT)

        assert not ui1.is_selected()
        assert ui2.is_selected()

    def test_clicking_left_arrow_selects_previous_element(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        click_harmony_ui(ui2)

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()

    def test_clicking_left_arrow_with_multiple_selected_selects_previous_element(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        _, ui3 = harmony_tlui.create_component(component_kind, 20)
        _, ui4 = harmony_tlui.create_component(component_kind, 30)
        click_harmony_ui(ui2)
        click_harmony_ui(ui3, modifier='shift')
        click_harmony_ui(ui4, modifier='shift')

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()
        assert not ui3.is_selected()
        assert not ui4.is_selected()

    def test_clicking_left_arrow_does_nothing_if_first_element_is_selected(
        self, component_kind, harmony_tlui
    ):
        _, ui1 = harmony_tlui.create_component(component_kind, 0)
        _, ui2 = harmony_tlui.create_component(component_kind, 10)
        click_harmony_ui(ui1)

        post(Post.TIMELINE_KEY_PRESS_LEFT)

        assert ui1.is_selected()
        assert not ui2.is_selected()
