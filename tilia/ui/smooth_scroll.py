# TODO:
# - use global timer? update all frames at the same time
# - apply smoothing curve to input - currently linear

from typing import Callable, Generic, TypeVar

import shiboken6
from PySide6.QtCore import QObject, QVariantAnimation

from tilia.settings import settings

T = TypeVar("T")


def _float_if_int(value: T) -> T:
    # The animation can't step between an int and a float: it sends None
    # instead. Times and positions are floats, so an int is made one.
    return float(value) if isinstance(value, int) else value


class SmoothSetter(Generic[T]):
    """
    Sets a value in small steps over a short time, so that it moves smoothly,
    or at once when the user prioritises performance.

    Create one per value when its owner is set up, from a getter and a setter
    of that value. Calling it moves the value to the given setpoint. An owner
    that is a QObject passes itself as `parent`, and the movement is deleted
    with it; any other owner deletes it with the objects the setter changes.
    """

    DURATION = 125

    def __init__(
        self,
        getter: Callable[[], T],
        setter: Callable[[T], None],
        parent: QObject | None = None,
    ) -> None:
        self._getter = getter
        self._setter = setter
        self._is_deleted = False
        self.animation = QVariantAnimation(parent)
        self.animation.setDuration(self.DURATION)
        self.animation.valueChanged.connect(self._setter)

    @property
    def _is_gone(self) -> bool:
        # Deleted, or its animation deleted with its Qt parent.
        return self._is_deleted or not shiboken6.isValid(self.animation)

    def __call__(self, setpoint: T) -> None:
        if self._is_gone:
            return

        setpoint = _float_if_int(setpoint)

        if settings.get("general", "prioritise_performance") is True:
            self.set_now(setpoint)
            return

        # A whole movement from where the value is now. Resumed, a movement
        # retargeted partway would leap ahead by the share of it that had
        # passed. Changing the values of a stopped animation still sends values
        # for the time it stopped at, so they are set with signals blocked.
        self.animation.stop()
        self.animation.blockSignals(True)
        self.animation.setStartValue(_float_if_int(self._getter()))
        self.animation.setEndValue(setpoint)
        self.animation.blockSignals(False)
        self.animation.start()

    def set_now(self, value: T) -> None:
        """
        Sets the value at once. Set it through here, not with the setter: a
        movement still running would overwrite it.
        """
        if self._is_gone:
            return
        self.animation.stop()
        self._setter(_float_if_int(value))

    def stop(self) -> None:
        """Stops the movement where it is."""
        if not self._is_gone:
            self.animation.stop()

    def delete(self) -> None:
        """
        Stops the movement and ignores calls from now on. A movement, or a call
        that comes late, would otherwise set the value on deleted objects. A
        movement deleted with its Qt parent ignores calls too.
        """
        self.stop()
        self._is_deleted = True
