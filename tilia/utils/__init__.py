"""
Aim to get rid of this by refactoring functions and classes into more meaningful modules.
"""

from threading import Thread
from typing import Callable

import tkinter as tk

import logging

logger = logging.getLogger(__name__)

LOGGER = logging.getLogger()

class StateSavable:
    """Objects that can be saved in file."""

    def __init__(self, *args, savable_obj, **kwargs):

        super().__init__(*args, **kwargs)

        self.savable = True  # also enables saving to file
        self.state_savable_obj = savable_obj

    def to_dict(self):
        """Saves savable_obj data to a dict"""
        return self.state_savable_obj.to_dict()

    def from_dict(self, dict):
        """Loads savable_obj data from a dict"""
        self.state_savable_obj.from_dict(dict)

    def clear_state_stack(self):
        "Calls clear() in savable_obj's state_stack"
        self.state_savable_obj.state_stack.clear()


class ObjectRightClickMenu:
    """Mixin for objects that have a right click menu"""

    def __init__(self, *args, menu_class: type = None, **kwargs):

        if not menu_class:
            raise ValueError(
                f"Can't initilized class '{self.__class__}': missing kwarg 'menu_class'"
            )

        super().__init__(*args, **kwargs)

        self.right_click_menu_class = menu_class

    def show_right_click_menu(self, event: tk.Event, *args, **kwargs):
        menu = self.right_click_menu_class(self, *args, **kwargs)
        menu.tk_popup(event.x_root, event.y_root)


def log_object_creation_with_vars(func: Callable, attrs: list[tuple[str, str]]):
    """
    Log object creation when decorating object's __init__ function.
    Logs a "Starting creation..." message before __init__ is called and
    a "Created object" message with given given attributes if
    object is succesfully created.
    Specific decorators should provided attrs to be logged as
    a tuple of the form (displayed name, attribute name).
    """

    def wrapper(self, *args, **kwargs):
        logger.debug(f"Creating {self.__class__.__name__}...")
        result = func(self, *args, **kwargs)
        attrs_text = ""
        for name, attr in attrs:
            attrs_text += f"{name}={getattr(self, attr)}, "
        attrs_text = attrs_text[:-2]
        logger.debug(f"Created {self.__class__.__name__} with {attrs_text}")
        return result

    return wrapper


def log_object_deletion(func: Callable, attrs: list[tuple[str, str]]):
    """
    Function to be called by decorators to log object delete,
    by decorating object's delete function.
    Logs a "Deleting creation..." with given attributes before
     delete is called and a "Deleted succesfylly" message if
    object is sucessfully deleted.
    Specific decorators should provided attrs to be logged as
    a tuple of the form (displayed name, attribute name).
    """

    def wrapper(self, *args, **kwargs):
        attrs_text = ""
        for name, attr in attrs:
            attrs_text += f"{name}={getattr(self, attr)}, "
        attrs_text = attrs_text[:-2]
        logger.debug(f"Deleting {self.__class__.__name__} with {attrs_text}")
        result = func(self, *args, **kwargs)
        logger.debug(f"Deleted {self.__class__.__name__}")
        return result

    return wrapper


# noinspection PyAttributeOutsideInit
# noinspection PyUnresolvedReferences
class PropagatingThread(Thread):
    def run(self):
        self.exc = None
        try:
            self.ret = self._target(*self._args, **self._kwargs)
        except BaseException as e:
            self.exc = e

    def join(self, timeout=None):
        super(PropagatingThread, self).join(timeout)
        if self.exc:
            raise self.exc
        return self.ret
