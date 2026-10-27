"""Statements written from category selections.

The categories panel turns chips into query language: a selection of categories, and an edit of the components in it.
TQL's parser isn't part of this package, so the few rules that decide whether something can be written are here.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

FIELDS = ("label", "color", "comments")
KEYWORDS = frozenset(
    "THEN OR NOT AND IN WHERE WITHIN DURING CONTAINS STARTS ENDS CONSISTS SAME "
    "OVERLAPS BEFORE AFTER".split()
)
_FORBIDDEN = re.compile(r'[\s\[\](){}",=<>!~/$@]')
_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")


class Refused(ValueError):
    """A selection or an edit the language can't say; ``str(error)`` is for the user."""


def as_word(category: str) -> str | None:
    """The category as a TQL word (NFC), or None when it can't be one."""
    word = unicodedata.normalize("NFC", category)
    if not word or _FORBIDDEN.search(word) or "->" in word:
        return None
    if word.startswith("--") or word.endswith(("+", "?", "*")):
        return None
    if any(not part for part in word.split(".")):
        return None
    if word.upper() in KEYWORDS:
        return None
    return word


def selection(categories: Sequence[str], mode: str, grammar: bool) -> str:
    """The query that selects the categories: any of them, or all in one component."""
    if mode not in ("any", "all"):
        raise Refused('mode is "any" or "all"')
    if not categories:
        raise Refused("select a category")
    words: list[str] = []
    for category in categories:
        word = as_word(category)
        if word is None:
            raise Refused(
                f"{category!r} can't be written in the query language yet: "
                "a category in a query is one word"
            )
        if word not in words:
            words.append(word)
    if mode == "all" and not grammar:
        raise Refused(
            '"all" needs a label grammar: without one, a label has one category'
        )
    return ("/" if mode == "all" else " OR ").join(words)


def _quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _slashes_escaped(pattern: str) -> str:
    """The pattern with each ``/`` written ``\\/``; an escape already there is kept."""
    out: list[str] = []
    chars = iter(pattern)
    for char in chars:
        if char == "\\":
            out.append(char + next(chars, ""))
        elif char == "/":
            out.append("\\/")
        else:
            out.append(char)
    return "".join(out)


def _field(field: str) -> str:
    if field not in FIELDS:
        raise Refused("field is label, color or comments")
    return field


def set_statement(
    categories: Sequence[str], mode: str, grammar: bool, field: str, value: str
) -> str:
    """``<selection> -> SET field = "value"``."""
    where = selection(categories, mode, grammar)
    _field(field)
    if field == "color" and not _COLOUR.fullmatch(value):
        raise Refused("a colour is #rrggbb")
    return f'{where} -> SET {field} = "{_quoted(value)}"'


def replace_statement(
    categories: Sequence[str],
    mode: str,
    grammar: bool,
    field: str,
    pattern: str,
    replacement: str,
    every: bool = False,
) -> str:
    """Replace the first match of a pattern in the field of each selected component."""
    where = selection(categories, mode, grammar)
    _field(field)
    if not pattern:
        raise Refused("the pattern is empty")
    try:
        groups = re.compile(pattern).groups
    except re.error as error:
        raise Refused(f"the pattern isn't a regular expression: {error}") from None
    if groups:
        raise Refused("the pattern has groups of its own; use (?:…) instead")
    if "\\" in replacement:
        raise Refused("a replacement with \\ can't be written yet")
    if every:
        raise Refused(
            "replacing every occurrence can't be written in the query language yet"
        )
    return (
        f"{where} WHERE {field} ~ /^(.*?){_slashes_escaped(pattern)}(.*)$/ "
        f'-> SET {field} = "\\1{_quoted(replacement)}\\2"'
    )
