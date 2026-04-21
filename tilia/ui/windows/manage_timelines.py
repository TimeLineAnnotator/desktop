from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from tilia.requests import (
    Get,
    Post,
    get,
    listen,
    post,
    stop_listening_to_all,
    stop_serving_all,
)
from tilia.timelines.base.timeline import TimelineFlag
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui import commands
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.windows import WindowKind


class ManageTimelines(QDialog):
    def __init__(self):
        super().__init__(get(Get.MAIN_WINDOW))
        self.setWindowTitle("Manage Timelines")
        self._setup_widgets()
        self._setup_checkbox()
        self.show()

        post(Post.WINDOW_OPEN_DONE, WindowKind.MANAGE_TIMELINES)

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
            commands.execute("timeline.set_is_visible", timeline_ui, bool(state))

    def get_current_timeline_ui(self):
        return self.list_widget.currentItem().timeline_ui

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        super().closeEvent(a0)
        stop_listening_to_all(self)
        stop_listening_to_all(self.list_widget)
        stop_serving_all(self)
        post(Post.WINDOW_CLOSE_DONE, WindowKind.MANAGE_TIMELINES)


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
        self._setup_requests()

    def _setup_requests(self):
        LISTENS = {
            (Post.TIMELINE_SET_DATA_DONE, self.on_timeline_set_data_done),
            (Post.TIMELINE_DELETE_DONE, self.update_current_selection),
            (Post.TIMELINE_CREATE_DONE, self.update_current_selection),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

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
        prev_index = self.currentIndex().row()
        self.update_items()
        if prev_index < self.model().rowCount():
            self.setCurrentRow(prev_index)
        else:  # rows are 0-indexed; if prev_index is more than the number of rows, use the last row.
            self.setCurrentRow(max(0, self.model().rowCount() - 1))

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
            commands.execute(
                "timelines.permute_ordinal", selected.timeline_ui, previous.timeline_ui
            )

    def on_down_button(self):
        if not self.selectedIndexes():
            return
        selected = self.selectedItems()[0]
        index = self.selectedIndexes()[0].row()
        next_item = self.item(index + 1)
        if next_item:
            commands.execute(
                "timelines.permute_ordinal", selected.timeline_ui, next_item.timeline_ui
            )

    @property
    def selected_timeline_ui(self):
        return self.selectedItems()[0].timeline_ui

    def on_delete_button(self):
        commands.execute("timeline.delete", self.selected_timeline_ui)

    def on_clear_button(self):
        commands.execute("timeline.clear", self.selected_timeline_ui)
