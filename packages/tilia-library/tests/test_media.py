from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.corpora import Corpora
from tilia_library.media import CONTENT_TYPES, RangeNotSatisfiable, parse_range
from tilia_library.server import LibraryServer

DATA = bytes(range(256)) * 4  # 1024 bytes, each position distinguishable


class MediaBackend(FixtureBackend):
    """Answers ``media_of`` from a table the test fills in."""

    def __init__(self) -> None:
        super().__init__()
        self.media: dict[str, dict] = {}

    def media_of(self, corpus, file_id):
        if file_id not in self.media:
            raise KeyError(file_id)
        return self.media[file_id]


def _local(path, **extra):
    return {
        "kind": "local",
        "path": str(path),
        "youtube_id": None,
        "length": 3.0,
        "reason": None,
        **extra,
    }


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "piece.wav"
    path.write_bytes(DATA)
    return path


@pytest.fixture
def backend(audio, tmp_path):
    backend = MediaBackend()
    odd = tmp_path / "piece.xyz"
    odd.write_bytes(b"x")
    backend.media = {
        "local": _local(audio),
        "upper": _local(audio.with_suffix(".WAV")),
        "gone": _local(tmp_path / "gone.wav"),
        "odd": _local(odd),
        "yt": {
            "kind": "youtube",
            "path": None,
            "youtube_id": "dQw4w9WgXcQ",
            "length": None,
            "reason": None,
        },
        "badyt": {
            "kind": "youtube",
            "path": None,
            "youtube_id": "short",
            "length": None,
            "reason": None,
        },
        "none": {
            "kind": "none",
            "path": None,
            "youtube_id": None,
            "length": None,
            "reason": "the file names none",
        },
    }
    return backend


@pytest.fixture
def library(backend, tmp_path):
    corpora = Corpora(tmp_path / "library.toml")
    folder = tmp_path / "pieces"
    folder.mkdir()
    corpora.add(folder)
    server = LibraryServer(backend)
    register_all(server, corpora)
    server.start()
    server.cid = corpora.all()[0].id
    yield server
    server.stop()


def get(server, path, method="GET", **headers):
    headers["Authorization"] = f"Bearer {server.token}"
    return send(server, method, path, headers)


def stream(server, file="local", method="GET", **headers):
    return get(server, f"/api/{server.cid}/media/{file}/stream", method, **headers)


def test_content_types_table():
    assert CONTENT_TYPES == {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".oga": "audio/ogg",
        ".opus": "audio/ogg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
    }


