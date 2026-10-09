"""The media routes: what plays for a file, and its local file, streamed."""

from __future__ import annotations

import re
from pathlib import Path

from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.media import CONTENT_TYPES, RangeNotSatisfiable, parse_range
from tilia_library.server import (
    ApiError,
    LibraryServer,
    Request,
    Response,
    error_response,
    json_response,
)

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def register(server: LibraryServer, corpora: Corpora, handles: CorpusHandles) -> None:
    """Add the media routes to the server."""

    def media_of(request: Request) -> dict:
        try:
            _, handle = handles.get(request.params["cid"])
        except KeyError:
            raise ApiError(404, "unknown corpus") from None
        try:
            return server.backend.media_of(handle, request.params["file"])
        except KeyError:
            raise ApiError(404, "unknown file") from None

    def get_media(request: Request) -> Response:
        media = media_of(request)
        kind = media.get("kind") or "none"
        youtube_id = media.get("youtube_id")
        reason = media.get("reason")
        if kind == "youtube" and not (
            isinstance(youtube_id, str) and YOUTUBE_ID.match(youtube_id)
        ):
            kind, youtube_id, reason = "none", None, "the YouTube link isn't valid"
        return json_response(
            {
                "kind": kind,
                "youtube_id": youtube_id if kind == "youtube" else None,
                "length": media.get("length"),
                "reason": reason,
            }
        )

    def stream(request: Request) -> Response:
        media = media_of(request)
        if media.get("kind") != "local" or not media.get("path"):
            raise ApiError(404, "no local media")
        path = Path(media["path"])
        try:
            size = path.stat().st_size if path.is_file() else None
        except OSError:
            size = None
        if size is None:
            raise ApiError(404, "the media file is missing")
        content_type = CONTENT_TYPES.get(path.suffix.lower())
        if content_type is None:
            raise ApiError(415, "unsupported media type")
        headers = {"Accept-Ranges": "bytes"}
        try:
            wanted = parse_range(request.headers.get("Range"), size)
        except RangeNotSatisfiable:
            headers["Content-Range"] = f"bytes */{size}"
            response = error_response(416, "range not satisfiable")
            response.headers.update(headers)
            return response
        if wanted is None:
            return Response(200, b"", content_type, headers, file=(path, 0, size))
        start, end = wanted
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(
            206, b"", content_type, headers, file=(path, start, end - start + 1)
        )

    server.router.add("GET", "/api/{cid}/media/{file}", get_media)
    server.router.add("GET", "/api/{cid}/media/{file}/stream", stream)
