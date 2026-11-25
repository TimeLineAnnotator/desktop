"""Reading a file that another program may have locked (Windows; FR-042).

A program that opens a file on Windows chooses what others may do with it meanwhile.
One that lets nobody read it, or that locks its bytes, makes `open` or `read` fail as
a file one may not read does. Python gives errno 13 for both, without Windows' own
number, so this asks Windows itself which of the two it was
(TimeLineAnnotator/project-management#683, b).
"""

from __future__ import annotations

import os
import sys
import time

from tilia_core import state
from tilia_core.tla.errors import FileInUse

_GENERIC_READ = 0x80000000
# What Python's `open` lets others do with the file, so that this is refused where
# `open` is.
_SHARE_READ_AND_WRITE = 0x1 | 0x2
_OPEN_EXISTING = 3
_READ_AT_A_TIME = 1 << 16

# Windows' errors for a file another program has open without sharing it, and for
# bytes another program has locked. No permission is another: access denied (5).
_SHARING_VIOLATION, _LOCK_VIOLATION = 32, 33


def held_by_another(path: str | os.PathLike[str]) -> bool:
    """Whether Windows won't let this program read the file at `path` because another
    program has it open without sharing it, or has locked bytes of it. False when it
    can be read, or can't be for another reason, such as permissions or that it isn't
    there. Only Windows locks files so: always False on other systems."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    read_file = kernel32.ReadFile
    read_file.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
        wintypes.LPVOID,
    ]
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]

    handle = create_file(
        os.fsdecode(path),
        _GENERIC_READ,
        _SHARE_READ_AND_WRITE,
        None,
        _OPEN_EXISTING,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        return ctypes.get_last_error() in (_SHARING_VIOLATION, _LOCK_VIOLATION)
    try:
        buffer = ctypes.create_string_buffer(_READ_AT_A_TIME)
        count = wintypes.DWORD()
        while True:
            if not read_file(
                handle, buffer, _READ_AT_A_TIME, ctypes.byref(count), None
            ):
                return ctypes.get_last_error() in (_SHARING_VIOLATION, _LOCK_VIOLATION)
            if count.value == 0:
                return False
    finally:
        close_handle(handle)


def read_bytes(path: str | os.PathLike[str]) -> bytes:
    """The bytes of the file at `path`, as `open` and `read` give them. On Windows,
    one another program has locked is tried again for as long as `atomic_write` tries
    its rename, and then raises `FileInUse`. Anything else raises what they raise."""
    deadline: float | None = None
    looked_again = False
    while True:
        try:
            with open(path, "rb") as file:
                return file.read()
        except PermissionError as error:
            if not state._IS_WINDOWS:
                raise
            if held_by_another(path):
                looked_again = False
                now = time.monotonic()
                if deadline is None:
                    deadline = now + state._REPLACE_RETRY_TIMEOUT
                if now >= deadline:
                    raise FileInUse(path) from error
                time.sleep(state._REPLACE_RETRY_INTERVAL)
            elif looked_again:
                raise
            else:
                # It may have been let go between the two looks: read it again.
                looked_again = True
