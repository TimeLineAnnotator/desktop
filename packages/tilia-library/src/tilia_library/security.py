"""Access checks that make the server usable only by whoever started it.

No secret is kept in a cookie: browsers keep cookies per host, not per port, so
a cookie set on 127.0.0.1 would go to every local server the user visits. The
token travels as a header, ``Authorization: Bearer <token>``, from programs and
from the page alike. The page gets it once, in the address's fragment.
"""

from __future__ import annotations

import email.message
import hmac
import secrets
from dataclasses import dataclass

# The query parameter that carries the media key: <audio> can't send a header.
MEDIA_PARAM = "media_key"


def new_token() -> str:
    """Make a random secret for one run of the server."""
    return secrets.token_urlsafe(32)


def entry_url(address: str, token: str) -> str:
    """The address that hands the page the token.

    The token is in the fragment, which a browser never sends to any server, so
    it can't reach a log or a ``Referer``. The page takes it and cleans the address.
    """
    return f"{address}#token={token}"


@dataclass(frozen=True)
class Verdict:
    """The outcome of checking a request: allowed (status None) or refused."""

    status: int | None
    reason: str


def _refuse(status: int, reason: str) -> Verdict:
    return Verdict(status, reason)


def host_ok(headers: email.message.Message, port: int) -> bool:
    """Whether the Host header is there once and names this server."""
    hosts = headers.get_all("Host") or []
    if len(hosts) != 1:
        return False
    host = str(hosts[0])
    return host == f"127.0.0.1:{port}" or host.lower() == f"localhost:{port}"


def token_matches(given: str | None, token: str) -> bool:
    """Compare a given secret with the real one in constant time."""
    if given is None:
        return False
    return hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def _bearer_token(headers: email.message.Message) -> str | None:
    value = headers.get("Authorization")
    if value is None:
        return None
    scheme, _, rest = str(value).partition(" ")
    if scheme.lower() != "bearer":
        return None
    return rest.strip()


def check_request(
    method: str,
    headers: email.message.Message,
    *,
    port: int,
    token: str,
    access: str,
    media_key: str = "",
    given_media_key: str | None = None,
) -> Verdict:
    """Apply the Host, credential and cross-site rules to one request.

    Nothing the browser adds by itself counts as a credential, so another page
    can't borrow one: no request of its own can carry the token or the media key.
    """
    if not host_ok(headers, port):
        return _refuse(400, "bad Host header")

    if access == "public":
        return Verdict(None, "ok")

    if not token_matches(_bearer_token(headers), token) and not (
        access == "media" and token_matches(given_media_key, media_key)
    ):
        return _refuse(403, "missing or wrong credentials")

    if method not in ("GET", "HEAD"):
        ctype = str(headers.get("Content-Type", ""))
        if ctype.partition(";")[0].strip().lower() != "application/json":
            return _refuse(403, "Content-Type must be application/json")
        origin = headers.get("Origin")
        if origin is not None and origin not in (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        ):
            return _refuse(403, "foreign Origin")

    return Verdict(None, "ok")
