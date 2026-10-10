"""Unicode rules and the label-grammar protocol shared by TQL's parser and index.

Words in queries and labels in a corpus compare in one folded form, and a
label grammar says how a corpus's labels split into categories.
"""

import unicodedata
from typing import Protocol


def nfc(s: str) -> str:
    """``s`` in Unicode's composed normal form (NFC): "ä" typed as one
    character and as "a" plus a combining mark become the same text."""
    return unicodedata.normalize("NFC", s)


def fold(s: str) -> str:
    """``s`` for comparing words and labels: one normal form and full case
    folding, so ``STRASSE`` finds "Straße" and ``ΚΟΣΜΟΣ`` "κοσμος" —
    Unicode's canonical caseless match, written out as NFC."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", s).casefold())


class LabelGrammar(Protocol):
    """How a corpus's labels split into categories."""

    def categories(self, label: str) -> tuple[str, ...]:
        """The label's categories as folded strings; a dot inside a category
        marks a subtype. Empty for an empty label."""
        ...

    def group(self, category: str) -> str | None:
        """The grammar's group for ``category``, or None."""
        ...


class WholeLabel:
    """The rule when a corpus names no label grammar: the whole label, folded,
    is its one category, and there are no groups."""

    def categories(self, label: str) -> tuple[str, ...]:
        stripped = label.strip()
        return (fold(stripped),) if stripped else ()

    def group(self, category: str) -> str | None:
        return None
