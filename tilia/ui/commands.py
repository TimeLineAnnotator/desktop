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
        text='Menu Text',  # Optional: for display in Qt interface
        shortcut='Ctrl+E',  # Optional: keyboard shortcut
        icon='example_icon'   # Optional: icon name in IMG_DIR (without extension)
    )

    # Execute a command
    commands.execute('example.command', arg1, arg2, kwarg1=value1)
"""
import functools
import inspect
import os
import traceback
from typing import Callable

import tilia.errors
from tilia.dirs import IMG_DIR

from PySide6.QtWidgets import QMainWindow, QWidget
from PySide6.QtGui import QAction, QKeySequence, QIcon


class CommandQAction(QAction):
    """
    Wrapper around QAction adding a `command_name` property.
    The property can be used to retrieve actions from menu by command name,
    which is very useful for testing.
    """

    def __init__(self, command_name: str, parent: QMainWindow | QWidget | None):
        super().__init__(parent)
        self.command_name = command_name


def get_img_path(basename: str):
    return IMG_DIR / f"{basename}.png"


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

    if shortcut:
        action.setShortcut(QKeySequence(shortcut))

    if icon:
        action.setIcon(QIcon(str(get_img_path(icon))))
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
    except KeyError:
        raise ValueError(f"Unknown command: {name}")


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


_name_to_action = {}
_name_to_callback = {}
