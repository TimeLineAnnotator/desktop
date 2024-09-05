from typing import Optional

import typing
from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
)

from tilia.requests import (
    Post,
    post,
    Get,
    get,
    listen,
    serve,
    stop_listening_to_all,
    stop_serving_all,
)
from tilia.timelines.base.timeline import TimelineFlag
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.timeline import TimelineUI


class ManageTimelines(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manage Timelines")
        self._setup_widgets()
        self._setup_checkbox()
        self._setup_requests()
        self.show()

    def _setup_widgets(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        list_widget = TimelinesListWidget()
        self.list_widget = list_widget
        list_widget.currentItemChanged.connect(self.on_list_current_item_changed)
        layout.addWidget(list_widget)

        right_layout = QVBoxLayout()

        self.up_button = QPushButton("▲")
        self.up_button.pressed.connect(list_widget.on_up_button)

        self.down_button = QPushButton("▼")
        self.down_button.pressed.connect(list_widget.on_down_button)

        checkbox = QCheckBox("Visible")
        self.checkbox = checkbox
        checkbox.stateChanged.connect(self.on_checkbox_state_changed)

        self.delete_button = QPushButton("Delete")
        self.delete_button.pressed.connect(list_widget.on_delete_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.pressed.connect(list_widget.on_clear_button)
        right_layout.addWidget(self.up_button)
        right_layout.addWidget(self.down_button)
        right_layout.addWidget(checkbox)
        right_layout.addWidget(self.clear_button)
        right_layout.addWidget(self.delete_button)

        layout.addLayout(right_layout)

    def _setup_requests(self):        
        SERVES = {
            (Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_TO_PERMUTE, self.get_timeline_uis_to_permute),
            (Get.WINDOW_MANAGE_TIMELINES_TIMELINE_UIS_CURRENT, self.get_current_timeline_ui)
        }

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_checkbox(self):
        self.on_list_current_item_changed(self.list_widget.currentItem())

    def on_list_current_item_changed(self, item):
        if not item:
            return

        timeline = get(Get.TIMELINE, item.timeline_ui.id)

        self.checkbox.setCheckState(
            Qt.CheckState.Checked
            if timeline.get_data("is_visible")
            else Qt.CheckState.Unchecked
        )
        self.delete_button.setEnabled(TimelineFlag.NOT_DELETABLE not in timeline.FLAGS)
        self.clear_button.setEnabled(TimelineFlag.NOT_CLEARABLE not in timeline.FLAGS)

    def on_checkbox_state_changed(self, state):
        item = self.list_widget.currentItem()
        if not item:
            return
        timeline_ui = item.timeline_ui
        if timeline_ui.get_data("is_visible") != bool(state):
            post(Post.TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES)

    def get_timeline_uis_to_permute(self):
        return self.list_widget.timeline_uis_to_permute

    def get_current_timeline_ui(self):
        return self.list_widget.currentItem().timeline_ui

    def closeEvent(self, a0: Optional[QtGui.QCloseEvent]) -> None:
        super().closeEvent(a0)
        stop_listening_to_all(self)
        stop_listening_to_all(self.list_widget)
        stop_serving_all(self)
        post(Post.WINDOW_MANAGE_TIMELINES_CLOSE_DONE)


class TimelineListItem(QListWidgetItem):
    def __init__(self, timeline_ui: TimelineUI):
        self.timeline_ui = timeline_ui
        super().__init__(self.get_timeline_ui_str(timeline_ui))

    @staticmethod
    def get_timeline_ui_str(timeline_ui: TimelineUI):
        if timeline_ui.TIMELINE_KIND == TimelineKind.SLIDER_TIMELINE:
            return "Slider"
        return timeline_ui.get_data("name")


class TimelinesListWidgetItem(QListWidgetItem):
    timeline_ui: TimelineUI


class TimelinesListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self._setup_items()

        self.setCurrentRow(0)
        self.timeline_uis_to_permute = None
        self._setup_requests()

    def _setup_requests(self):
        LISTENS = {
            (Post.TIMELINE_SET_DATA_DONE, self.on_timeline_set_data_done),
            (Post.TIMELINE_DELETE_DONE, self.update_current_selection),
            (Post.TIMELINE_CREATE_DONE, self.update_current_selection),
        }

        for post, callback in LISTENS:
            listen(self, post, callback)

    def item(self, row: int) -> typing.Optional[TimelineListItem]:
        return super().item(row)

    def currentItem(self) -> typing.Optional[TimelineListItem]:
        return super().currentItem()

    def selectedItems(self) -> list[TimelineListItem]:
        return super().selectedItems()

    def _setup_items(self):
        for tl in get(Get.TIMELINE_UIS):
            self.addItem(TimelineListItem(tl))

    def on_timeline_set_data_done(self, _, attr, __):
        if attr != "ordinal":
            return

        prev_selected = self.currentItem() or self.item(0)
        self.update_items()
        for i in range(self.model().rowCount()):
            if self.item(i).timeline_ui == prev_selected.timeline_ui:
                self.setCurrentRow(i)
                break

    def update_current_selection(self, *_):
        prev_index = self.currentIndex()
        self.update_items()
        self.setCurrentRow(prev_index.row())

    def update_items(self):
        self.clear()
        self._setup_items()

    def on_up_button(self):
        if not self.selectedIndexes():
            return

        selected = self.selectedItems()[0]
        index = self.selectedIndexes()[0].row()
        previous = self.item(index - 1)
        if previous:
            self.timeline_uis_to_permute = (selected.timeline_ui, previous.timeline_ui)
            post(Post.TIMELINE_ORDINAL_DECREASE_FROM_MANAGE_TIMELINES)
            self.timeline_uis_to_permute = None

    def on_down_button(self):
        if not self.selectedIndexes():
            return
        selected = self.selectedItems()[0]
        index = self.selectedIndexes()[0].row()
        next_item = self.item(index + 1)
        if next_item:
            self.timeline_uis_to_permute = (selected.timeline_ui, next_item.timeline_ui)
            post(Post.TIMELINE_ORDINAL_INCREASE_FROM_MANAGE_TIMELINES)
            self.timeline_uis_to_permute = None

    @staticmethod
    def on_delete_button():
        post(Post.TIMELINE_DELETE_FROM_MANAGE_TIMELINES)

    @staticmethod
    def on_clear_button():
        post(Post.TIMELINE_CLEAR_FROM_MANAGE_TIMELINES)
