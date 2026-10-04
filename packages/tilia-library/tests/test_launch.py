from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library import launch
from tilia_library.api import register_all
from tilia_library.corpora import Corpora
from tilia_library.launch import TiliaNotFound, open_in_tilia
from tilia_library.server import LibraryServer


def entry_points(*names):
    def fake(group=None):
        assert group == "tilia.commands"
        return [SimpleNamespace(name=n) for n in names]

    return fake


class Popen:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, command, **kwargs):
        if self.error:
            raise self.error
        self.calls.append((command, kwargs))


@pytest.fixture
def python(tmp_path):
    """A fake executable with the ``tilia`` script beside it."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").write_bytes(b"")
    (tmp_path / "bin" / "tilia").write_bytes(b"")
    (tmp_path / "bin" / "tilia.exe").write_bytes(b"")
    return tmp_path / "bin" / "python"


FILE = Path("/music/Überleitung.tla")


def test_gui_command_is_started_detached(python):
    popen = Popen()
    how = open_in_tilia(
        FILE,
        entry_points=entry_points("gui", "other"),
        popen=popen,
        platform="linux",
        executable=str(python),
    )
    assert how == "tilia-gui"
    [(command, kwargs)] = popen.calls
    assert command == [str(python.parent / "tilia"), "gui", str(FILE)]
    assert kwargs == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "start_new_session": True,
    }


def test_gui_command_on_windows(python):
    popen = Popen()
    how = open_in_tilia(
        FILE,
        entry_points=entry_points("gui"),
        popen=popen,
        platform="win32",
        executable=str(python),
    )
    assert how == "tilia-gui"
    [(command, kwargs)] = popen.calls
    assert command == [str(python.parent / "tilia.exe"), "gui", str(FILE)]
    expected = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    assert kwargs["creationflags"] == expected
    assert "start_new_session" not in kwargs
    assert kwargs["close_fds"] is True


@pytest.mark.parametrize("platform,opener", [("linux", "xdg-open"), ("darwin", "open")])
def test_system_opener_without_the_gui_command(python, platform, opener):
    popen = Popen()
    how = open_in_tilia(
        FILE,
        entry_points=entry_points("other"),
        popen=popen,
        platform=platform,
        executable=str(python),
    )
    assert how == "system"
    [(command, kwargs)] = popen.calls
    assert command == [opener, str(FILE)]
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["start_new_session"] is True


def test_system_opener_on_windows(python):
    popen = Popen()
    opened = []
    how = open_in_tilia(
        FILE,
        entry_points=entry_points(),
        popen=popen,
        startfile=opened.append,
        platform="win32",
        executable=str(python),
    )
    assert how == "system"
    assert opened == [str(FILE)]
    assert popen.calls == []


def test_system_opener_when_the_script_is_missing(tmp_path):
    popen = Popen()
    how = open_in_tilia(
        FILE,
        entry_points=entry_points("gui"),
        popen=popen,
        platform="linux",
        executable=str(tmp_path / "python"),
    )
    assert how == "system"
    assert popen.calls[0][0][0] == "xdg-open"


def test_failures_become_tilia_not_found(python):
    with pytest.raises(TiliaNotFound):
        open_in_tilia(
            FILE,
            entry_points=entry_points("gui"),
            popen=Popen(OSError("no")),
            platform="linux",
            executable=str(python),
        )
    with pytest.raises(TiliaNotFound):
        open_in_tilia(
            FILE,
            entry_points=entry_points(),
            popen=Popen(FileNotFoundError("xdg-open")),
            platform="darwin",
            executable=str(python),
        )
    with pytest.raises(TiliaNotFound):
        open_in_tilia(
            FILE,
            entry_points=entry_points(),
            startfile=lambda path: (_ for _ in ()).throw(OSError("no")),
            platform="win32",
            executable=str(python),
        )
    with pytest.raises(TiliaNotFound):
        open_in_tilia(
            FILE,
            entry_points=entry_points(),
            startfile=None,
            platform="win32",
            executable=str(python),
        )


def test_launch_does_not_import_the_app():
    source = Path(launch.__file__).read_text(encoding="utf-8")
    assert "import tilia\n" not in source
    assert "from tilia " not in source and "from tilia." not in source


# ---- the route ------------------------------------------------------------ #


class OpenBackend(FixtureBackend):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def files(self, corpus):
        return self.rows


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / "pieces"
    folder.mkdir()
    (folder / "a.tla").write_text("{}")
    elsewhere = tmp_path / "b.tla"
    elsewhere.write_text("{}")
    rows = [
        {"file_id": "rel", "path": "a.tla"},
        {"file_id": "abs", "path": str(elsewhere)},
        {"file_id": "gone", "path": "gone.tla"},
    ]
    corpora = Corpora(tmp_path / "library.toml")
    corpora.add(folder)
    opened = []
    result = {"value": "tilia-gui"}

    def opener(path):
        opened.append(path)
        if isinstance(result["value"], Exception):
            raise result["value"]
        return result["value"]

    server = LibraryServer(OpenBackend(rows))
    register_all(server, corpora, opener=opener)
    server.start()
    yield SimpleNamespace(
        server=server,
        cid=corpora.all()[0].id,
        opened=opened,
        result=result,
        folder=folder,
        elsewhere=elsewhere,
    )
    server.stop()


def post(s, file, cid=None):
    path = f"/api/{cid or s.cid}/files/{file}/open"
    headers = {
        "Authorization": f"Bearer {s.server.token}",
        "Content-Type": "application/json",
        "X-Tilia-Library": "1",
    }
    r = send(s.server, "POST", path, headers, b"{}")
    return r.status, json.loads(r.body)


def test_route_opens_a_relative_and_an_absolute_path(setup):
    assert post(setup, "rel") == (202, {"how": "tilia-gui"})
    assert post(setup, "abs") == (202, {"how": "tilia-gui"})
    resolved = [p.resolve() for p in setup.opened]
    assert resolved == [
        (setup.folder / "a.tla").resolve(),
        setup.elsewhere.resolve(),
    ]


def test_route_says_how(setup):
    setup.result["value"] = "system"
    assert post(setup, "rel") == (202, {"how": "system"})


def test_route_when_tilia_is_not_found(setup):
    setup.result["value"] = TiliaNotFound("no")
    assert post(setup, "rel") == (503, {"error": "TiLiA wasn't found"})


def test_route_404s(setup):
    assert post(setup, "nope") == (404, {"error": "unknown file"})
    assert post(setup, "gone") == (404, {"error": "the file is gone"})
    assert post(setup, "rel", cid="nope")[0] == 404
    assert setup.opened == []
