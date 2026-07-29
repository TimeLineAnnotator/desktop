import functools

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

from tilia.requests import Post, listen
from tilia.settings import settings
from tilia.ui import commands
from tilia.ui.timelines.toolbar import TimelineToolbar

VALID_LABEL_ALIGNMENTS = ("left", "center", "right")


class _ButtonRow(QWidget):
    """A row of action buttons. Items are either QActions (rendered as a
    plain button with that action) or pre-built QToolButtons (e.g. a
    dropdown)."""

    def __init__(
        self,
        items: list[QAction | QToolButton],
        icon_size,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for item in items:
            if isinstance(item, QAction):
                btn = QToolButton(self)
                btn.setDefaultAction(item)
            else:
                btn = item
                btn.setParent(self)
            btn.setIconSize(icon_size)
            layout.addWidget(btn)


class RangeTimelineToolbar(TimelineToolbar):
    # COMMANDS is left empty so the base class skips its sequential addAction
    # loop; we build the toolbar manually below in separator-divided groups.
    COMMANDS = []

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
        # mid-grey line nearly disappears against a dark toolbar. Same for the
        # dropdown buttons' menu-arrow area: give it a visible divider and
        # force the arrow onto the CSS renderer so it actually shows up
        # (palette-based, so it stays correct in both light and dark themes).
        self.setStyleSheet(
            "QToolBar::separator { background: palette(mid); "
            "width: 2px; margin: 4px 8px; }"
            "QToolButton::menu-button { border-left: 1px solid palette(mid); "
            "width: 14px; }"
            "QToolButton::menu-arrow { width: 8px; height: 8px; }"
        )
        listen(self, Post.SETTINGS_UPDATED, self._on_settings_updated)
        self._build_ranges_section()
        self.addSeparator()
        self._build_rows_section()
        self._split_mode_button = self._build_split_mode_button()
        self.addSeparator()
        self.addWidget(self._split_mode_button)
        self._refresh_split_mode_checked()

    def _build_ranges_section(self) -> None:
        add_action = commands.get_qaction("timeline.range.add_range")
        join_merge = self._build_action_dropdown(
            ["timeline.range.join_ranges", "timeline.range.merge_ranges"],
        )
        separate_split = self._build_action_dropdown(
            ["timeline.range.separate_ranges", "timeline.range.split_range"],
        )
        section = _ButtonRow(
            [add_action, join_merge, separate_split], self.iconSize(), self
        )
        self.addWidget(section)

    def _build_rows_section(self) -> None:
        add_row = self._build_action_dropdown(
            ["timeline.range.add_row_above", "timeline.range.add_row_below"],
        )
        section = _ButtonRow([add_row], self.iconSize(), self)
        self.addWidget(section)

    def _build_action_dropdown(self, command_names: list[str]) -> QToolButton:
        # MenuButtonPopup: the main button area re-runs whichever action was
        # used last (starting with the first), the small arrow area opens
        # the menu to pick a different one. "Last used" is session-only —
        # these are one-shot, order-symmetric actions, unlike alignment/
        # split-mode's settings-backed persistent state below.
        actions = [commands.get_qaction(name) for name in command_names]

        button = QToolButton(self)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        menu = QMenu(self)
        for action in actions:
            menu.addAction(action)
            action.triggered.connect(functools.partial(button.setDefaultAction, action))
        button.setMenu(menu)
        button.setDefaultAction(actions[0])
        return button

    def _on_settings_updated(self, updated_settings) -> None:
        if "range_timeline" in updated_settings:
            self._refresh_split_mode_checked()

    def _build_split_mode_button(self) -> QToolButton:
        # A plain checkable toggle: split mode is a binary choice (all rows
        # vs. selected row), so the QActionGroup+QMenu dropdown this used to
        # be is unnecessary complexity — one click instead of two, no popup.
        button = QToolButton(self)
        button.setToolTip("Split mode")
        button.setCheckable(True)
        button.clicked.connect(self._on_split_mode_toggled)
        return button

    def _on_split_mode_toggled(self, checked: bool) -> None:
        commands.execute(self.SPLIT_MODE_COMMAND_BY_ALL_ROWS[checked])

    def _refresh_split_mode_checked(self) -> None:
        all_rows = bool(settings.get("range_timeline", "split_all_rows"))
        self._split_mode_button.setChecked(all_rows)
        self._split_mode_button.setText(
            f"Split: {self.SPLIT_MODE_LABEL_BY_ALL_ROWS[all_rows].lower()}"
        )
