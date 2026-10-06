"""Every route to a command runs that command.

`commands.register()` creates one CommandQAction per command and connects it
to `commands.execute(name)`. Menus, toolbars and context menus reuse that
action through `commands.get_qaction(name)`, so their routes are right by
construction. What can still go wrong is a surface that builds its own
CommandQAction or rewires a shared one. So instead of listing routes by hand,
these tests find every CommandQAction on every surface, trigger it with
`commands.execute` patched, and check that it runs the command it's named
after. A new command needs no change here.

Controls that aren't CommandQActions (plain QActions and widgets wired
straight to a method, like the player toolbar's volume slider) aren't covered.
"""

from unittest.mock import patch

from PySide6.QtWidgets import QToolBar, QWidget

from tilia.requests import Get, get
from tilia.ui import commands
from tilia.ui.commands import CommandQAction

# CommandQActions whose name isn't the command they run. Each entry must still
# be wrong, so fixing one fails test_known_mismatches_are_still_wrong as a
# reminder to remove it here.
KNOWN_MISMATCHES = {
    # TimelineUIContextMenu.check_move_up/down name their actions after
    # commands that don't exist, and run timelines.permute_ordinal instead.
    "timeline.move_up",
    "timeline.move_down",
}


def _command_actions(widget: QWidget) -> list[CommandQAction]:
    actions = []
    for action in widget.actions():
        if isinstance(action, CommandQAction):
            actions.append(action)
        if action.menu():
            actions += _command_actions(action.menu())
    return actions


def _executed_command(action: CommandQAction) -> str | None:
    """Triggers `action` without running anything and returns the command it
    asked to execute, or None if it asked for none."""
    was_enabled, was_checked = action.isEnabled(), action.isChecked()
    action.setEnabled(True)  # Whether it's enabled is behaviour, not wiring.
    with patch.object(commands, "execute") as execute:
        action.trigger()
    action.setEnabled(was_enabled)
    if action.isCheckable():
        action.blockSignals(True)
        action.setChecked(was_checked)
        action.blockSignals(False)
    return execute.call_args.args[0] if execute.called else None


def _wrongly_wired(actions: list[CommandQAction]) -> dict[str, str | None]:
    """Maps each action's name to the command it ran instead, if any."""
    wrong = {}
    for action in actions:
        name = action.command_name
        if name in KNOWN_MISMATCHES:
            continue
        executed = _executed_command(action)
        if executed != name:
            wrong[name] = executed
    return wrong


def _context_menu_actions(tluis: list, elements: list) -> list[CommandQAction]:
    actions = []
    for tlui in tluis:
        if tlui.CONTEXT_MENU_CLASS:
            actions += _command_actions(tlui.CONTEXT_MENU_CLASS(tlui, 0, 0))
    for element in elements:
        if element.CONTEXT_MENU_CLASS:
            actions += _command_actions(element.CONTEXT_MENU_CLASS(element))
    return actions


def _one_element_of_each_kind(
    beat_tlui,
    harmony_tlui,
    hierarchy_tlui,
    marker_tlui,
    pdf_tlui,
    range_tlui,
    note_ui,
) -> list:
    commands.execute("timeline.beat.add", time=1)
    commands.execute("timeline.hierarchy.add", start=10, end=20, level=2)
    commands.execute("media.seek", 5)
    commands.execute("timeline.marker.add")
    commands.execute("timeline.pdf.add")
    commands.execute("timeline.range.add_range", start=10, end=20)
    harmony_tlui.create_harmony(time=1)
    harmony_tlui.create_mode(time=2)
    return [
        beat_tlui[0],
        hierarchy_tlui[0],
        marker_tlui[0],
        pdf_tlui[0],
        range_tlui[0],
        harmony_tlui.harmonies()[0],
        harmony_tlui.modes()[0],
        note_ui,
    ]


def test_registered_actions_run_their_command(qtui):
    actions = [
        commands.get_qaction(name)
        for name, callback in commands._name_to_callback.items()
        if callback
    ]

    assert _wrongly_wired(actions) == {}


def test_menu_actions_run_their_command(qtui):
    actions = _command_actions(get(Get.MAIN_WINDOW).menuBar())
    assert actions

    assert _wrongly_wired(actions) == {}


def test_toolbar_actions_run_their_command(
    qtui,
    audiowave_tlui,
    beat_tlui,
    harmony_tlui,
    hierarchy_tlui,
    marker_tlui,
    pdf_tlui,
    range_tlui,
    score_tlui,
):
    toolbars = get(Get.MAIN_WINDOW).findChildren(QToolBar)
    toolbars += score_tlui.get_or_create_svg_view().findChildren(QToolBar)
    actions = [a for toolbar in toolbars for a in _command_actions(toolbar)]
    assert actions

    assert _wrongly_wired(actions) == {}


def test_context_menu_actions_run_their_command(
    qtui,
    tilia_state,
    audiowave_tlui,
    beat_tlui,
    harmony_tlui,
    hierarchy_tlui,
    marker_tlui,
    pdf_tlui,
    range_tlui,
    score_tlui,
    note_ui,
    tluis,
):
    tilia_state.duration = 100
    elements = _one_element_of_each_kind(
        beat_tlui,
        harmony_tlui,
        hierarchy_tlui,
        marker_tlui,
        pdf_tlui,
        range_tlui,
        note_ui,
    )
    actions = _context_menu_actions(list(tluis), elements)
    assert actions

    assert _wrongly_wired(actions) == {}


def test_known_mismatches_are_still_wrong(qtui, marker_tlui, hierarchy_tlui, tluis):
    actions = _context_menu_actions(list(tluis), [])
    mismatched = {
        a.command_name
        for a in actions
        if a.command_name in KNOWN_MISMATCHES and _executed_command(a) != a.command_name
    }

    assert mismatched == KNOWN_MISMATCHES


def test_no_ambiguous_shortcuts():
    """Qt ignores a shortcut that two active actions share. The app resolves
    the known cross-kind collisions (e.g. hierarchy and range both binding "s"
    to split) through TimelineUIs.on_shared_shortcut_fired, which dispatches
    only when every bound name is `timeline.<kind>.*` with a distinct kind.
    Check every registered shortcut against that rule, so a new collision
    fails here instead of silently doing nothing at runtime."""
    for shortcut, names in commands._shortcut_to_commands.items():
        if len(names) <= 1:
            continue
        kinds = [".".join(name.split(".", 2)[:2]) for name in names]
        assert all(
            name.startswith("timeline.") for name in names
        ), f"{shortcut!r} is shared by a command outside a timeline: {names}"
        assert len(set(kinds)) == len(
            kinds
        ), f"{shortcut!r} is shared by two commands of the same kind: {names}"
