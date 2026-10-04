"""The ``tilia library`` command."""

from __future__ import annotations

import argparse
import html
import logging
import os
import signal
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from tilia_core import state
from tilia_core.library_link import PROTOCOL, LibraryLink, ServerRecord, ping
from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.server import LibraryServer

DEFAULT_PORT = 8765
PORT_TRIES = 50
OPEN_NAME = "open.html"
LOCK_NAME = "start.lock"
LOCK_STALE_S = 30.0
PING_TIMEOUT_S = 2.0

_MAX_PORT = 65535
_LOCK_POLL_S = 0.1
_CLEANUP_WAIT_S = 4.0
# Windows console control events: close, logoff and shutdown.
_CONSOLE_EVENTS = (2, 5, 6)


class NoFreePort(Exception):
    """Raised when none of the ports tried could be used."""

    def __init__(self, first: int, last: int) -> None:
        super().__init__(f"no free port from {first} to {last}")
        self.first = first
        self.last = last


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command's arguments; a bad argument exits with status 2."""
    parser = argparse.ArgumentParser(
        prog="tilia library",
        description=(
            "Open folders of TiLiA files in your browser: query them, edit them "
            "in bulk and see their statistics."
        ),
    )
    parser.add_argument(
        "folder",
        metavar="FOLDER",
        nargs="?",
        help="a folder of TiLiA files to open; it is added to the library if it is new",
    )
    parser.add_argument(
        "--port",
        metavar="N",
        type=int,
        default=DEFAULT_PORT,
        help=f"the first port to try (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print the address instead of opening a browser",
    )
    return parser.parse_args(argv)


def bind_server(
    make: Callable[[int], LibraryServer], first: int, tries: int = PORT_TRIES
) -> LibraryServer:
    """Make a server on the first free port from ``first``, trying ``tries`` ports."""
    last = min(first + tries - 1, _MAX_PORT)
    for port in range(first, last + 1):
        try:
            return make(port)
        except OSError:
            continue
    raise NoFreePort(first, last)


def write_open_page(path: Path, entry_url: str) -> None:
    """Write a page that sends the browser on to ``entry_url``.

    The browser is given this file's address instead of the entry URL, because a
    URL passed to a browser ends up in its command line, which other users of the
    computer can read; the token must never be there. The page is readable by
    this user only.
    """
    entry = html.escape(entry_url)
    page = (
        "<!doctype html>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0;url={entry}">\n'
        "<title>TiLiA Library</title>\n"
        f'<a href="{entry}">Open TiLiA Library</a>\n'
    )
    state.atomic_write(path, page.encode("utf-8"), mode=0o600)


def _error(message: str) -> None:
    print(message, file=sys.stderr)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def _now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _open_browser(page: Path) -> None:
    """Open the page in the browser, saying so if that doesn't work."""
    try:
        opened = webbrowser.open(page.absolute().as_uri())
    except Exception:  # noqa: BLE001 - any browser failure is only a message
        opened = False
    if not opened:
        _error("tilia library: couldn't open a browser; open the address above")


def _running() -> tuple[ServerRecord, dict[str, object]] | None:
    """Return the record and ping answer of a running library, if there is one."""
    record = ServerRecord.read()
    if record is None:
        return None
    answer = ping(record, PING_TIMEOUT_S)
    return None if answer is None else (record, answer)


def _hand_over(
    record: ServerRecord,
    answer: dict[str, object],
    folder: Path | None,
    typed: str | None,
    no_browser: bool,
) -> int:
    """Use the library that is already running instead of starting another."""
    protocol = answer.get("protocol")
    if protocol != PROTOCOL:
        _error(
            f"Another version of TiLiA Library is running ({record.address}). "
            "Stop it with Ctrl+C in its terminal, then try again."
        )
        return 1
    version = answer.get("library_version")
    link = LibraryLink(record, PROTOCOL, version if isinstance(version, str) else "")
    if folder is not None:
        try:
            status, body = link.request(
                "POST", "/api/corpora", {"path": str(folder)}, timeout=5.0
            )
        except OSError:
            _error(
                f"tilia library: the running library at {record.address} "
                "stopped answering"
            )
            return 1
        if status != 200:
            message = body.get("error") if isinstance(body, dict) else None
            _error(
                "tilia library: the running library couldn't add "
                f"{typed}: {message or f'status {status}'}"
            )
            return 1
    entry_url = f"{record.address}?token={record.token}"
    if not no_browser:
        page = state.state_dir() / OPEN_NAME
        if record.token not in _read_text(page):
            write_open_page(page, entry_url)
        _open_browser(page)
    print(f"TiLiA Library is already running at {entry_url}", flush=True)
    return 0


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _take_lock(
    path: Path,
) -> tuple[bool, tuple[ServerRecord, dict[str, object]] | None]:
    """Take the start lock, or find that a library has started meanwhile.

    Return ``(True, None)`` once the lock is ours, ``(False, running)`` when a
    running library answered instead.
    """
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        except PermissionError:
            # Windows: the other command is deleting its lock right now.
            if sys.platform != "win32":
                raise
        else:
            with os.fdopen(fd, "w") as lock:
                lock.write(str(os.getpid()))
            return True, None
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            continue
        if age > LOCK_STALE_S:
            _remove(path)
            continue
        running = _running()
        if running is not None:
            return False, running
        time.sleep(_LOCK_POLL_S)


