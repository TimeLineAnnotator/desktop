"""The library's list of corpora, and the routes that show and change it."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
import tomlkit
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import library as library_api
from tilia_library.corpora import Corpora, corpus_id, same_path
from tilia_library.server import LibraryServer


@pytest.fixture
def corpora(tmp_path):
    return Corpora(tmp_path / "state" / "library.toml")


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "Mozart"
    path.mkdir()
    (path / "a.tla").write_bytes(b"{}")
    return path


def read(corpora):
    return tomlkit.parse(corpora.path.read_text(encoding="utf-8"))


class TestIds:
    def test_slugs(self):
        assert re.fullmatch(
            r"mozart-sonatas-[0-9a-f]{4}", corpus_id(Path("/x/Mozart Sonatas"))
        )
        assert corpus_id(Path("/x/Überleitung")).startswith("uberleitung-")
        assert corpus_id(Path("/x/过渡")).startswith("corpus-")

    def test_long_names_are_cut(self):
        cid = corpus_id(Path("/x/" + "ab " * 40))
        slug = cid.rsplit("-", 1)[0]
        assert slug.startswith("ab-ab-") and len(slug) <= 40
        assert not slug.endswith("-")

    def test_taken_ids_get_more_digits(self):
        first = corpus_id(Path("/x/Mozart"))
        second = corpus_id(Path("/x/Mozart"), {first})
        assert len(second) == len(first) + 1
        assert second.startswith(first)

    def test_same_path_same_id(self):
        assert corpus_id(Path("/x/Mozart")) == corpus_id(Path("/x/Mozart"))


class TestSamePath:
    def test_one_folder_under_several_spellings(self, corpora, folder, monkeypatch):
        first = corpora.add(folder)
        monkeypatch.chdir(folder.parent)
        assert corpora.add(Path(folder.name)).id == first.id
        assert corpora.add(folder / ".." / folder.name).id == first.id
        if sys.platform != "win32":
            link = folder.parent / "link"
            link.symlink_to(folder, target_is_directory=True)
            assert corpora.add(link).id == first.id
        else:
            assert corpora.add(Path(str(folder).swapcase())).id == first.id
        assert len(corpora.all()) == 1

    def test_same_path_compares_case_on_windows_only(self):
        expected = sys.platform == "win32"
        assert same_path(Path("/A/b"), Path("/a/B")) is expected


class TestFile:
    def test_add_writes_version_1(self, corpora, folder):
        corpus = corpora.add(folder)
        doc = read(corpora)
        assert doc["version"] == 1
        assert doc["last_corpus"] == corpus.id
        [entry] = doc["corpora"]
        assert entry["id"] == corpus.id
        assert entry["path"] == str(folder.resolve())
        for key in ("added", "last_opened"):
            assert isinstance(entry[key], datetime)
            assert entry[key].tzinfo is not None
        assert corpus.name == "Mozart"
        assert corpus.available

    def test_adding_again_keeps_one_entry(self, corpora, folder):
        first = corpora.add(folder)
        again = corpora.add(folder)
        assert again.id == first.id
        assert again.added == first.added
        assert again.last_opened >= first.last_opened
        assert len(read(corpora)["corpora"]) == 1

    def test_add_a_file_raises(self, corpora, folder):
        with pytest.raises(NotADirectoryError):
            corpora.add(folder / "a.tla")

    def test_remove_leaves_the_folder_alone(self, corpora, folder):
        corpus = corpora.add(folder)
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()
        }
        assert corpora.remove(corpus.id) is True
        assert corpora.remove(corpus.id) is False
        assert corpora.all() == []
        assert "last_corpus" not in read(corpora)
        assert corpora.last() is None
        after = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()
        }
        assert after == before

    def test_remove_keeps_last_corpus_when_it_names_another(self, corpora, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()
        first = corpora.add(a)
        second = corpora.add(b)
        corpora.remove(first.id)
        assert corpora.last().id == second.id

    def test_opened(self, corpora, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()
        first = corpora.add(a)
        corpora.add(b)
        corpora.opened(first.id)
        assert corpora.last().id == first.id
        corpora.opened("unknown")
        assert corpora.last().id == first.id

    def test_hand_edits_survive(self, corpora, folder, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        corpus = corpora.add(folder)
        text = corpora.path.read_text(encoding="utf-8")
        text = text.replace(f'id = "{corpus.id}"', f'id = "{corpus.id}"\nnote = "mine"')
        corpora.path.write_text(
            "# typed by hand\nflavour = 3\n" + text, encoding="utf-8"
        )

        def check():
            text = corpora.path.read_text(encoding="utf-8")
            assert text.startswith("# typed by hand\nflavour = 3\n")
            assert 'note = "mine"' in text

        corpora.opened(corpus.id)
        check()
        second = corpora.add(other)
        check()
        corpora.add(folder)
        check()
        corpora.remove(second.id)
        check()

    def test_entries_that_are_not_corpora_are_kept(self, corpora, folder):
        corpora.path.parent.mkdir(parents=True)
        corpora.path.write_text(
            'version = 1\n[[corpora]]\nid = "x"\n[[corpora]]\nid = 3\npath = "p"\n',
            encoding="utf-8",
        )
        corpus = corpora.add(folder)
        assert [c.id for c in corpora.all()] == [corpus.id]
        assert len(read(corpora)["corpora"]) == 3

    def test_unreadable_file_is_set_aside(self, corpora):
        corpora.path.parent.mkdir(parents=True)
        corpora.path.write_bytes(b"= broken")
        assert corpora.all() == []
        assert corpora.set_aside_to.read_bytes() == b"= broken"
        assert corpora.problem
        assert not corpora.path.exists()

    def test_corpora_that_are_not_tables_are_set_aside(self, corpora):
        corpora.path.parent.mkdir(parents=True)
        corpora.path.write_text('version = 1\ncorpora = "x"\n', encoding="utf-8")
        assert corpora.all() == []
        assert corpora.set_aside_to is not None
        assert "list of tables" in corpora.problem

    def test_default_path_is_decided_at_construction(self, tmp_path, monkeypatch):
        from tilia_core import state

        monkeypatch.setattr(state, "state_dir", lambda: tmp_path / "here")
        assert Corpora().path == tmp_path / "here" / "library.toml"


class TestApi:
    @pytest.fixture
    def served(self, corpora):
        server = LibraryServer(FixtureBackend())
        library_api.register(server, corpora)
        server.start()
        yield server
        server.stop()

    def call(self, server, method, path, body=None):
        headers = {"Authorization": f"Bearer {server.token}"}
        data = None
        if method != "GET":
            headers["Content-Type"] = "application/json"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        reply = send(server, method, path, headers, data)
        return reply.status, (json.loads(reply.body) if reply.body else None)

    def test_empty(self, served):
        assert self.call(served, "GET", "/api/library") == (
            200,
            {
                "corpora": [],
                "last_corpus": None,
                "how_to_add": "tilia library FOLDER",
                "notices": [],
            },
        )

    def test_add_list_remove(self, served, folder):
        status, body = self.call(served, "POST", "/api/corpora", {"path": str(folder)})
        assert status == 200
        cid = body["id"]
        _, listing = self.call(served, "GET", "/api/library")
        assert listing == {
            "corpora": [
                {
                    "id": cid,
                    "name": "Mozart",
                    "path": str(folder.resolve()),
                    "available": True,
                    "files": None,
                    "unreadable": None,
                    "unavailable": None,
                }
            ],
            "last_corpus": cid,
            "notices": [],
        }
        assert self.call(served, "DELETE", f"/api/corpora/{cid}") == (204, None)
        assert self.call(served, "GET", "/api/library")[1]["corpora"] == []

    def test_bad_additions(self, served, folder):
        for body in (
            {"path": str(folder / "a.tla")},
            {"path": str(folder / "missing")},
            {"path": "relative/folder"},
            {"folder": str(folder)},
            {"path": 3},
            ["x"],
        ):
            status, answer = self.call(served, "POST", "/api/corpora", body)
            assert status == 400, body
            assert "error" in answer
        status, answer = self.call(
            served, "POST", "/api/corpora", {"path": str(folder / "a.tla")}
        )
        assert answer["error"] == f"{folder / 'a.tla'} is not a folder"

    def test_unknown_corpus(self, served):
        assert self.call(served, "DELETE", "/api/corpora/nope") == (
            404,
            {"error": "unknown corpus"},
        )

    def test_missing_folder_is_unavailable(self, served, folder):
        self.call(served, "POST", "/api/corpora", {"path": str(folder)})
        (folder / "a.tla").unlink()
        folder.rmdir()
        _, listing = self.call(served, "GET", "/api/library")
        assert listing["corpora"][0]["available"] is False

    def test_notice_when_the_file_was_set_aside(self, tmp_path):
        path = tmp_path / "library.toml"
        path.write_bytes(b"= broken")
        corpora = Corpora(path)
        server = LibraryServer(FixtureBackend())
        library_api.register(server, corpora)
        server.start()
        try:
            _, listing = self.call(server, "GET", "/api/library")
        finally:
            server.stop()
        [notice] = listing["notices"]
        assert notice == (
            f"library.toml couldn't be read; kept as {corpora.set_aside_to.name}"
            ", starting with no corpora"
        )
