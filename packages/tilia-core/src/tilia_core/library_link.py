"""How programs find and talk to a running TiLiA Library.

While the library runs it writes a record, ``server.toml``, in the state
folder: its address, a per-run secret token and a random instance id. Other
programs of the same user read it to connect. A record left behind by a crash
is told apart from a live server by asking ``/api/ping`` and comparing the
instance id, never by the record's existence or a process id alone.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomlkit

from tilia_core import state

logger = logging.getLogger(__name__)

PROTOCOL = 1
RECORD_VERSION = 1
RECORD_NAME = "server.toml"

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


@dataclass(frozen=True)
class ServerRecord:
    """What a running library tells other programs about itself."""

    protocol: int
    library_version: str
    instance: str
    pid: int
    address: str
    token: str
    started: datetime
    version: int = RECORD_VERSION

    @classmethod
    def new(cls, address: str, token: str, library_version: str) -> ServerRecord:
        """Make the record for a library starting now, in this process."""
        return cls(
            protocol=PROTOCOL,
            library_version=library_version,
            instance=secrets.token_hex(8),
            pid=os.getpid(),
            address=address,
            token=token,
            started=datetime.now().astimezone().replace(microsecond=0),
        )

    @staticmethod
    def default_path() -> Path:
        """Return where the record lives, inside the state folder."""
        return state.state_dir() / RECORD_NAME

    def write(self, path: Path | None = None) -> None:
        """Write the record atomically, readable by this user only."""
        path = self.default_path() if path is None else Path(path)
        doc = tomlkit.document()
        doc["version"] = self.version
        doc["protocol"] = self.protocol
        doc["library_version"] = self.library_version
        doc["instance"] = self.instance
        doc["pid"] = self.pid
        doc["address"] = self.address
        doc["token"] = self.token
        doc["started"] = self.started
        path.parent.mkdir(parents=True, exist_ok=True)
        state.atomic_write(path, tomlkit.dumps(doc).encode("utf-8"), mode=0o600)

    @classmethod
    def read(cls, path: Path | None = None) -> ServerRecord | None:
        """Return the record on disk, or None if missing or not a valid record."""
        path = cls.default_path() if path is None else Path(path)
        try:
            data = tomlkit.parse(path.read_bytes().decode("utf-8")).unwrap()
        except (OSError, ValueError, tomlkit.exceptions.TOMLKitError):
            return None
        try:
            started = data["started"]
            values = {
                "version": data["version"],
                "protocol": data["protocol"],
                "library_version": data["library_version"],
                "instance": data["instance"],
                "pid": data["pid"],
                "address": data["address"],
                "token": data["token"],
            }
        except KeyError:
            return None
        for key in ("version", "protocol", "pid"):
            if isinstance(values[key], bool) or not isinstance(values[key], int):
                return None
        for key in ("library_version", "instance", "address", "token"):
            if not isinstance(values[key], str):
                return None
        if not isinstance(started, datetime) or started.tzinfo is None:
            return None
        return cls(started=started, **values)

    def remove(self, path: Path | None = None) -> bool:
        """Delete the file if it holds this record's instance; say if it did."""
        path = self.default_path() if path is None else Path(path)
        on_disk = self.read(path)
        if on_disk is None or on_disk.instance != self.instance:
            return False
        try:
            path.unlink()
        except OSError:
            return False
        return True


def _send(
    record: ServerRecord,
    method: str,
    path: str,
    body: object | None,
    timeout: float,
) -> tuple[int, object | None]:
    url = urllib.parse.urljoin(record.address, path.lstrip("/"))
    headers = {"Authorization": f"Bearer {record.token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    # An empty proxy map keeps the token from being sent to a proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        with error:
            status, raw = error.code, error.read()
    except urllib.error.URLError as error:
        raise OSError(str(error.reason)) from error
    except http.client.HTTPException as error:
        raise OSError(f"The server sent a malformed reply: {error!r}") from error
    try:
        return status, json.loads(raw.decode("utf-8")) if raw.strip() else None
    except ValueError:
        return status, None


@dataclass(frozen=True)
class LibraryLink:
    """A live library: its record and what it said when pinged."""

    record: ServerRecord
    protocol: int
    library_version: str

    def request(
        self,
        method: str,
        path: str,
        body: object | None = None,
        *,
        timeout: float = 2.0,
    ) -> tuple[int, object | None]:
        """Send a request to the library; return the status and the JSON body.

        The body is None when the answer is empty or not JSON. An HTTP error
        status is returned, not raised; a connection failure raises OSError.
        """
        return _send(self.record, method, path, body, timeout)


def _is_loopback(address: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(address)
        return (
            parts.scheme == "http"
            and parts.hostname in _LOOPBACK_HOSTS
            and parts.port is not None
        )
    except ValueError:
        return False


def ping(record: ServerRecord, timeout: float = 2.0) -> dict[str, object] | None:
    """Ask the server in the record who it is.

    Return its answer only if it is the record's own instance; None when the
    address isn't local, nothing answers, or the answer is someone else's.
    """
    if not _is_loopback(record.address):
        return None
    try:
        status, answer = _send(record, "GET", "/api/ping", None, timeout)
    except (OSError, http.client.HTTPException):
        return None
    if status != 200 or not isinstance(answer, dict):
        return None
    if answer.get("instance") != record.instance:
        return None
    return answer


def find_library(timeout: float = 2.0) -> LibraryLink | None:
    """Return a link to the running library, or None if there is none."""
    record = ServerRecord.read()
    if record is None:
        return None
    answer = ping(record, timeout)
    if answer is None or answer.get("protocol") != PROTOCOL:
        return None
    library_version = answer.get("library_version")
    if not isinstance(library_version, str):
        return None
    return LibraryLink(record, PROTOCOL, library_version)
