"""Helpers to run ``tilia library`` in a subprocess, through the wrapper."""

from __future__ import annotations

import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

WRAPPER = Path(__file__).with_name("library_wrapper.py")
IS_WINDOWS = sys.platform == "win32"


class Running:
    """A started command, with its stdout read by a background thread."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: list[str] = []
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._queue.put(line.rstrip("\r\n"))
        self._queue.put(None)

    def read_until(self, prefix: str, timeout: float = 10.0) -> str:
        """Return the first stdout line starting with ``prefix``."""
        for line in self.lines:
            if line.startswith(prefix):
                return line
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no stdout line starting with {prefix!r}") from None
            try:
                line = self._queue.get(timeout=left)
            except queue.Empty:
                raise TimeoutError(f"no stdout line starting with {prefix!r}") from None
            if line is None:
                raise EOFError(f"output ended without {prefix!r}: {self.lines}")
            self.lines.append(line)
            if line.startswith(prefix):
                return line

    def stop(self, timeout: float = 10.0) -> int:
        """Ask the command to stop, wait for it, and return its exit code."""
        if self.process.poll() is None:
            if IS_WINDOWS:
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.process.send_signal(signal.SIGINT)
        return self.wait(timeout)

    def wait(self, timeout: float = 10.0) -> int:
        try:
            return self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            raise

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()

    def stderr_text(self) -> str:
        """Everything on stderr; call after the command has exited."""
        assert self.process.stderr is not None
        return self.process.stderr.read()


def start(state_dir: Path, browser_log: Path, *arguments: str) -> Running:
    """Start the command and return at once."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    process = subprocess.Popen(
        [sys.executable, str(WRAPPER), str(state_dir), str(browser_log), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        creationflags=flags,
    )
    return Running(process)


def run(
    state_dir: Path, browser_log: Path, *arguments: str, timeout: float = 10.0
) -> tuple[int, str, str]:
    """Run a command that ends by itself; return its exit code, stdout, stderr."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    result = subprocess.run(
        [sys.executable, str(WRAPPER), str(state_dir), str(browser_log), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=flags,
    )
    return result.returncode, result.stdout, result.stderr
