# TODO:
# - use global timer? update all frames at the same time
# - apply smoothing curve to input - currently linear

from typing import Any, Callable
from PySide6.QtCore import QVariantAnimation

from tilia.settings import settings


def setup_smooth(self):
    self.animation = QVariantAnimation()
    self.animation.setDuration(125)


def smooth(self: Any, args_getter: Callable[[], object]):
    """
    Function Wrapper
    Smooths changes made by `args_setter` by inputting smaller changes over time.
    Run `setup_smooth` in object init.

    - `args_getter` retrieves current values
    - `args_setter` sets values
    - `args_setpoint` is the final value of the variables to be set

    `args_getter` and `args_setter` must refer to the same variables in `args_setpoint` in the same order.
    """

    def wrapper(args_setter: Callable[[object], None]) -> Callable:
        def wrapped_setter(args_setpoint: object) -> None:
            if self.animation.state() is QVariantAnimation.State.Running:
                self.animation.pause()
            self.animation.setStartValue(args_getter())
            self.animation.setEndValue(args_setpoint)
            self.animation.start()

        def timeout(value: object) -> None:
            args_setter(value)

        if settings.get("general", "prioritise_performance") is True:
            return args_setter

        self.animation.valueChanged.connect(timeout)
        return wrapped_setter

    return wrapper
