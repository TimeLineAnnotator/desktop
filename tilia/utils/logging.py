from typing import Callable
import logging

logger = logging.getLogger(__name__)


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
