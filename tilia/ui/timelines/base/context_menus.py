from PyQt6.QtGui import QAction
from tilia.ui.actions import TiliaAction
from tilia.ui.menus import MenuItemKind, TiliaMenu
from tilia.ui.timelines.dialogs import confirm_delete_timeline
from tilia.requests import get, Get, serve, post, Post


class TimelineUIContextMenu(TiliaMenu):
    title = "Timeline"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_NAME_SET),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_HEIGHT_SET),
    ]

    def __init__(self, timeline_ui):
        super().__init__()
        self.timeline_ui = timeline_ui
        self.timeline_uis_to_permute = None
        self._setup_requests()
        self._add_timeline_actions()

    def _setup_requests(self):
        SERVES = {
            (
                Get.CONTEXT_MENU_TIMELINE_UIS_TO_PERMUTE,
                self.get_timeline_uis_to_permute,
            ),
        }

        for request, callback in SERVES:
            serve(self, request, callback)

    def _add_timeline_actions(self):
        self.addSeparator()

        self.check_move_up()
        self.check_move_down()
        self.add_delete_timeline()

    def get_timeline_uis_to_permute(self):
        return self.timeline_uis_to_permute

    def check_move_up(self):
        def on_move_up():
            self.timeline_uis_to_permute = (
                self.timeline_ui,
                indices_to_timelines[current_index - 1],
            )
            post(Post.TIMELINE_ORDINAL_INCREASE_FROM_CONTEXT_MENU)

        current_index = self.timeline_ui.get_data("ordinal")
        indices_to_timelines = {
            tlui.get_data("ordinal"): tlui for tlui in get(Get.TIMELINE_UIS)
        }
        if indices_to_timelines.get(current_index - 1, False):
            move_up = QAction("Move timeline up", self)
            move_up.triggered.connect(on_move_up)
            self.addAction(move_up)

    def check_move_down(self):
        def on_move_down():
            self.timeline_uis_to_permute = (
                self.timeline_ui,
                indices_to_timelines[current_index + 1],
            )
            post(Post.TIMELINE_ORDINAL_DECREASE_FROM_CONTEXT_MENU)

        current_index = self.timeline_ui.get_data("ordinal")
        indices_to_timelines = {
            tlui.get_data("ordinal"): tlui for tlui in get(Get.TIMELINE_UIS)
        }
        if indices_to_timelines.get(current_index + 1, False):
            move_down = QAction("Move timeline down", self)
            move_down.triggered.connect(on_move_down)
            self.addAction(move_down)

    def add_delete_timeline(self):
        def on_delete():
            if confirm_delete_timeline(self.timeline_ui.get_data("name")):
                get(Get.TIMELINE_COLLECTION).delete_timeline(self.timeline_ui.timeline)

        delete_timeline = QAction("Delete timeline", self)
        delete_timeline.triggered.connect(on_delete)
        self.addAction(delete_timeline)


class TimelineUIElementContextMenu(TiliaMenu):
    title = "TimelineElement"
    items = []

    def __init__(self, element):
        super().__init__()
        self.element = element
