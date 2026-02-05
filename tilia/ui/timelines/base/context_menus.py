from tilia.ui import commands
from tilia.ui.commands import get_qaction, CommandQAction
from tilia.ui.menus import MenuItemKind, TiliaMenu
from tilia.requests import get, Get


class TimelineUIContextMenu(TiliaMenu):
    title = "Timeline"
    items = [
        (MenuItemKind.COMMAND, "timeline.set_name"),
        (MenuItemKind.COMMAND, "timeline.set_height"),
    ]

    def __init__(self, timeline_ui):
        super().__init__()
        self.timeline_ui = timeline_ui
        self._add_timeline_actions()

    def _add_timeline_actions(self):
        self.addSeparator()

        self.check_move_up()
        self.check_move_down()
        self.add_default_actions()

    def get_timeline_ui_for_selector(self):
        return [self.timeline_ui]

    def add_action(self, name: str):
        action = get_qaction(name)
        action.triggered.disconnect()
        action.triggered.connect(lambda: commands.execute(name, self.timeline_ui))
        self.addAction(action)

    def check_move_up(self):
        def on_move_up():
            commands.execute(
                "timelines.permute_ordinal",
                self.timeline_ui,
                indices_to_timelines[current_index - 1],
            )

        current_index = self.timeline_ui.get_data("ordinal")
        indices_to_timelines = {
            tlui.get_data("ordinal"): tlui for tlui in get(Get.TIMELINE_UIS)
        }
        if indices_to_timelines.get(current_index - 1, False):
            move_up = CommandQAction("timeline.move_up", self)
            move_up.setText("Move up")
            move_up.triggered.connect(on_move_up)
            self.addAction(move_up)

    def check_move_down(self):
        def on_move_down():
            commands.execute(
                "timelines.permute_ordinal",
                self.timeline_ui,
                indices_to_timelines[current_index + 1],
            )

        current_index = self.timeline_ui.get_data("ordinal")
        indices_to_timelines = {
            tlui.get_data("ordinal"): tlui for tlui in get(Get.TIMELINE_UIS)
        }
        if indices_to_timelines.get(current_index + 1, False):
            move_down = CommandQAction("timeline.move_down", self)
            move_down.setText("Move down")
            move_down.triggered.connect(on_move_down)
            self.addAction(move_down)

    def add_default_actions(self):
        # I wasn't able to make this work with functools.partial,
        # so I'm defining these functions.
        def on_delete_timeline():
            commands.execute("timeline.delete", self.timeline_ui)

        def on_clear_timeline():
            commands.execute("timeline.clear", self.timeline_ui)

        self.addSeparator()

        delete_timeline = CommandQAction("timeline.delete", self)
        delete_timeline.setText("Delete")
        delete_timeline.triggered.connect(on_delete_timeline)
        self.addAction(delete_timeline)

        clear_timeline = CommandQAction("timeline.clear", self)
        clear_timeline.setText("Clear")
        clear_timeline.triggered.connect(on_clear_timeline)
        self.addAction(clear_timeline)


class TimelineUIElementContextMenu(TiliaMenu):
    title = "TimelineElement"
    items = []

    def __init__(self, element):
        super().__init__()
        self.element = element
