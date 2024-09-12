from __future__ import annotations

import functools
from typing import Any, Optional

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import (
    QGraphicsView,
    QMainWindow,
    QGraphicsItem,
    QGraphicsScene,
)

import tilia
import tilia.errors
import tilia.ui.timelines.collection.request_handler
import tilia.ui.timelines.collection.requests.timeline_uis
import tilia.ui.timelines.collection.requests.args
import tilia.ui.timelines.collection.requests.enums
import tilia.ui.timelines.collection.requests.post_process
from tilia.ui import actions
from tilia.settings import settings
from tilia.media.player.base import MediaTimeChangeReason
from tilia.timelines import timeline_kinds
from tilia.timelines.component_kinds import ComponentKind
from .scene import TimelineUIsScene
from .validators import validate
from tilia.exceptions import TimelineUINotFound, UserCancelledDialog
from tilia.requests import get, Get, serve
from tilia.requests import listen, Post, post
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind, TimelineKind
from tilia.ui.coords import get_x_by_time, get_time_by_x
from tilia.ui.dialogs.choose import ChooseDialog
from tilia.ui.modifier_enum import ModifierEnum
from tilia.ui.player import PlayerToolbarElement
from tilia.ui.timelines.base.element_manager import ElementManager
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.scene import TimelineScene
from tilia.ui.timelines.toolbar import TimelineToolbar
from tilia.ui.timelines.view import TimelineView
from tilia.ui.timelines.collection.requests.timeline import (
    TimelineSelector,
    TlRequestSelector,
)
from tilia.ui.timelines.collection.requests.element import TlElmRequestSelector
from .view import TimelineUIsView
from ..beat import BeatTimelineToolbar
from ..harmony import HarmonyTimelineToolbar
from ..hierarchy import HierarchyTimelineToolbar
from ..marker import MarkerTimelineToolbar
from ..pdf import PdfTimelineToolbar
from ..selection_box import SelectionBoxQt
from ..slider.timeline import SliderTimelineUI
from ...actions import TiliaAction
from ...request_handler import RequestFailure


