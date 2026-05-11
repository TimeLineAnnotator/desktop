"""
This module provides a way to register and execute reusable commands.
Commands are the primary way to handle user interactions that modify the application state.

Note that commands should only be used for operations that could be initiated by the user.
For internal communication between components, use `tilia.requests.post()` and `tilia.requests.get()` instead.

Naming conventions for commands:
- Use snake_case.
- Use nested categories and separate with dots (e.g., 'timeline.component.copy').
- Group related commands under same category (e.g., 'file.open', 'file.save').

Examples:
- File commands:        'file.open', 'file.save', 'file.export.img'
- Timeline commands:    'timeline.delete', 'timeline.component.copy'
- View commands:        'view.zoom.in', 'view.zoom.out'

Usage:
    # Register a new command
    commands.register(
        'example.command',
        callback_function,
        text='Menu Text',       # Optional: for display in Qt interface
        shortcut='Ctrl+E',      # Optional: keyboard shortcut
        icon='example_icon'     # Optional: icon name in icon directory (without extension); see ./icons/README.md
    )

    # Execute a command
    commands.execute('example.command', arg1, arg2, kwarg1=value1)
"""
import functools
import inspect
import os
import traceback
from typing import Callable

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QWidget

import tilia.errors
from tilia.requests import Post, post


class CommandQAction(QAction):
    """
    Wrapper around QAction adding a `command_name` property.
    The property can be used to retrieve actions from menu by command name,
    which is very useful for testing.
    """

    def __init__(self, command_name: str, parent: QMainWindow | QWidget | None):
        super().__init__(parent)
        self.command_name = command_name


def register(
    name: str,
    callback: Callable,
    text: str = "",
    shortcut: str = "",
    icon: str = "",
    parent: QMainWindow | QWidget | None = None,
):
    """
    Register a command with name to a callback.
    Registered commands can be executed anywhere using commands.execute(name).

    Also creates a QAction with the given text, shortcut and icon.
     The action can be retrieved with commands.get_qaction(name) and used in the Qt interface.
    """
    action = CommandQAction(name, parent)

    action.setText(text)
    action.setToolTip(f"{text} ({shortcut})" if shortcut else text)

    # Re-registration of an existing name is allowed: callbacks and actions
    # are replaced (dict assignment is idempotent), so shortcut tracking
    # must be idempotent too. Otherwise the same command would appear
    # multiple times under its shortcut after a re-register (e.g. the
    # test suite, which rebuilds the QtUI per module in the same process),
    # turning a unique key into a fake collision.
    for cmds_list in _shortcut_to_commands.values():
        if name in cmds_list:
            cmds_list.remove(name)

    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
        _shortcut_to_commands.setdefault(_normalize_shortcut(shortcut), []).append(name)

    if icon:
        if QIcon.hasThemeIcon(icon):
            action.setIcon(QIcon.fromTheme(icon))
        elif icon in QIcon.ThemeIcon._member_names_:
            action.setIcon(QIcon.fromTheme(getattr(QIcon.ThemeIcon, icon)))
    action.setIconVisibleInMenu(False)

    if callback:
        # Qt sometimes activates signals with additional parameters,
        # so we need to make sure that we call the callback without them.
        # This also means that we can't pass arguments to the actions,
        # for that, we should use commands.execute().
        action.triggered.connect(lambda *_: execute(name))

    _name_to_callback[name] = callback
    _name_to_action[name] = action


def get_qaction(name):
    try:
        return _name_to_action[name]
    except KeyError as e:
        raise ValueError(f"Unknown command: {name}") from e


def execute(command_name: str, *args, **kwargs):
    """
    Executes commands previously registered with commands.register(name) by calling the registered callback.
    If in development environment, prints errors to console, else displays them as error message with tilia.errors.
    """
    if os.environ.get("ENVIRONMENT") != "prod":
        return _execute_dev(command_name, *args, **kwargs)
    else:
        return _execute_prod(command_name, *args, **kwargs)


