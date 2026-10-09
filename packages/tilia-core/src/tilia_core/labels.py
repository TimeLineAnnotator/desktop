"""Unicode rules for text in files and labels."""

import unicodedata


def nfc(s: str) -> str:
    """``s`` in Unicode's composed normal form (NFC): "ä" typed as one
    character and as "a" plus a combining mark become the same text."""
    return unicodedata.normalize("NFC", s)