class TimelineUIs:
    ZOOM_FACTOR = 0.1
    DO_NOT_RECORD = [
        Post.TIMELINE_ELEMENT_COPY,
    ]
    UPDATE_TRIGGERS = ["height", "level_count"]

    def __init__(
        self,
        main_window: QMainWindow,
    ):

        self.main_window = main_window
        self.kind_to_toolbar = {kind: None for kind in timeline_kinds.NOT_SLIDER}

        self._timeline_uis = set()
        self._select_order = []
        self._timeline_uis_to_playback_line_ids = {}
        self.sb_items_to_selected_items = {}

        self._setup_widgets(main_window)
        self._setup_requests()

        self._setup_selection_box()
        self._setup_drag_tracking_vars()
        self._setup_auto_scroll()
        self.selected_time = get(Get.MEDIA_CURRENT_TIME)
        self.loop_time = (self.selected_time, self.selected_time)
        self.loop_elements = set()
        self.loop_delete_ignore = set()

    def __str__(self) -> str:
        return self.__class__.__name__ + "-" + str(id(self))

    def __iter__(self):
        return iter(self._timeline_uis)

    def __getitem__(self, item):
        return sorted(self._timeline_uis)[item]

    def __len__(self):
        return len(self._timeline_uis)

    @property
    def is_empty(self):
        return len(self) == 0

    def _setup_selection_box(self):
        self.selection_boxes = []
        self.selection_boxes_above = False
        self.selection_boxes_below = True

    def _setup_drag_tracking_vars(self):
        self.is_dragging = False
        self.hscrollbar_is_being_dragged = False

    def _setup_auto_scroll(self):
        self.auto_scroll_is_enabled = settings.get("general", "auto-scroll")

    def _setup_widgets(self, main_window: QMainWindow):
        self.scene = TimelineUIsScene()
        self.view = TimelineUIsView()
        self.view.setScene(self.scene)
        main_window.setCentralWidget(self.view)

    def _setup_requests(self):
        LISTENS = {
            (Post.TIMELINE_CREATE_DONE, self.on_timeline_created),
            (Post.TIMELINE_DELETE_DONE, self.on_timeline_deleted),
            (Post.TIMELINE_COMPONENT_CREATED, self.on_timeline_component_created),
            (Post.TIMELINE_COMPONENT_DELETED, self.on_timeline_component_deleted),
            (
                Post.TIMELINE_COMPONENT_SET_DATA_DONE,
                self.on_timeline_component_set_data_done,
            ),
            (Post.TIMELINE_SET_DATA_DONE, self.on_timeline_set_data_done),
            (Post.TIMELINE_VIEW_LEFT_CLICK, self._on_timeline_ui_left_click),
            (Post.TIMELINE_VIEW_DOUBLE_LEFT_CLICK, self._on_timeline_ui_left_click),
            (Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, self._on_timeline_ui_left_drag),
            (Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE, self.on_timeline_ui_left_released),
            (Post.TIMELINE_VIEW_RIGHT_CLICK, self._on_timeline_ui_right_click),
            (
                Post.TIMELINES_AUTO_SCROLL_ENABLE,
                functools.partial(self.set_auto_scroll, True),
            ),
            (
                Post.TIMELINES_AUTO_SCROLL_DISABLE,
                functools.partial(self.set_auto_scroll, False),
            ),
            (
                Post.TIMELINE_KEY_PRESS_DOWN,
                functools.partial(self.on_arrow_press, "down"),
            ),
            (Post.TIMELINE_KEY_PRESS_UP, functools.partial(self.on_arrow_press, "up")),
            (
                Post.TIMELINE_KEY_PRESS_RIGHT,
                functools.partial(self.on_arrow_press, "right"),
            ),
            (
                Post.TIMELINE_KEY_PRESS_LEFT,
                functools.partial(self.on_arrow_press, "left"),
            ),
            (Post.ELEMENT_DRAG_END, lambda: self.set_is_dragging(False)),
            (Post.ELEMENT_DRAG_START, lambda: self.set_is_dragging(True)),
            (Post.SLIDER_DRAG, self.on_slider_drag),
            (Post.SLIDER_DRAG_END, lambda: self.set_is_dragging(False)),
            (Post.SLIDER_DRAG_START, lambda: self.set_is_dragging(True)),
            (Post.PLAYER_CURRENT_TIME_CHANGED, self.on_media_time_change),
            (Post.VIEW_ZOOM_IN, self.on_zoom_in),
            (Post.VIEW_ZOOM_OUT, self.on_zoom_out),
            (Post.SELECTION_BOX_SELECT_ITEM, self.on_selection_box_select_item),
            (Post.SELECTION_BOX_DESELECT_ITEM, self.on_selection_box_deselect_item),
            (Post.TIMELINE_WIDTH_SET_DONE, self.on_timeline_width_set_done),
            (Post.TIMELINES_CROP_DONE, self.on_timelines_crop_done),
            (Post.HIERARCHY_SELECTED, self.on_hierarchy_selected),
            (Post.HIERARCHY_DESELECTED, self.on_hierarchy_deselected),
            (Post.HIERARCHY_MERGE_SPLIT_DONE, self.on_hierarchy_merge_split),
            (
                Post.HARMONY_TIMELINE_COMPONENTS_DESERIALIZED,
                self.on_harmony_timeline_components_deserialized,
            ),
            (Post.LOOP_IGNORE_COMPONENT, self.on_loop_ignore_delete),
            (Post.PLAYER_CANCEL_LOOP, self.on_loop_cancel),
            (Post.PLAYER_TOGGLE_LOOP, self.on_loop_toggle),
            (Post.EDIT_REDO, self.loop_cancel),
            (Post.EDIT_UNDO, self.loop_cancel),
        }

        SERVES = {
            (Get.TIMELINE_UI, self.get_timeline_ui),
            (Get.TIMELINE_UI_BY_ATTR, self.get_timeline_ui_by_attr),
            (Get.TIMELINE_UIS_BY_ATTR, self.get_timeline_uis_by_attr),
            (Get.TIMELINE_UIS, self.get_timeline_uis),
            (Get.TIMELINE_UI_ELEMENT, self.get_timeline_ui_element),
            (Get.TIMELINE_ELEMENTS_SELECTED, self.get_timeline_elements_selected),
            (Get.SELECTED_TIME, self.get_selected_time),
            (Get.LOOP_TIME, self.get_loop_time),
            (
                Get.FIRST_TIMELINE_UI_IN_SELECT_ORDER,
                self.get_first_timeline_ui_in_select_order,
            ),
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

        for request in tilia.ui.timelines.collection.requests.timeline_uis.requests:
            listen(
                self, request, functools.partial(self.on_timeline_ui_request, request)
            )

        for (
            request,
            selector,
        ) in tilia.ui.timelines.collection.requests.element.request_to_scope.items():
            listen(
                self,
                request,
                functools.partial(self.on_timeline_element_request, request, selector),
            )

        for (
            request,
            selector,
        ) in tilia.ui.timelines.collection.requests.timeline.request_to_scope.items():
            listen(
                self,
                request,
                functools.partial(self.on_timeline_request, request, selector),
            )

    def create_timeline_ui(self, kind: TlKind, id: int) -> TimelineUI:
        timeline_class = self.get_timeline_ui_class(kind)
        w = get(Get.TIMELINE_WIDTH)
        h = get(Get.TIMELINE, id).get_data("height")
        scene = self.create_timeline_scene(id, w, h)
        view = self.create_timeline_view(scene)

        element_manager = ElementManager(timeline_class.ELEMENT_CLASS)

        tl_ui = timeline_class(
            id=id,
            collection=self,
            element_manager=element_manager,
            scene=scene,
            view=view,
        )

        self._add_to_timeline_uis_set(tl_ui)
        self._add_to_timeline_ui_select_order(tl_ui)

        self.add_timeline_view_to_scene(view, tl_ui.get_data("ordinal"))
        self.setup_toolbar(kind)

        return tl_ui

    def on_timeline_component_created(
        self, _: TlKind, tl_id: int, component_kind: ComponentKind, component_id: int
    ):
        self.get_timeline_ui(tl_id).on_timeline_component_created(
            component_kind, component_id
        )

    def on_timeline_component_deleted(self, _: TlKind, tl_id: int, component_id: int):
        if (tl_id, component_id) in self.loop_elements:
            if (tl_id, component_id) not in self.loop_delete_ignore:
                self.loop_elements.remove((tl_id, component_id))
                self._update_loop_elements(clear=len(self.loop_elements) == 0)

        self.get_timeline_ui(tl_id).on_timeline_component_deleted(component_id)

    def on_timeline_component_set_data_done(
        self, timeline_id: int, component_id: int, attr: str, _: Any
    ):
        timeline_ui = self.get_timeline_ui(timeline_id)
        element = timeline_ui.get_element(component_id)
        element.update(attr)
        if attr in element.tl_component.ORDERING_ATTRS:
            timeline_ui.update_element_order(element)
        if (timeline_id, component_id) in self.loop_elements and self.loop_time[
            0
        ] != self.loop_time[1]:
            self._update_loop_elements()

    def on_timeline_set_data_done(self, id: int, attr: str, _: Any):
        self.get_timeline_ui(id).update(attr)
        if attr in self.UPDATE_TRIGGERS:
            # these are the collection updaters
            # they're different from timeline ui updaters
            getattr(self, "update_" + attr)()

    def delete_timeline_ui(self, timeline_ui: TimelineUI):
        timeline_ui.delete()
        self.scene.removeItem(timeline_ui.view.proxy)
        self._remove_from_timeline_uis_set(timeline_ui)
        self._remove_from_timeline_ui_select_order(timeline_ui)
        self._hide_toolbar_if_needed(timeline_ui.TIMELINE_KIND)
        self.update_timeline_uis_position()

    def _add_to_timeline_uis_set(self, timeline_ui: TimelineUI) -> None:
        self._timeline_uis.add(timeline_ui)

    def _remove_from_timeline_uis_set(self, timeline_ui: TimelineUI) -> None:
        try:
            self._timeline_uis.remove(timeline_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{timeline_ui}' from {self}: not in"
                " self.timeline_uis."
            )

    def _add_to_timeline_ui_select_order(self, tl_ui: TimelineUI) -> None:
        self._select_order.insert(0, tl_ui)

    def _remove_from_timeline_ui_select_order(self, tl_ui: TimelineUI) -> None:
        try:
            self._select_order.remove(tl_ui)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline ui '{tl_ui}' from select order: not in select"
                " order."
            )

    def _send_to_top_of_select_order(self, tl_ui: TimelineUI):
        self._select_order.remove(tl_ui)
        self._select_order.insert(0, tl_ui)

    def add_timeline_view_to_scene(self, view: QGraphicsView, ordinal: int) -> None:
        view.proxy = self.scene.addWidget(view)
        y = sum(tlui.get_data("height") for tlui in sorted(self)[: ordinal - 1])
        view.move(0, y)
        self.update_height()

    def update_timeline_uis_position(self):
        next_y = 0
        for tlui in sorted(self):
            if tlui.get_data("is_visible"):
                tlui.view.move(0, next_y)
                next_y += tlui.get_data("height")

    def update_height(self):
        self.update_timeline_uis_position()
        self.set_playback_lines_position(get(Get.MEDIA_CURRENT_TIME))
        self.change_loop_box_position()

    def update_level_count(self):
        self.update_height()

    def set_playback_lines_position(self, time):
        for tl_ui in self:
            self.change_playback_line_position(tl_ui, time)

    def update_toolbar_visibility(self):
        visible_tl_kinds = {
            tlui.TIMELINE_KIND for tlui in self if tlui.get_data("is_visible")
        }
        for kind, toolbar in self.kind_to_toolbar.items():
            toolbar: TimelineToolbar
            if not toolbar:
                continue
            toolbar.show() if kind in visible_tl_kinds else toolbar.hide()

    def get_scene_height(self):
        return (
            sum(
                tlui.get_data("height")
                for tlui in sorted(self)
                if tlui.get_data("is_visible")
            )
            + 20
        )

    def on_timeline_width_set_done(self, width):
        self.scene.setSceneRect(0, 0, width, self.get_scene_height())
        for tlui in self:
            tlui.set_width(width)

    def update_timeline_ui_ordinal(self):
        self.update_timeline_uis_position()

    @staticmethod
    def update_timeline_times(tlui: TimelineUI):
        if tlui.TIMELINE_KIND == TlKind.SLIDER_TIMELINE:
            tlui: SliderTimelineUI
            tlui.update_items_position()
        else:
            tlui.element_manager.update_time_on_elements()

    @staticmethod
    def get_timeline_ui_class(kind: TlKind) -> type[TimelineUI]:
        from tilia.ui.timelines.hierarchy import HierarchyTimelineUI
        from tilia.ui.timelines.slider.timeline import SliderTimelineUI
        from tilia.ui.timelines.audiowave.timeline import AudioWaveTimelineUI
        from tilia.ui.timelines.marker.timeline import MarkerTimelineUI
        from tilia.ui.timelines.harmony.timeline import HarmonyTimelineUI
        from tilia.ui.timelines.beat import BeatTimelineUI
        from tilia.ui.timelines.pdf import PdfTimelineUI

        kind_to_class = {
            TlKind.HIERARCHY_TIMELINE: HierarchyTimelineUI,
            TlKind.SLIDER_TIMELINE: SliderTimelineUI,
            TlKind.AUDIOWAVE_TIMELINE: AudioWaveTimelineUI,
            TlKind.MARKER_TIMELINE: MarkerTimelineUI,
            TlKind.BEAT_TIMELINE: BeatTimelineUI,
            TlKind.HARMONY_TIMELINE: HarmonyTimelineUI,
            TlKind.PDF_TIMELINE: PdfTimelineUI,
        }

        return kind_to_class[kind]

    @staticmethod
    def create_timeline_scene(id: int, width: int, height: int):
        return TimelineScene(
            id=id,
            width=width,
            height=height,
            left_margin=get(Get.LEFT_MARGIN_X),
            text=get(Get.TIMELINE, id).name,
        )

    @staticmethod
    def create_timeline_view(scene: TimelineScene):
        return TimelineView(scene)

    def setup_toolbar(self, tl_kind: TlKind):
        if not tl_kind:
            return

        if tl_kind in [TlKind.SLIDER_TIMELINE, TlKind.AUDIOWAVE_TIMELINE]:
            return

        if toolbar := self.kind_to_toolbar[tl_kind]:
            toolbar.show()
        else:
            toolbar = self.get_toolbar_class(tl_kind)()
            self.main_window.addToolBar(toolbar)
            self.kind_to_toolbar[tl_kind] = toolbar

    @staticmethod
    def get_toolbar_class(kind: TlKind) -> type[TimelineToolbar]:
        return {
            TlKind.BEAT_TIMELINE: BeatTimelineToolbar,
            TlKind.MARKER_TIMELINE: MarkerTimelineToolbar,
            TlKind.HIERARCHY_TIMELINE: HierarchyTimelineToolbar,
            TlKind.HARMONY_TIMELINE: HarmonyTimelineToolbar,
            TlKind.PDF_TIMELINE: PdfTimelineToolbar,
        }[kind]

    def _get_timeline_ui_by_scene(self, scene):
        return next((tlui for tlui in self if tlui.scene == scene), None)

    def _get_timeline_ui_by_view(self, view):
        return next((tlui for tlui in self if tlui.view == view), None)

    def _on_timeline_ui_right_click(
        self,
        view: QGraphicsView,
        x: int,
        y: int,
        item: Optional[QGraphicsItem],
        modifier: ModifierEnum,
        **_,  # ignores the double argument
    ) -> None:
        timeline_ui = self._get_timeline_ui_by_view(view)

        if not timeline_ui:
            raise ValueError(
                f"Can't process left click: no timeline with view '{view}' on"
                f" {self}"
            )

        if (
            modifier == Qt.KeyboardModifier.NoModifier
            and not timeline_ui.belongs_to_selection(item)
        ):
            self.deselect_all_elements_in_timeline_uis(excluding=timeline_ui)

        self._send_to_top_of_select_order(timeline_ui)
        timeline_ui.on_right_click(x, y, item, modifier=modifier)

    def _on_timeline_ui_left_click(
        self,
        view: QGraphicsView,
        x: int,
        y: int,
        item: Optional[QGraphicsItem],
        modifier: Qt.KeyboardModifier,
        double: bool,
    ) -> None:
        timeline_ui = self._get_timeline_ui_by_view(view)

        if double:
            self.clear_selection_boxes()

        if modifier == Qt.KeyboardModifier.NoModifier:
            self.deselect_all_elements_in_timeline_uis(excluding=timeline_ui)

        self._send_to_top_of_select_order(timeline_ui)
        timeline_ui.on_left_click(item, modifier=modifier, double=double, x=x, y=y)

        if not self.is_dragging and not double:
            sb = SelectionBoxQt()
            timeline_ui.scene.addItem(sb)
            sb.setPos(x, y)
            self.selection_boxes = [sb]
            self.next_sbx_boundary_below = view.height()
            self.next_sbx_boundary_above = 0

    def _on_timeline_ui_left_drag(self, x: int, y: int) -> None:
        def create_selection_box_below():
            """
            Extends the selection box to the timeline below the current one
            """
            curr_timeline_ord = self._get_timeline_ui_by_scene(
                self.selection_boxes[-1].scene()
            ).get_data("ordinal")

            if curr_timeline_ord == len(self):
                # no more timelines below
                return

            next_timeline = get(Get.TIMELINE_BY_ATTR, "ordinal", curr_timeline_ord + 1)
            if next_timeline is None:
                return
            next_timeline_ui = get(Get.TIMELINE_UI_BY_ATTR, "id", next_timeline.id)

            new_sb = SelectionBoxQt()

            next_timeline_ui.scene.addItem(new_sb)
            new_sb.setPos(self.selection_boxes[-1].pos().x(), -1)
            self.selection_boxes.append(new_sb)

        def create_selection_box_above():
            curr_timeline_ord = self.get_timeline_ui_by_attr(
                "scene", self.selection_boxes[-1].scene()
            ).get_data("ordinal")

            if curr_timeline_ord == 1:
                # no more timelines above
                return

            next_timeline = get(Get.TIMELINE_BY_ATTR, "ordinal", curr_timeline_ord - 1)
            next_timeline_ui = get(Get.TIMELINE_UI_BY_ATTR, "id", next_timeline.id)

            new_sb = SelectionBoxQt()

            next_timeline_ui.scene.addItem(new_sb)
            new_sb.setPos(
                self.selection_boxes[-1].pos().x(), next_timeline.get_data("height") + 1
            )
            self.selection_boxes.append(new_sb)

        if self.is_dragging or not self.selection_boxes:
            return

        reference_tlui = get(
            Get.TIMELINE_UI_BY_ATTR, "scene", self.selection_boxes[0].scene()
        )
        global_point = reference_tlui.view.mapToGlobal(QPoint(x, y))

        for sb in self.selection_boxes:
            tlui = get(Get.TIMELINE_UI_BY_ATTR, "scene", sb.scene())
            local_point = tlui.view.mapFromGlobal(global_point)
            local_x = local_point.x()
            local_y = local_point.y()
            sb.on_drag(local_x, local_y)

        if y > self.next_sbx_boundary_below:
            if self.selection_boxes_above:
                self.selection_boxes = self.selection_boxes[:1]
                self.selection_boxes_above = False
                self.next_sbx_boundary_above = 0

            self.next_sbx_boundary_below = sum(
                [sbx.scene().height() for sbx in self.selection_boxes]
            )
            self.selection_boxes_below = True

            create_selection_box_below()
        elif y < self.next_sbx_boundary_above:
            if self.selection_boxes_below:
                self.selection_boxes = self.selection_boxes[:1]
                self.selection_boxes_below = False
                self.next_sbx_boundary_below = self.selection_boxes[0].scene().height()

            self.next_sbx_boundary_above = (
                sum([sbx.scene().height() for sbx in self.selection_boxes]) * -1
            )
            self.selection_boxes_above = True

            create_selection_box_above()

    def on_timeline_ui_left_released(self):
        self.clear_selection_boxes()

    def clear_selection_boxes(self):
        for sb in self.selection_boxes.copy():
            sb.scene().removeItem(sb)
            self.selection_boxes.remove(sb)

    def on_selection_box_select_item(
        self, scene: QGraphicsScene, item: QGraphicsItem
    ) -> None:
        timeline_ui = self._get_timeline_ui_by_scene(scene)

        try:
            element = timeline_ui.get_item_owner(item)[0]
        except IndexError:
            return

        was_selected = timeline_ui.select_element_if_selectable(element, item)

        # keep track of selection triggers under selection box
        if was_selected:
            if element in self.sb_items_to_selected_items:
                self.sb_items_to_selected_items[element].add(item)
            else:
                self.sb_items_to_selected_items[element] = {item}

    def on_selection_box_deselect_item(self, scene: QGraphicsScene, item: int) -> None:
        timeline_ui = self._get_timeline_ui_by_scene(scene)

        try:
            element = timeline_ui.get_item_owner(item)[0]
        except IndexError:
            # scene id does not belong to a timeline element (as in the playback line's
            # id) note that if the scene item belongs to multiple elements 'element'
            # will always hold the first one on the list returned
            return

        if item not in element.selection_triggers():
            return

        self.sb_items_to_selected_items[element].remove(item)

        # stop tracking element if there are no more selection triggers under
        # selection box
        if not self.sb_items_to_selected_items[element]:
            self.sb_items_to_selected_items.pop(element)
            timeline_ui.deselect_element(element)

    def on_arrow_press(self, arrow: str):
        direction = "horizontal" if arrow in ["right", "left"] else "vertical"
        for tlui in self:
            if direction == "horizontal" and tlui.ACCEPTS_HORIZONTAL_ARROWS:
                tlui.on_horizontal_arrow_press(arrow)
            if direction == "vertical" and tlui.ACCEPTS_VERTICAL_ARROWS:
                tlui.on_vertical_arrow_press(arrow)

    @staticmethod
    def on_hierarchy_selected():
        actions.get_qaction(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE).setVisible(
            True
        )

    def on_hierarchy_deselected(self):
        selected_hierarchies = []
        for tlui in self:
            if tlui.TIMELINE_KIND == TlKind.HIERARCHY_TIMELINE:
                selected_hierarchies += tlui.selected_elements
        if not selected_hierarchies:
            actions.get_qaction(TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE).setVisible(
                False
            )

    def on_hierarchy_merge_split(self, new_units: list, old_units: list):
        if (
            self.loop_delete_ignore.issuperset(set(old_units))
            and self.loop_time[0] != self.loop_time[1]
        ):
            self.loop_elements.update(new_units)
            self.loop_elements.difference_update(old_units)
            self.loop_delete_ignore.difference_update(old_units)
            self._update_loop_elements()

    def on_harmony_timeline_components_deserialized(self, id):
        self.get_timeline_ui(id).on_timeline_components_deserialized()  # noqa

    def on_loop_ignore_delete(self, tl_id: int, comp_id: int):
        self.loop_delete_ignore.add((tl_id, comp_id))

    def loop_cancel(self):
        self.loop_elements.clear()
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, False)
        self.on_loop_change(0, 0)

    def on_loop_cancel(self):
        self.update_loop_elements_ui(False)
        self.loop_time = (0, 0)
        self.change_loop_box_position()
        post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, False)

    def on_loop_toggle(self, is_looping):
        if is_looping:
            for tlui in self:
                if tlui.TIMELINE_KIND == TlKind.HIERARCHY_TIMELINE:
                    self.loop_elements.update(
                        [(tlui.id, element.id) for element in tlui.selected_elements]
                    )

            self._update_loop_elements()

        else:
            self.update_loop_elements_ui(False)
            self.on_loop_change(0, 0)

    def _update_loop_elements(self, clear=False) -> None:
        if self.loop_elements:
            connected, [start_time, end_time] = self._check_loop_continuity()
            if not connected:
                tilia.errors.display(tilia.errors.LOOP_DISJUNCT)
                post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, False)
                self.update_loop_elements_ui(False)
                self.on_loop_change(0, 0)
                return

            post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, True)
            self.update_loop_elements_ui(True)
            self.on_loop_change(start_time, end_time)

        elif clear:
            post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, False)
            self.on_loop_change(0, 0)

        else:
            post(Post.PLAYER_UI_UPDATE, PlayerToolbarElement.TOGGLE_LOOP, True)
            self.on_loop_change(0, get(Get.MEDIA_DURATION))

    def _check_loop_continuity(self) -> tuple[bool, list]:
        def dfs(index, cur_min, cur_max):
            if graph[index]["is_visited"]:
                return cur_min, cur_max

            graph[index]["is_visited"] = True
            for node in graph[index]["node"]:
                new_min, new_max = dfs(node, min(node, cur_min), max(node, cur_max))
                cur_min = min(new_min, cur_min)
                cur_max = max(new_max, cur_max)

            return cur_min, cur_max

        graph = {}
        elements = [
            self.get_timeline_ui(element_id[0]).get_element(element_id[1])
            for element_id in self.loop_elements
        ]
        for element in elements:
            if element.get_data("start") in graph:
                graph[element.get_data("start")]["node"].add(element.get_data("end"))
            else:
                graph[element.get_data("start")] = {
                    "is_visited": False,
                    "node": {element.get_data("end")},
                }

            if element.get_data("end") in graph:
                graph[element.get_data("end")]["node"].add(element.get_data("start"))
            else:
                graph[element.get_data("end")] = {
                    "is_visited": False,
                    "node": {element.get_data("start")},
                }

        connections = {}
        for i in graph:
            if not graph[i]["is_visited"]:
                min_time, max_time = dfs(i, i, i)
                connections[i] = [min_time, max_time]

        connector = next(iter(connections.values()))

        for i in connections:
            if (
                connector[0] < connections[i][0]
                and connector[1] > connections[i][0]
                and connector[1] < connections[i][1]
            ):
                connector[1] = connections[i][1]
            elif (
                connector[0] > connections[i][0]
                and connector[0] < connections[i][1]
                and connector[1] > connections[i][1]
            ):
                connector[0] = connections[i][0]
            elif (
                connector[0] <= connections[i][0] and connector[1] >= connections[i][1]
            ):
                pass
            elif connector[0] > connections[i][0] and connector[1] < connections[i][1]:
                connector[0] = connections[i][0]
                connector[1] = connections[i][1]
            else:
                return False, [0, 0]

        return True, connector

    def on_loop_change(self, start_time: float, end_time: float) -> None:
        self.loop_time = (start_time, end_time)
        post(Post.PLAYER_CURRENT_LOOP_CHANGED, start_time, end_time)
        self.change_loop_box_position()

    def change_loop_box_position(self):
        start_time, end_time = self.loop_time
        for tl_ui in self:
            tl_ui.scene.set_loop_box_position(
                get_x_by_time(start_time), get_x_by_time(end_time)
            )

    def update_loop_elements_ui(self, is_looping: bool) -> None:
        for element in [
            self.get_timeline_ui(element_id[0]).get_element(element_id[1])
            for element_id in self.loop_elements
        ]:
            element.on_loop_set(is_looping)

        if not is_looping:
            self.loop_elements.clear()

    def pre_process_timeline_request(
        self,
        request: Post,
        kinds: list[TlKind],
        selector: tilia.ui.timelines.collection.requests.timeline.TimelineSelector,
    ):
        timeline_uis = self.get_timelines_uis_for_request(kinds, selector)

        try:
            (
                args,
                kwargs,
            ) = tilia.ui.timelines.collection.requests.args.get_args_for_request(
                request, timeline_uis
            )
        except UserCancelledDialog:
            return None, None, None, False

        if not validate(request, timeline_uis, *args, **kwargs):
            return None, None, None, False

        return timeline_uis, args, kwargs, True

    @staticmethod
    def pre_process_timeline_uis_request(request, *args, **kwargs):
        args, kwargs = tilia.ui.timelines.collection.requests.args.get_args_for_request(
            request, [], *args, **kwargs
        )

        return args, kwargs, True

    def on_timeline_element_request(
        self,
        request: Post,
        selector: TlElmRequestSelector,
    ) -> None:
        timeline_uis, args, kwargs, success = self.pre_process_timeline_request(
            request, selector.tl_kind, selector.timeline
        )

        if not success:
            return

        result = []

        for tlui in timeline_uis:
            result.append(
                tlui.on_timeline_element_request(
                    request, selector.element, *args, **kwargs
                )
            )

        tilia.ui.timelines.collection.requests.post_process.post_process_request(
            request, result
        )
        if request not in self.DO_NOT_RECORD and not all([isinstance(r, RequestFailure) for r in result]):
            post(Post.APP_RECORD_STATE, f"timeline element request: {request.name}")

    def on_timeline_ui_request(self, request: Post, *args, **kwargs):
        args, kwargs, success = self.pre_process_timeline_uis_request(
            request, *args, **kwargs
        )
        if not success:
            return

        tilia.ui.timelines.collection.request_handler.TimelineUIsRequestHandler(
            self
        ).on_request(request, *args, **kwargs)

        if request not in self.DO_NOT_RECORD:
            post(Post.APP_RECORD_STATE, f"timeline element request: {request.name}")

    def on_timeline_request(self, request: Post, selector: TlRequestSelector):
        timeline_uis, args, kwargs, success = self.pre_process_timeline_request(
            request,
            selector.tl_kind,
            selector.timeline,
        )

        if not success:
            return

        result = []
        for tlui in timeline_uis:
            result.append(tlui.on_timeline_request(request, *args, **kwargs))

        tilia.ui.timelines.collection.requests.post_process.post_process_request(
            request, result
        )
        if request not in self.DO_NOT_RECORD:
            post(Post.APP_RECORD_STATE, f"timeline request: {request.name}")

    def get_timelines_uis_for_request(
        self, kinds: list[TlKind], selector: TimelineSelector
    ) -> list[TimelineUI]:
        def get_by_kinds(_kinds: list[TlKind]) -> list[TimelineUI]:
            return [tlui for tlui in self if tlui.TIMELINE_KIND in _kinds]

        def filter_if_has_selected_elements(
            timeline_uis: list[TimelineUI],
        ) -> list[TimelineUI]:
            return [tlui for tlui in timeline_uis if tlui.has_selected_elements]

        def filter_if_first_on_select_order(
            timeline_uis: list[TimelineUI],
        ) -> list[TimelineUI]:
            for tl_ui in self._select_order:
                if tl_ui in timeline_uis:
                    return [tl_ui]

        def filter_for_pasting(_) -> list[TimelineUI]:
            clipboard_data = get(Get.CLIPBOARD_CONTENTS)
            if not clipboard_data["components"]:
                return []

            timeline_uis = get_by_kinds([clipboard_data["timeline_kind"]])
            if any([tlui.has_selected_elements for tlui in timeline_uis]):
                return filter_if_has_selected_elements(timeline_uis)
            else:
                return filter_if_first_on_select_order(timeline_uis)

        def filter_if_from_manage_timelines_to_permute(_):
            return get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_TO_PERMUTE)

        def filter_if_from_manage_timelines_current(_):
            return [get(Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_CURRENT)]

        def filter_if_from_cli(_):
            return [get(Get.TIMELINES_FROM_CLI)]

        def filter_if_from_context_menu(_):
            return get(Get.CONTEXT_MENU_TIMELINE_UI)

        def filter_if_from_context_menu_to_permute(_):
            return get(Get.CONTEXT_MENU_TIMELINE_UIS_TO_PERMUTE)

        selector_to_func = {
            TimelineSelector.ALL: lambda x: x,
            TimelineSelector.FIRST: filter_if_first_on_select_order,
            TimelineSelector.SELECTED: filter_if_has_selected_elements,
            TimelineSelector.PASTE: filter_for_pasting,
            TimelineSelector.FROM_MANAGE_TIMELINES_TO_PERMUTE: filter_if_from_manage_timelines_to_permute,
            TimelineSelector.FROM_MANAGE_TIMELINES_CURRENT: filter_if_from_manage_timelines_current,
            TimelineSelector.FROM_CLI: filter_if_from_cli,
            TimelineSelector.ANY: filter_if_first_on_select_order,
            TimelineSelector.FROM_CONTEXT_MENU: filter_if_from_context_menu,
            TimelineSelector.FROM_CONTEXT_MENU_TO_PERMUTE: filter_if_from_context_menu_to_permute,
        }

        try:
            return selector_to_func[selector](get_by_kinds(kinds))
        except KeyError:
            raise NotImplementedError(f"Can't select with {selector=}")

    def on_zoom_in(self):
        post(
            Post.PLAYBACK_AREA_SET_WIDTH,
            get(Get.PLAYBACK_AREA_WIDTH) * (1 + self.ZOOM_FACTOR),
        )

    def on_zoom_out(self):
        post(
            Post.PLAYBACK_AREA_SET_WIDTH,
            get(Get.PLAYBACK_AREA_WIDTH) * (1 - self.ZOOM_FACTOR),
        )

    def _should_auto_scroll(self, media_time_change_reason) -> bool:
        return all(
            [
                not self.is_dragging,
                self.auto_scroll_is_enabled,
                media_time_change_reason != MediaTimeChangeReason.SEEK,
                not self.view.is_hscrollbar_pressed(),
            ]
        )

    def on_media_time_change(self, time: float, reason: MediaTimeChangeReason) -> None:
        if self._should_auto_scroll(reason):
            self.center_on_time(time)

        if not self.is_dragging:
            self.set_playback_lines_position(time)
            self.selected_time = time

    def set_is_dragging(self, is_dragging: bool) -> None:
        # noinspection PyAttributeOutsideInit
        self.is_dragging = is_dragging
        if is_dragging:
            self.clear_selection_boxes()

    def on_slider_drag(self, x: float):
        time = get_time_by_x(x)
        self.selected_time = time
        self.set_playback_lines_position(time)

    def set_auto_scroll(self, value: bool):
        settings.set("general", "auto-scroll", value)
        # noinspection PyAttributeOutsideInit
        self.auto_scroll_is_enabled = value

    def center_on_time(self, time: float):
        self.view.move_to_x(get_x_by_time(time))

    @staticmethod
    def change_playback_line_position(timeline_ui: TimelineUI, time: float):
        if timeline_ui.timeline.KIND == TlKind.SLIDER_TIMELINE:
            return

        timeline_ui.scene.set_playback_line_pos(get_x_by_time(time))

    def on_timelines_crop_done(self):
        for tlui in self:
            self.update_timeline_times(tlui)

    def deselect_all_elements_in_timeline_uis(self, excluding: TimelineUI):
        for timeline_ui in self:
            if timeline_ui == excluding:
                continue
            timeline_ui.deselect_all_elements()

        self.sb_items_to_selected_items = {}

    @staticmethod
    def kind_to_timeline():
        return {
            kind: len([tl for tl in get(Get.TIMELINES) if tl.KIND == kind])
            for kind in TlKind
        }

    def _hide_toolbar_if_needed(self, kind: TlKind):
        if kind in [TlKind.SLIDER_TIMELINE, TlKind.AUDIOWAVE_TIMELINE]:
            return
        if self.kind_to_timeline()[kind] == 0:
            self.kind_to_toolbar[kind].hide()

    def _show_toolbar(self, kind: TlKind):
        self.kind_to_toolbar[kind].show()

    def get_selected_time(self):
        return self.selected_time

    def get_loop_time(self):
        return self.loop_time

    def get_timeline_uis(self):
        return sorted(list(self._timeline_uis))

    def get_timeline_ui(self, tl_id: int) -> TimelineUI:
        try:
            return next(tlui for tlui in self if tlui.id == tl_id)
        except StopIteration:
            raise TimelineUINotFound(f"No timeline UI with id={tl_id}")

    def get_timeline_ui_element(self, timeline_id: int, element_id: int):
        return self.get_timeline_ui(timeline_id).get_element(element_id)

    def get_timeline_ui_by_attr(self, attr: str, value: Any) -> TimelineUI | None:
        return next((tlui for tlui in self if getattr(tlui, attr) == value), None)

    def get_timeline_uis_by_attr(self, attr: str, value: Any) -> list[TimelineUI]:
        return [tlui for tlui in self if getattr(tlui, attr) == value]

    def get_first_timeline_ui_in_select_order(self, kind: TimelineKind):
        return next(
            (tlui for tlui in self._select_order if tlui.get_data("KIND") == kind), None
        )

    def _get_choose_timeline_dialog(
        self,
        title: str,
        prompt: str,
        kind: TlKind | list[TlKind] | None = None,
    ) -> ChooseDialog:
        if kind and not isinstance(kind, list):
            kind = [kind]

        options = [
            (str(tlui), tlui)
            for tlui in sorted(self)
            if ((tlui.TIMELINE_KIND in kind) if kind else True)
        ]

        return ChooseDialog(self.main_window, title, prompt, options)

    def ask_choose_timeline(
        self,
        title: str,
        prompt: str,
        kind: TlKind | list[TlKind] | None = None,
    ) -> Optional[Timeline] | None:
        """
        Opens a dialog where the user may choose an existing timeline.
        Choices are restricted to the kinds in 'kind'. If no kind is passed,
        all kinds are considered.
        """

        dialog = self._get_choose_timeline_dialog(title, prompt, kind)
        success = dialog.exec()

        if not success:
            return

        return dialog.get_option()

    def get_timeline_elements_selected(self):
        return [tlui for tlui in self if tlui.has_selected_elements]

    def on_component_event(
        self,
        event: Post,
        _: TlKind,
        tl_id: int,
        component_id: int,
        *args,
        **kwargs,
    ):
        event_to_callback = {}

        tlui = self.get_timeline_ui(tl_id)

        event_to_callback[event](tlui, component_id, *args, **kwargs)

    def on_timeline_event(self, event: Post, tl_id: int, *args, **kwargs):
        event_to_callback = {}
        tlui = self.get_timeline_ui(tl_id)

        event_to_callback[event](tlui, *args, **kwargs)

    def on_timeline_created(self, kind: TlKind, id: int):
        self.create_timeline_ui(kind, id)

    def on_timeline_deleted(self, id: int):
        self.delete_timeline_ui(self.get_timeline_ui(id))