def _execute_dev(command_name: str, *args, **kwargs):
    if command_name not in _name_to_callback:
        raise ValueError(
            f"Unregistered command: {command_name}.\nRegistered commands:\n{list(_name_to_callback.keys())}"
        )

    try:
        return _name_to_callback[command_name](*args, **kwargs)
    except Exception as e:
        callback = _name_to_callback[command_name]
        sig = inspect.signature(callback)
        if isinstance(callback, functools.partial):
            partial_message = (
                "Callback is a partial.\n"
                + f"Partial args: {callback.args}\n"
                + f"Partial kwargs: {callback.keywords}\n"
            )
            callback = callback.func
        else:
            partial_message = ""

        message = f"Error executing command '{command_name}'. \n"
        message += f"Callback: {callback.__module__}.{callback.__name__}{sig}\n"
        message += partial_message
        message += f"Called with args: {args}, kwargs: {kwargs}"
        raise Exception(message) from e


def _execute_prod(command_name: str, *args, **kwargs):
    """Returns False if an error was raised during execution."""
    try:
        return _name_to_callback[command_name](*args, **kwargs)
    except Exception:
        tilia.errors.display(
            tilia.errors.COMMAND_FAILED, command_name, traceback.format_exc()
        )
        return False


def _normalize_shortcut(shortcut: str | QKeySequence | QKeyCombination) -> str:
    """Reduce any shortcut form to the same canonical PortableText string,
    so dict lookups work regardless of how the caller specified the key."""
    if isinstance(shortcut, QKeySequence):
        seq = shortcut
    else:
        seq = QKeySequence(shortcut)
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


def setup_shortcuts(main_window: QMainWindow) -> None:
    """Resolve shared-shortcut conflicts and ensure every command's shortcut
    fires regardless of where the action lives.

    Call once after all commands are registered. Two things happen:
    - Every QAction is parented to `main_window` (via addAction). Qt only
      activates an action's shortcut if some widget containing the action is
      in the active window's hierarchy; without this, actions that only
      appear in a transient context menu (e.g. range move-to-row) would
      have shortcuts that never fire.
    - For shortcuts bound to more than one command (e.g. range and hierarchy
      both map "e" to merge, "s" to split): strip the shortcut from every
      QAction (Qt would emit "Ambiguous shortcut overload" otherwise) and
      install one QShortcut on `main_window` that posts
      Post.SHARED_SHORTCUT_FIRED with the bound names. Some listener (today:
      TimelineUIs) is responsible for picking the winner. QShortcut is used
      in preference to handling the key in `keyPressEvent` because
      QGraphicsView's QAbstractScrollArea base eats some keys before they
      reach the main window.

    Safe to call again with a different `main_window` (the test suite
    rebuilds the main window per test module): old QShortcuts are detached
    and scheduled for deletion so the new main window's shortcuts don't
    fight orphaned ApplicationShortcut bindings still alive on the old
    one.
    """
    # If the previous main window was destroyed, its child QShortcuts
    # have already been deleted on the C++ side; calling methods on them
    # raises RuntimeError. If it's still alive (test fixtures hold an
    # extra reference), explicitly tear the shortcut down so its
    # ApplicationShortcut binding doesn't survive alongside the new
    # main window's binding.
    import shiboken6

    for shortcut in _shared_qshortcuts:
        if shiboken6.isValid(shortcut):
            shortcut.setEnabled(False)
            shortcut.setParent(None)
            shortcut.deleteLater()
    _shared_qshortcuts.clear()

    for action in _name_to_action.values():
        main_window.addAction(action)

    for shortcut_str, names in _shortcut_to_commands.items():
        if len(names) > 1:
            for name in names:
                _name_to_action[name].setShortcut(QKeySequence())
            shortcut = QShortcut(QKeySequence(shortcut_str), main_window)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            # Hand the bound names to whichever listener owns the dispatch
            # decision (today: TimelineUIs picks the most-recently-clicked
            # timeline's command). commands.py stays domain-agnostic.
            shortcut.activated.connect(
                functools.partial(post, Post.SHARED_SHORTCUT_FIRED, tuple(names))
            )
            _shared_qshortcuts.append(shortcut)


_name_to_action = {}
_name_to_callback = {}
_shortcut_to_commands: dict[str, list[str]] = {}
_shared_qshortcuts: list[QShortcut] = []


def reset() -> None:
    _name_to_action.clear()
    _name_to_callback.clear()
    _shortcut_to_commands.clear()
    _shared_qshortcuts.clear()