def _install_console_handler(stop: threading.Event, done: threading.Event) -> object:
    """On Windows, let the closing console wait for the cleanup to finish."""
    import ctypes
    from ctypes import wintypes

    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def handle(event: int) -> bool:
        if event not in _CONSOLE_EVENTS:
            return False  # let Ctrl+C reach Python's own handler
        stop.set()
        done.wait(_CLEANUP_WAIT_S)
        return True  # Windows ends the process after this returns

    callback = handler_type(handle)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(callback, True)
    return callback


def _ask_to_stop_on_signals(stop: threading.Event) -> None:
    """Make the stop signals set ``stop``; the cleanup runs in the main thread."""

    def ask_to_stop(signum: int, frame: object) -> None:
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, ask_to_stop)


def _wait_for_stop(stop: threading.Event) -> None:
    # A plain wait() can't be interrupted on Windows.
    while not stop.wait(0.5):
        pass


def _start(args: argparse.Namespace, folder: Path | None) -> int:
    """Start a library; the caller holds the start lock until this returns."""
    lock = state.state_dir() / LOCK_NAME
    taken, running = _take_lock(lock)
    if not taken:
        assert running is not None
        return _hand_over(*running, folder, args.folder, args.no_browser)
    released = False

    def release() -> None:
        # Once released, the lock may be another command's: never delete it twice.
        nonlocal released
        if not released:
            released = True
            _remove(lock)

    try:
        running = _running()
        if running is not None:
            return _hand_over(*running, folder, args.folder, args.no_browser)
        return _serve(args, folder, release)
    finally:
        release()


def _serve(
    args: argparse.Namespace, folder: Path | None, release_lock: Callable[[], None]
) -> int:
    corpora = Corpora()
    corpora.all()
    if corpora.set_aside_to is not None:
        _error(
            "library.toml couldn't be read; kept as "
            f"{corpora.set_aside_to.name}, starting with no corpora"
        )
    if folder is not None:
        corpora.add(folder)
    else:
        last = corpora.last()
        if last is not None and not last.available:
            _error(
                f"tilia library: {last.path} is missing; it is listed as unavailable"
            )

    try:
        server = bind_server(
            lambda port: LibraryServer(CoreBackend(), port=port), args.port
        )
    except NoFreePort as error:
        _error(f"tilia library: no free port from {error.first} to {error.last}")
        return 1
    started = False
    try:
        register_all(server, corpora)
        record = ServerRecord(
            protocol=PROTOCOL,
            library_version=server.library_version,
            instance=server.instance,
            pid=os.getpid(),
            address=server.address,
            token=server.token,
            started=_now(),
        )
        record.write()
        started = True
    finally:
        if not started:
            server.stop()

    page = state.state_dir() / OPEN_NAME
    stop = threading.Event()
    done = threading.Event()
    callback = None
    # Handlers first: a stop signal sent as soon as the address is printed must
    # not find Python's default handler.
    _ask_to_stop_on_signals(stop)
    try:
        if sys.platform == "win32":
            callback = _install_console_handler(stop, done)
        write_open_page(page, server.entry_url)
        release_lock()
        server.start()
        print(f"TiLiA Library is running at {server.entry_url}", flush=True)
        print("Press Ctrl+C to stop it.", flush=True)
        if not args.no_browser:
            _open_browser(page)
        _wait_for_stop(stop)
    finally:
        server.stop()
        record.remove()
        if server.token in _read_text(page):
            _remove(page)
        done.set()
    del callback  # held until here so that Windows can call it
    return 0


def main() -> int:
    """Run ``tilia library``."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = parse_args(sys.argv[1:])

    folder: Path | None = None
    if args.folder is not None:
        folder = Path(args.folder).expanduser()
        if not folder.is_dir():
            _error(f"tilia library: {args.folder} is not a folder")
            return 1
        folder = folder.resolve()

    try:
        state.state_dir().mkdir(parents=True, exist_ok=True)
    except OSError as error:
        _error(
            f"tilia library: can't write to {state.state_dir()}: "
            f"{error.strerror or error}"
        )
        return 1

    running = _running()
    if running is not None:
        return _hand_over(*running, folder, args.folder, args.no_browser)
    return _start(args, folder)
