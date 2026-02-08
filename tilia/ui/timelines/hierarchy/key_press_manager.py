class HierarchyTimelineUIKeyPressManager:
    def __init__(self, timeline_ui):
        self.element_manager = timeline_ui.element_manager
        self.has_selected_elements = timeline_ui.has_selected_elements
        self.selected_elements = timeline_ui.selected_elements
        self.get_element = timeline_ui.get_element
        self.select_element = timeline_ui.select_element
        self.deselect_element = timeline_ui.deselect_element

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[1:]:
                self.element_manager.deselect_element(element)

    def on_vertical_arrow_press(self, direction: str):
        if not self.has_selected_elements:
            return

        self._deselect_all_but_last()

        selected_element = self.element_manager.get_selected_elements()[0]

        element_to_select = None

        parent = selected_element.get_data("parent")
        children = selected_element.get_data("children")
        if direction == "up" and parent:
            element_to_select = self.get_element(parent.id)
        elif direction == "down" and children:
            component_to_select = sorted(selected_element.get_data("children"))[0]
            element_to_select = self.get_element(component_to_select.id)

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)

    def on_horizontal_arrow_press(self, side: str):
        def _get_next_element_in_same_level(elm):
            def is_later_at_same_level(h):
                return (
                    h.tl_component.start > elm.tl_component.start
                    and h.tl_component.level == elm.tl_component.level
                )

            later_elements = self.element_manager.get_elements_by_condition(
                is_later_at_same_level
            )
            if later_elements:
                return sorted(later_elements, key=lambda x: x.tl_component.start)[0]
            else:
                return None

        def _get_previous_element_in_same_level(elm):
            def is_earlier_at_same_level(h):
                return (
                    h.tl_component.start < elm.tl_component.start
                    and h.tl_component.level == elm.tl_component.level
                )

            earlier_elements = self.element_manager.get_elements_by_condition(
                is_earlier_at_same_level
            )
            if earlier_elements:
                return sorted(earlier_elements, key=lambda x: x.tl_component.start)[-1]
            else:
                return None

        if not self.has_selected_elements:
            return

        if side not in ["right", "left"]:
            raise ValueError(f"Invalid arrow '{side}'.")

        if side == "right":
            self._deselect_all_but_last()
        else:
            self._deselect_all_but_first()

        selected_element = self.selected_elements[0]
        if side == "right":
            element_to_select = _get_next_element_in_same_level(selected_element)
        else:
            element_to_select = _get_previous_element_in_same_level(selected_element)

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)
