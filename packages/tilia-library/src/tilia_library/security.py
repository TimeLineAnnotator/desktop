"""Access checks that make the server usable only by whoever started it."""

from __future__ import annotations

import email.message
import hmac
import secrets
from dataclasses import dataclass

COOKIE_PREFIX = "tilia-library-"
CUSTOM_HEADER = "X-Tilia-Library"


def new_token() -> str:
    """Make a random token for one run of the server."""
    return secrets.token_urlsafe(32)


def cookie_name(port: int) -> str:
    """Name of the cookie that holds the token for the server on this port."""
    return f"{COOKIE_PREFIX}{port}"


def entry_cookie(port: int, token: str) -> str:
    """The whole Set-Cookie value for the entry: a session cookie, not for scripts."""
    return f"{cookie_name(port)}={token}; HttpOnly; SameSite=Lax; Path=/"


@dataclass(frozen=True)
class Verdict:
    """The outcome of checking a request: allowed (status None) or refused."""

    status: int | None
    reason: str
    credential: str | None = None


def _refuse(status: int, reason: str) -> Verdict:
    return Verdict(status, reason, None)


def host_ok(headers: email.message.Message, port: int) -> bool:
    """Whether the Host header is there once and names this server."""
    hosts = headers.get_all("Host") or []
    if len(hosts) != 1:
        return False
    host = str(hosts[0])
    return host == f"127.0.0.1:{port}" or host.lower() == f"localhost:{port}"


def _cookie_token(headers: email.message.Message, port: int) -> str | None:
    # Parsed the way browsers send cookies: they share one header across every
    # local server, so other programs' cookies can hold any characters.
    wanted = cookie_name(port)
    for line in headers.get_all("Cookie") or []:
        for piece in str(line).split(";"):
            name, sep, value = piece.partition("=")
            if not sep or name.strip() != wanted:
                continue
            value = value.strip()
            if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value
    return None


def token_matches(given: str | None, token: str) -> bool:
    """Compare a given token with the real one in constant time."""
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
) -> Verdict:
    """Apply the Host, credential and cross-site rules to one request."""
    if not host_ok(headers, port):
        return _refuse(400, "bad Host header")

    if token_matches(_bearer_token(headers), token):
        credential = "bearer"
    elif access == "any" and token_matches(_cookie_token(headers, port), token):
        credential = "cookie"
    else:
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
        if credential == "cookie" and headers.get(CUSTOM_HEADER) != "1":
            return _refuse(403, f"missing {CUSTOM_HEADER} header")

    return Verdict(None, "ok", credential)
