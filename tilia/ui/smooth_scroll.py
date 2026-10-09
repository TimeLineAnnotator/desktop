# TODO:
# - use global timer? update all frames at the same time
# - apply smoothing curve to input - currently linear

from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QVariantAnimation

from tilia.settings import settings

T = TypeVar("T")


class SmoothSetter(Generic[T]):
    """
    Sets a value in small steps over a short time, so that it moves smoothly,
    or at once when the user prioritises performance.

    Create one per value when its owner is set up, from a getter and a setter
    of that value. Calling it moves the value to the given setpoint.
    """

    DURATION = 125

    def __init__(self, getter: Callable[[], T], setter: Callable[[T], None]) -> None:
        self._getter = getter
        self._setter = setter
        self.animation = QVariantAnimation()
        self.animation.setDuration(self.DURATION)
        self.animation.valueChanged.connect(self._setter)

    def __call__(self, setpoint: T) -> None:
        if isinstance(setpoint, int):
            # The animation can't step between an int and a float: it sends
            # None instead. Times and positions are floats.
            setpoint = float(setpoint)

        if settings.get("general", "prioritise_performance") is True:
            self.set_now(setpoint)
            return

        if self.animation.state() is QVariantAnimation.State.Running:
            self.animation.pause()
        self.animation.setStartValue(self._getter())
        self.animation.setEndValue(setpoint)
        self.animation.start()

    def set_now(self, value: T) -> None:
        """
        Sets the value at once. Set it through here, not with the setter: a
        movement still running would overwrite it.
        """
        self.animation.stop()
        self._setter(value)
