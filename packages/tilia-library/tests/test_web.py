from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

import tilia_library
from tilia_library.server import LibraryServer

WEB = Path(tilia_library.__file__).resolve().parent / "web"
VENDOR = WEB / "vendor"
PANELS = ["files", "query", "categories", "statistics", "edit-log"]
IMPORT = re.compile(r"""^\s*import\s+(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]""", re.M)


def _web_files():
    return sorted(p for p in WEB.rglob("*") if p.is_file())


def test_index_links_existing_assets_and_has_tabs():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    links = re.findall(r"""(?:href|src)="(/web/[^"]+)\"""", page)
    assert "/web/css/library.css" in links
    assert "/web/js/main.js" in links
    assert "/web/js/lib/boot-guard.js" in links
    for link in links:
        assert (WEB / link.removeprefix("/web/")).is_file(), link
    nav = re.search(r'<nav id="tabs">(.*?)</nav>', page, re.S).group(1)
    assert re.findall(r'data-panel="([^"]+)"', nav) == PANELS


def test_imports_exist():
    scripts = list(WEB.glob("js/**/*.js"))
    assert scripts
    for script in scripts:
        for name in IMPORT.findall(script.read_text(encoding="utf-8")):
            assert name.startswith("."), (script, name)
            assert (script.parent / name).resolve().is_file(), (script, name)


def test_nothing_loads_from_the_internet():
    for path in _web_files():
        if VENDOR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text, path


def test_main_ends_with_boot_flag():
    text = (WEB / "js" / "main.js").read_text(encoding="utf-8").rstrip()
    assert text.splitlines()[-1] == "window.__bootOk = true;"


@pytest.fixture
def running():
    server = LibraryServer(FixtureBackend())
    server.start()
    yield server
    server.stop()


def test_every_web_file_is_served_with_its_type(running):
    types = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}
    headers = {"Authorization": f"Bearer {running.token}"}
    for path in _web_files():
        if path.suffix not in types:
            continue
        url = "/web/" + path.relative_to(WEB).as_posix()
        reply = send(running, "GET", url, headers)
        assert reply.status == 200, url
        assert reply.headers["content-type"].startswith(types[path.suffix]), url
        assert reply.body == path.read_bytes()