@pytest.mark.parametrize(
    "header,expected",
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 999)),
        ("bytes=-100", (900, 999)),
        ("bytes=990-5000", (990, 999)),
        ("bytes=-5000", (0, 999)),
        ("bytes=999-999", (999, 999)),
        ("bytes=0-0,5-9", None),
        ("bytes=a-b", None),
        ("bytes=-", None),
        ("bytes=9-2", None),
        ("items=0-9", None),
        ("garbage", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_range(header, expected):
    assert parse_range(header, 1000) == expected


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=2000-3000", "bytes=-0"])
def test_parse_range_outside_the_file(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 1000)


def test_parse_range_of_an_empty_file():
    with pytest.raises(RangeNotSatisfiable):
        parse_range("bytes=0-", 0)


def test_whole_file(library):
    r = stream(library)
    assert r.status == 200
    assert r.body == DATA
    assert r.headers["content-length"] == str(len(DATA))
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["accept-ranges"] == "bytes"
    assert "content-range" not in r.headers


@pytest.mark.parametrize(
    "header,first,last",
    [
        ("bytes=0-99", 0, 99),
        ("bytes=100-", 100, 1023),
        ("bytes=-100", 924, 1023),
        ("bytes=1000-9999", 1000, 1023),
    ],
)
def test_ranges(library, header, first, last):
    r = stream(library, Range=header)
    assert r.status == 206
    assert r.body == DATA[first : last + 1]
    assert r.headers["content-range"] == f"bytes {first}-{last}/1024"
    assert r.headers["content-length"] == str(last - first + 1)
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"] == "audio/wav"


def test_range_outside_the_file(library):
    r = stream(library, Range="bytes=1024-")
    assert r.status == 416
    assert r.headers["content-range"] == "bytes */1024"
    assert r.headers["accept-ranges"] == "bytes"


def test_unusable_range_is_ignored(library):
    r = stream(library, Range="bytes=0-1,5-6")
    assert r.status == 200
    assert r.body == DATA


def test_head_sends_no_body(library):
    r = stream(library, method="HEAD")
    assert r.status == 200
    assert r.body == b""
    assert r.headers["content-length"] == str(len(DATA))
    r = stream(library, method="HEAD", Range="bytes=0-9")
    assert r.status == 206
    assert r.body == b""
    assert r.headers["content-length"] == "10"


def test_extension_is_matched_in_lower_case(library, tmp_path):
    (tmp_path / "piece.WAV").write_bytes(b"abc")
    r = stream(library, "upper")
    assert r.status == 200
    assert r.headers["content-type"] == "audio/wav"


def test_missing_file(library):
    r = stream(library, "gone")
    assert r.status == 404
    assert json.loads(r.body) == {"error": "the media file is missing"}


@pytest.mark.parametrize("file", ["yt", "badyt", "none"])
def test_nothing_to_stream_for_other_kinds(library, file):
    r = stream(library, file)
    assert r.status == 404
    assert json.loads(r.body) == {"error": "no local media"}


def test_unsupported_type(library):
    r = stream(library, "odd")
    assert r.status == 415
    assert json.loads(r.body) == {"error": "unsupported media type"}


def test_a_path_is_never_taken_from_the_request(library):
    for file in ("..%2F..%2Fetc%2Fpasswd", "%2Fetc%2Fpasswd", "..%5C..%5Cx"):
        assert stream(library, file).status == 404
    assert get(library, f"/api/{library.cid}/media/..%2F..%2Fetc").status == 404


def test_unknown_corpus_and_file(library):
    assert get(library, "/api/nope/media/local").status == 404
    assert get(library, "/api/nope/media/local/stream").status == 404
    assert get(library, f"/api/{library.cid}/media/nope").status == 404
    assert stream(library, "nope").status == 404


def test_info_for_each_kind(library):
    def info(file):
        r = get(library, f"/api/{library.cid}/media/{file}")
        assert r.status == 200
        return json.loads(r.body)

    assert info("local") == {
        "kind": "local",
        "youtube_id": None,
        "length": 3.0,
        "reason": None,
        "stream": f"/api/{library.cid}/media/local/stream?media_key={library.media_key}",
    }
    assert info("yt") == {
        "kind": "youtube",
        "youtube_id": "dQw4w9WgXcQ",
        "length": None,
        "reason": None,
        "stream": None,
    }
    assert info("none") == {
        "kind": "none",
        "youtube_id": None,
        "length": None,
        "reason": "the file names none",
        "stream": None,
    }
    assert info("badyt") == {
        "kind": "none",
        "youtube_id": None,
        "length": None,
        "reason": "the YouTube link isn't valid",
        "stream": None,
    }


def test_info_never_shows_the_path(library, audio):
    r = get(library, f"/api/{library.cid}/media/local")
    assert str(audio.parent).encode() not in r.body


def test_a_large_file_is_streamed_not_read_whole(
    library, backend, tmp_path, monkeypatch
):
    big = tmp_path / "big.mp3"
    size = 5 * 1024 * 1024 + 123
    with big.open("wb") as out:
        out.write(b"\x01" * (size - 1))
        out.write(b"\x02")
    backend.media["big"] = _local(big)

    original = Path.read_bytes

    def refuse(self, *args, **kwargs):
        if self == big:
            raise AssertionError("the media file was read whole")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    r = stream(library, "big")
    assert r.status == 200
    assert len(r.body) == size
    assert r.body[-1] == 2
    r = stream(library, "big", Range=f"bytes={size - 2}-")
    assert r.status == 206
    assert r.body == b"\x01\x02"


# The media key: what an <audio> element sends, since it can't send a header.
def stream_address(server, file="local"):
    r = get(server, f"/api/{server.cid}/media/{file}")
    return json.loads(r.body)["stream"]


def test_the_stream_address_plays_without_the_header(library):
    r = send(library, "GET", stream_address(library))
    assert r.status == 200
    assert r.body == DATA
    r = send(library, "GET", stream_address(library), {"Range": "bytes=0-9"})
    assert r.status == 206
    assert r.body == DATA[:10]
    r = send(library, "HEAD", stream_address(library))
    assert r.status == 200
    assert r.body == b""


def test_the_stream_is_refused_without_the_key(library):
    path = f"/api/{library.cid}/media/local/stream"
    assert send(library, "GET", path).status == 403
    assert send(library, "GET", f"{path}?media_key=nope").status == 403
    assert send(library, "GET", f"{path}?media_key=").status == 403
    assert send(library, "GET", f"{path}?media_key={library.token}").status == 403
    assert send(library, "GET", f"{path}?token={library.token}").status == 403
    assert send(library, "GET", f"{path}?token={library.media_key}").status == 403


def test_the_key_is_not_the_token(library):
    assert library.media_key
    assert library.media_key != library.token


def test_the_key_is_useless_on_every_other_route(library):
    key = library.media_key
    for route in library.router.routes:
        if route.access != "bearer":
            continue
        path = re.sub(r"\{(\w+)(?::path)?\}", "v", route.pattern)
        path = path.replace("/api/v/", f"/api/{library.cid}/", 1)
        headers = {"Content-Type": "application/json"}
        body = None if route.method == "GET" else b"{}"
        for given, extra in (
            (f"{path}?media_key={key}", {}),
            (path, {"Authorization": f"Bearer {key}"}),
        ):
            r = send(library, route.method, given, {**headers, **extra}, body)
            assert r.status == 403, (route.method, route.pattern)


def test_the_key_only_reads(library):
    # Another method on the stream's path doesn't fall back on the route's access.
    path = stream_address(library)
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        r = send(library, method, path, {"Content-Type": "application/json"}, b"{}")
        assert r.status == 403, method


def test_the_key_is_not_logged(library, caplog):
    address = stream_address(library)
    with caplog.at_level(logging.DEBUG):
        assert send(library, "GET", address).status == 200
    assert caplog.records
    for record in caplog.records:
        assert library.media_key not in record.getMessage()
    assert any("media_key=…" in r.getMessage() for r in caplog.records)
