# TODO:
# - use global timer? update all frames at the same time
# - apply smoothing curve to input - currently linear

from typing import Any, Callable
from PyQt6.QtCore import QTimer


def setup_smooth(self):
    self.smoothing_timer = QTimer()
    self.step_queue = []


def smooth(self: Any, args_getter: Callable[[], tuple[Any]]):
    """
    Function Wrapper
    Smooths changes made by `args_setter` by inputting smaller changes over time.
    Run `setup_smooth` in object init.

    - `args_getter` retrieves current values
    - `args_setter` sets values
    - `args_setpoint` is the final value of the variables to be set

    `args_getter` and `args_setter` must refer to the same variables in `args_setpoint` in the same order.
    """
    fps = 500
    smoothing_duration = 150
    steps_total = fps * smoothing_duration / 1000
    is_ints = [isinstance(o, int) for o in args_getter()]

    def wrapper(args_setter: Callable[[tuple[Any]], None]) -> None:
        def wrapped_setter(*args_setpoint: tuple[Any]) -> None:
            if list(args_setpoint) == list(args_getter()):
                return

            current_values = args_getter()
            new_queue = []
            to_activate = False
            for v, c in zip(args_setpoint, current_values):
                if v == c:
                    new_queue.append({"target": c, "remaining_steps": 0})
                else:
                    new_queue.append({"target": v, "remaining_steps": steps_total})
                    to_activate = True

            self.step_queue = new_queue
            if not to_activate and self.smoothing_timer.isActive():
                self.smoothing_timer.stop()
            elif to_activate and not self.smoothing_timer.isActive():
                self.smoothing_timer.start(1000 // fps)

        def timeout() -> None:
            new_values, to_stop = get_new_values()
            args_setter(*new_values)
            if to_stop:
                self.smoothing_timer.stop()

        def get_new_values() -> tuple[list[Any], bool]:
            new_values = []
            current_values = args_getter()
            empty_count = 0

            for step, current, is_int in zip(self.step_queue, current_values, is_ints):
                if current == step["target"] or step["remaining_steps"] <= 0:
                    new_values.append(step["target"])
                    step["remaining_steps"] = 0
                    empty_count += 1
                else:
                    new_value = (step["target"] - current) / step["remaining_steps"]
                    new_values.append(
                        (round(new_value) if is_int else new_value) + current
                    )
                    step["remaining_steps"] -= 1

            return new_values, empty_count == len(self.step_queue)

        self.smoothing_timer.timeout.connect(timeout)
        return wrapped_setter

    return wrapper
