import music21

from tilia import errors
from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
    with_elements,
)
from tilia.ui.timelines.collection.collection import TimelineSelector, TimelineUIs
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
    paste_into_element,
)
from tilia.ui.timelines.harmony import HarmonyUI, ModeUI
from tilia.ui.timelines.harmony.context_menu import HarmonyTimelineUIContextMenu
from tilia.ui.timelines.harmony.toolbar import HarmonyTimelineToolbar

from . import level_label


class HarmonyTimelineUI(TimelineUI):
    TOOLBAR_CLASS = HarmonyTimelineToolbar
    ELEMENT_CLASS = [HarmonyUI, ModeUI]
    CONTEXT_MENU_CLASS = HarmonyTimelineUIContextMenu
    TIMELINE_KIND = TimelineKind.HARMONY_TIMELINE
    ACCEPTS_HORIZONTAL_ARROWS = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.UPDATE_TRIGGERS = self.UPDATE_TRIGGERS + [
            "level_count",
            "visible_level_count",
        ]
        self._setup_level_labels()

    @classmethod
    def register_commands(cls, collection: TimelineUIs):
        args = [
            ("add_harmony", "Add harmony", "h", "harmony-add", TimelineSelector.FIRST),
            (
                "component.display_as_letter",
                "Display as letter",
                "",
                "harmony-display-letter",
                TimelineSelector.SELECTED,
            ),
            (
                "component.display_as_roman",
                "Display as roman numeral",
                "",
                "harmony-display-roman",
                TimelineSelector.SELECTED,
            ),
            ("hide_keys", "Hide keys", "", "", TimelineSelector.FIRST),
            ("show_keys", "Show keys", "", "", TimelineSelector.FIRST),
            ("add_mode", "Add mode", "", "mode-add", TimelineSelector.FIRST),
        ]

        for name, text, shortcut, icon, selector in args:
            cls.register_timeline_command(
                collection,
                name,
                getattr(cls, f"on_{name.replace('.', '_')}"),
                selector,
                text=text,
                shortcut=shortcut,
                icon=icon,
            )

    def _setup_level_labels(self):
        self.harmony_level_label = level_label.LevelLabel(
            get(Get.LEFT_MARGIN_X) - 5, self.get_y(1) - 5, "Harmonies"
        )
        self.key_level_label = level_label.LevelLabel(
            get(Get.LEFT_MARGIN_X) - 5, self.get_y(2) - 5, "Keys"
        )

        self.scene.addItem(self.harmony_level_label)
        self.scene.addItem(self.key_level_label)

    def modes(self):
        return self.element_manager.get_elements_by_condition(
            lambda elm: isinstance(elm, ModeUI)
        )

    def harmonies(self):
        return self.element_manager.get_elements_by_condition(
            lambda elm: isinstance(elm, HarmonyUI)
        )

    @with_elements
    def on_delete_component(self, elements: list[TimelineUIElement], *_, **__):
        if any((elm for elm in elements if elm.get_data("KIND") == ComponentKind.MODE)):
            needs_recalculation = True
        else:
            needs_recalculation = False

        self.timeline.delete_components(self.elements_to_components(elements))

        if needs_recalculation:
            self.on_mode_delete_done()

        return True

    def on_mode_add_done(self):
        self.update_harmony_labels()

    def on_mode_delete_done(self):
        self.update_harmony_labels()

    def on_element_drag_done(self):
        self.update_harmony_labels()

    def on_timeline_components_deserialized(self):
        self.update_harmony_labels()

    def update_harmony_labels(self):
        for harmony in self.harmonies():
            harmony.update_label()

    def update_level_count(self):
        self.update_height()

    def update_height(self):
        new_height = self.get_data("level_height") * self.get_data(
            "visible_level_count"
        )
        self.scene.set_height(new_height)
        self.view.set_height(new_height)
        self.element_manager.update_time_on_elements()

    def update_visible_level_count(self):
        self.update_height()
        self.element_manager.update_time_on_elements()
        self.update_level_labels()

    def update_level_labels(self):
        self.harmony_level_label.set_position(
            get(Get.LEFT_MARGIN_X) - 5, self.get_y(1) - 5
        )
        self.key_level_label.setVisible(self.get_data("visible_level_count") == 2)

    def get_y(self, level: int):
        return self.get_data("level_height") * (
            self.get_data("visible_level_count") - level
        )

    def get_key_by_time(self, time: float) -> music21.key.Key:
        return self.timeline.get_key_by_time(time)

    def paste_single_into_selected_elements(self, paste_data: list[dict] | dict):
        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

        self.update_harmony_labels()

    def paste_multiple_into_selected_elements(self, paste_data: list[dict] | dict):
        paste_data = sorted(paste_data, key=lambda md: md["context"]["time"])

        first_selected_element = self.selected_elements[0]
        if first_selected_element.kind == paste_data[0]["context"]["KIND"]:
            self.deselect_element(self.selected_elements[0])
            paste_into_element(first_selected_element, paste_data[0])
            self.select_element(first_selected_element)

            self.create_pasted_components(
                paste_data[1:],
                paste_data[0]["context"]["time"],
                self.selected_elements[0].get_data("time"),
            )
        else:
            self.create_pasted_components(
                paste_data,
                paste_data[0]["context"]["time"],
                self.selected_elements[0].get_data("time"),
            )

        self.update_harmony_labels()

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(md["context"]["time"] for md in paste_data)

        self.create_pasted_components(
            paste_data,
            reference_time,
            get(Get.SELECTED_TIME),
        )

        self.update_harmony_labels()

    def create_pasted_components(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for harmony_data in paste_data:
            harmony_time = harmony_data["context"]["time"]

            self.timeline.create_component(
                harmony_data["context"]["KIND"],
                target_time + (harmony_time - reference_time),
                **harmony_data["values"],
            )

    def on_add_mode(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)

        valid, reason = self.timeline.component_manager._validate_component_creation(
            ComponentKind.MODE, time
        )

        if not valid:
            errors.display(errors.ADD_MODE_FAILED, reason)
            return False

        confirmed, kwargs = get(Get.FROM_USER_MODE_PARAMS)
        if not confirmed:
            return False
        mode, reason = self.timeline.create_component(
            ComponentKind.MODE, time, **kwargs
        )
        if not mode:
            errors.display(errors.ADD_MODE_FAILED, reason)
            return False
        self.on_mode_add_done()
        return True

    def on_add_harmony(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)

        valid, reason = self.timeline.component_manager._validate_component_creation(
            ComponentKind.HARMONY, time
        )

        if not valid:
            errors.display(errors.ADD_HARMONY_FAILED, reason)
            return False

        confirmed, kwargs = get(Get.FROM_USER_HARMONY_PARAMS)
        if not confirmed:
            return False

        harmony, reason = self.timeline.create_component(
            ComponentKind.HARMONY, time, **kwargs
        )

        if not harmony:
            errors.display(errors.ADD_HARMONY_FAILED, reason)
            return False
        return True

    @with_elements
    def on_component_display_as_letter(self, elements: list[ModeUI | HarmonyUI]):
        harmonies = [elm for elm in elements if isinstance(elm, HarmonyUI)]
        self.set_elements_attr(harmonies, "display_mode", "letter")
        return True

    @with_elements
    def on_component_display_as_roman(self, elements: list[ModeUI | HarmonyUI]):
        harmonies = [elm for elm in elements if isinstance(elm, HarmonyUI)]
        self.set_elements_attr(harmonies, "display_mode", "roman")
        return True

    @staticmethod
    def _get_copy_data_from_element(element: HarmonyUI | ModeUI):
        return {
            "components": get_copy_data_from_element(
                element, element.DEFAULT_COPY_ATTRIBUTES
            ),
            "timeline_kind": TimelineKind.HARMONY_TIMELINE,
        }

    def on_show_keys(self, _):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.id,
            "visible_level_count",
            2,
        )
        return True

    def on_hide_keys(self, _):
        get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.id,
            "visible_level_count",
            1,
        )
        return True
