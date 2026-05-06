from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tilia.requests import Get, Post, get, listen
from tilia.settings import settings
from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui import commands
from tilia.ui.timelines.toolbar import TimelineToolbar

VALID_LABEL_ALIGNMENTS = ("left", "center", "right")


class _ToolbarSection(QWidget):
    """A ribbon-style group: a row of action buttons with a section label
    underneath."""

    def __init__(
        self,
        label_text: str,
        actions: list[QAction],
        icon_size,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)
        for action in actions:
            btn = QToolButton(button_row)
            btn.setDefaultAction(action)
            btn.setIconSize(icon_size)
            button_layout.addWidget(btn)
        layout.addWidget(button_row, 0, Qt.AlignmentFlag.AlignHCenter)

        label = QLabel(label_text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # No explicit color — inherits from the widget palette so the label
        # is legible in both light and dark themes.
        label.setStyleSheet("QLabel { font-size: 10px; padding: 0 4px; }")
        layout.addWidget(label)


class RangeTimelineToolbar(TimelineToolbar):
    # COMMANDS is left empty so the base class skips its sequential addAction
    # loop; we build the toolbar manually below in labelled groups.
    COMMANDS = []

    GROUPS = [
        (
            "Ranges",
            [
                "timeline.range.add_range",
                "timeline.range.join_ranges",
                "timeline.range.separate_ranges",
                "timeline.range.merge_ranges",
                "timeline.range.split_range",
            ],
        ),
        (
            "Rows",
            [
                "timeline.range.add_row_above",
                "timeline.range.add_row_below",
                "timeline.range.remove_row",
            ],
        ),
        (
            "Display",
            [
                "timeline.range.align_labels_left",
                "timeline.range.align_labels_center",
                "timeline.range.align_labels_right",
                "timeline.range.toggle_always_show_extensions",
            ],
        ),
    ]

    SPLIT_MODE_COMMAND_BY_ALL_ROWS = {
        True: "timeline.range.set_split_mode_all_rows",
        False: "timeline.range.set_split_mode_selected_row",
    }
    SPLIT_MODE_LABEL_BY_ALL_ROWS = {
        True: "All rows",
        False: "Selected row",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the section separator visible across themes — the default 1-px
        # mid-grey line nearly disappears against a dark toolbar.
        self.setStyleSheet(
            "QToolBar::separator { background: palette(mid); "
            "width: 2px; margin: 4px 8px; }"
        )
        listen(self, Post.TIMELINE_UI_SELECTED, self._on_timeline_ui_selected)
        listen(self, Post.TIMELINE_SET_DATA_DONE, self._on_timeline_data_set)
        listen(self, Post.SETTINGS_UPDATED, self._on_settings_updated)
        self._setup_alignment_actions()
        self._setup_always_show_extensions_action()
        self._build_grouped_toolbar()
        self._split_mode_button = self._build_split_mode_button()
        self.addSeparator()
        self.addWidget(self._split_mode_button)
        self._refresh_remove_row_enabled()
        self._refresh_alignment_checked()
        self._refresh_always_show_extensions_checked()
        self._refresh_split_mode_checked()

    def _build_grouped_toolbar(self) -> None:
        for i, (label_text, command_names) in enumerate(self.GROUPS):
            if i > 0:
                self.addSeparator()
            actions = [commands.get_qaction(name) for name in command_names]
            section = _ToolbarSection(label_text, actions, self.iconSize(), self)
            self.addWidget(section)

    def _on_timeline_ui_selected(self, _tl_ui) -> None:
        self._refresh_remove_row_enabled()

    def _on_timeline_data_set(self, _tl_id, attr, _value) -> None:
        if attr == "rows":
            self._refresh_remove_row_enabled()

    def _on_settings_updated(self, updated_settings) -> None:
        if "range_timeline" in updated_settings:
            self._refresh_alignment_checked()
            self._refresh_always_show_extensions_checked()
            self._refresh_split_mode_checked()

    def _setup_alignment_actions(self) -> None:
        for alignment in VALID_LABEL_ALIGNMENTS:
            action = commands.get_qaction(f"timeline.range.align_labels_{alignment}")
            action.setCheckable(True)

    def _refresh_remove_row_enabled(self) -> None:
        # The QAction is shared across all range timelines, so the button
        # reflects the most-recently-active range timeline (= first range
        # timeline in the timeline-uis collection's select order).
        active = get(Get.FIRST_TIMELINE_UI_IN_SELECT_ORDER, RangeTimeline)
        action = commands.get_qaction("timeline.range.remove_row")
        if active is None:
            action.setEnabled(False)
            return
        action.setEnabled(active.timeline.row_count > 1)

    def _refresh_alignment_checked(self) -> None:
        current = settings.get("range_timeline", "default_label_alignment")
        for alignment in VALID_LABEL_ALIGNMENTS:
            action = commands.get_qaction(f"timeline.range.align_labels_{alignment}")
            action.setChecked(alignment == current)

    def _setup_always_show_extensions_action(self) -> None:
        action = commands.get_qaction("timeline.range.toggle_always_show_extensions")
        action.setCheckable(True)

    def _refresh_always_show_extensions_checked(self) -> None:
        action = commands.get_qaction("timeline.range.toggle_always_show_extensions")
        action.setChecked(
            bool(settings.get("range_timeline", "always_show_extensions"))
        )

    def _build_split_mode_button(self) -> QToolButton:
        # Custom dropdown (instead of the standard COMMAND list entry) so the
        # two split-mode options behave as exclusive radio items under a
        # single labelled toolbar button whose label reflects the active mode.
        all_rows_action = commands.get_qaction(
            self.SPLIT_MODE_COMMAND_BY_ALL_ROWS[True]
        )
        selected_row_action = commands.get_qaction(
            self.SPLIT_MODE_COMMAND_BY_ALL_ROWS[False]
        )
        all_rows_action.setText(self.SPLIT_MODE_LABEL_BY_ALL_ROWS[True])
        selected_row_action.setText(self.SPLIT_MODE_LABEL_BY_ALL_ROWS[False])
        for action in (all_rows_action, selected_row_action):
            action.setCheckable(True)

        group = QActionGroup(self)
        group.setExclusive(True)
        group.addAction(all_rows_action)
        group.addAction(selected_row_action)

        menu = QMenu(self)
        menu.addAction(all_rows_action)
        menu.addAction(selected_row_action)

        button = QToolButton(self)
        button.setToolTip("Split mode")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        return button

    def _refresh_split_mode_checked(self) -> None:
        all_rows = bool(settings.get("range_timeline", "split_all_rows"))
        for is_all_rows, command in self.SPLIT_MODE_COMMAND_BY_ALL_ROWS.items():
            commands.get_qaction(command).setChecked(is_all_rows == all_rows)
        self._split_mode_button.setText(
            f"Split: {self.SPLIT_MODE_LABEL_BY_ALL_ROWS[all_rows].lower()}"
        )
