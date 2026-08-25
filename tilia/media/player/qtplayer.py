from __future__ import annotations

from PySide6.QtCore import QEventLoop, QObject, QTimer, SignalInstance, Slot


class PositionRelay(QObject):
    """Lives on the GUI thread. AudioEngineWorker/VideoEngineWorker push
    position here via a queued connection (same pattern as FrameRelay), so
    _engine_get_current_time can read a plain attribute instead of blocking
    on a round-trip to the worker thread every UPDATE_INTERVAL tick -- which
    used to cause real, sustained lag under CPU contention, since a blocked
    GUI thread pumps no messages at all."""

    def __init__(self) -> None:
        super().__init__()
        self.position = 0.0

    @Slot(float)
    def on_position_changed(self, position: float) -> None:
        self.position = position


def wait_for_signal(signal: SignalInstance, value):
    """
    Many Qt functions run on threads, and this wrapper makes sure that after starting a process, the right signal is emitted before continuing the TiLiA process.
    See _do_stop in audio_worker.py/video_worker.py for an example implementation.

    :param signal: The signal to watch.
    :type signal: SignalInstance
    :param value: The "right" output value that signal should emit before continuing. (eg. on stopping player, playbackStateChanged emits StoppedState when player has been successfully stopped. Only then can we continue the rest of the update process.)
    """

    def signal_wrapper(func):
        timer = QTimer(singleShot=True, interval=200)
        loop = QEventLoop()
        success = False

        def value_checker(signal_value):
            if signal_value == value:
                nonlocal success
                success = True
                loop.quit()

        def check_signal(*args, **kwargs):
            nonlocal success
            if not func(*args, **kwargs):
                return False
            signal.connect(value_checker)
            timer.timeout.connect(loop.quit)
            timer.start()
            loop.exec()
            return timer.isActive() and success

        return check_signal

    return signal_wrapper
