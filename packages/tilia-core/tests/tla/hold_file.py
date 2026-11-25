"""Another program that has a file open, for the tests of a file in use (Windows).

A test starts it as another program with `Held`, and it runs as:

    hold_file.py PATH SHARE [--lock-from OFFSET] [--may-delete] [--then-write SOURCE]

It opens PATH for reading and writing, and lets other programs do with it meanwhile
what SHARE says: "none", or any of "read", "write" and "delete" joined by "+".
`--lock-from` locks its bytes from OFFSET on as well, as a program does that shares the
file but not its content; `--may-delete` opens it with the right to delete it, as a
program does that deletes it when it ends. It prints "held", and keeps the file until
its standard input ends; with `--then-write`, it first writes SOURCE's bytes in the
file, as a program that changes it and lets it go. It ends by itself after a minute,
whatever becomes of the test.

It opens the file through Windows, not through Python, whose `open` always lets the
others read and write.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# What another program opens the file with, by the name a test gives it: Windows'
# sharing modes, a file whose bytes are locked, and one it may delete. Python's `open`
# can't read it in the first five: the program lets others do nothing with it that
# reading needs, or locks what it reads, or has a right that `open` doesn't share. (A
# file the person may not read is told apart in `no_permission_to_read`.)
MODES = {
    "none": ["none"],
    "write": ["write"],
    "delete": ["delete"],
    "lock": ["read+write+delete", "--lock-from", "0"],
    "may delete": ["read+write", "--may-delete"],
    "read": ["read"],
    "read+write": ["read+write"],
    "read+write+delete": ["read+write+delete"],
}
UNREADABLE = ["none", "write", "delete", "lock", "may delete"]
READABLE = ["read", "read+write", "read+write+delete"]

# A virtual environment's python.exe can be a launcher that starts the interpreter as a
# child, which would go on holding the file when the launcher is ended.
PYTHON = getattr(sys, "_base_executable", None) or sys.executable

SHARES = {"read": 1, "write": 2, "delete": 4}


class Held:
    """Another program with the file open, in one of `UNREADABLE` or `READABLE`, until
    `release`. With `then_write`, it leaves that file's bytes in it as it lets it go."""

    def __init__(
        self,
        path: object,
        mode: str,
        then_write: object = None,
        lock_from: int | None = None,
    ) -> None:
        command = [PYTHON, str(Path(__file__)), str(path), *MODES[mode]]
        if lock_from is not None:
            command += ["--lock-from", str(lock_from)]
        if then_write is not None:
            command += ["--then-write", str(then_write)]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = self.process.stdout.readline()
        assert line == "held\n", self.process.communicate()[1]

    def release(self) -> None:
        self.process.stdin.close()
        self.process.wait(timeout=60)

    def __enter__(self) -> Held:
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self.process.poll() is None:
            self.release()


@contextmanager
def no_permission_to_read(path: object) -> Iterator[None]:
    """Windows' way to say that nobody may read a file's data, while its owner still
    reads, and so can give back, its permissions."""
    everyone = "*S-1-1-0"
    subprocess.run(
        ["icacls", str(path), "/deny", f"{everyone}:(RD)"],
        check=True,
        capture_output=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            ["icacls", str(path), "/remove:d", everyone],
            check=True,
            capture_output=True,
        )


def main() -> None:
    import ctypes
    from ctypes import wintypes

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("share")
    parser.add_argument("--lock-from", type=int)
    parser.add_argument("--may-delete", action="store_true")
    parser.add_argument("--then-write", type=Path)
    arguments = parser.parse_args()
    threading.Timer(60, os._exit, [3]).start()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    def check(result: object) -> None:
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    generic_read, generic_write, open_existing = 0x80000000, 0x40000000, 3
    delete = 0x00010000
    share = 0
    if arguments.share != "none":
        for name in arguments.share.split("+"):
            share |= SHARES[name]
    handle = kernel32.CreateFileW(
        arguments.path,
        generic_read | generic_write | (delete if arguments.may_delete else 0),
        share,
        None,
        open_existing,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = wintypes.HANDLE(handle)
    if arguments.lock_from is not None:
        # Every byte from there to the end of any file.
        overlapped = Overlapped()
        overlapped.Offset = arguments.lock_from
        check(
            kernel32.LockFileEx(
                handle,
                3,  # exclusively, and at once
                0,
                0xFFFFFFFF,
                0x7FFFFFFF,
                ctypes.byref(overlapped),
            )
        )
    print("held", flush=True)
    sys.stdin.read()

    if arguments.then_write is not None:
        # A program may write what it has locked. Written before it is cut to length,
        # so that nobody ever sees it empty.
        data = arguments.then_write.read_bytes()
        check(kernel32.SetFilePointer(handle, 0, None, 0) != 0xFFFFFFFF)
        written = wintypes.DWORD()
        check(kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None))
        check(written.value == len(data))
        check(kernel32.SetEndOfFile(handle))
    kernel32.CloseHandle(handle)
    os._exit(0)


if __name__ == "__main__":
    main()
