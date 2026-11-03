"""Tags and generator marks in old files' comments, moved into metadata.

The prototype in `tla-corpus-ui` keeps a component's tags, and marks of what
it generated, in the component's comments, as tokens among the analyst's own
text: `tag=VALUE` and `gen=VALUE`. Tokens are separated by whitespace or `|`,
as the prototype's `_split_provenance` splits them, and a token is a mark
when it starts with `tag=` or `gen=`, in that letter case, and has a value
after it: a bare `tag=` or `gen=` stays in the comment.

The migration moves each mark into the component's metadata: `tag=` values
into `tags`, in order and without repeats, and `gen=` values into
`generated_by`, a text, or a list in order, repeats included, when there are
several. The comment is rebuilt by cutting the marks out of the original
text. Marks with only separators between them are cut out together with the
separators around them: at the start or the end of the comment, all of them;
elsewhere, all but one, the separator right after the last mark, since the
separator before a mark goes with it. A CRLF counts as one separator. So the
rest keeps its spacing character for character, where joining the remaining
tokens again, as the prototype does, would change it. Other `key=value`
tokens, the s4 pipeline's `src_start=`, `src_end=` and `true_end=` among
them, stay in the comment (TimeLineAnnotator/project-management#180, and
the eight cases of TimeLineAnnotator/project-management#362).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tilia_core.tla.check import is_field_value
from tilia_core.tla.layout import nfc_text

_TAG = "tag="
_GEN = "gen="


@dataclass
class Marks:
    """A comment's marks, and the comment without them."""

    comment: str
    tags: list[str] = field(default_factory=list)  # in order, without repeats
    generated_by: list[str] = field(default_factory=list)  # in order
    count: int = 0  # the marks cut out of the comment, repeats included


def _is_separator(char: str) -> bool:
    # Whitespace as str.split() finds it, which the prototype splits on first.
    return char == "|" or char.isspace()


def _tokens(text: str) -> Iterator[tuple[int, int]]:
    """Where each token of `text` starts and ends."""
    start: int | None = None
    for index, char in enumerate(text):
        if _is_separator(char):
            if start is not None:
                yield start, index
                start = None
        elif start is None:
            start = index
    if start is not None:
        yield start, len(text)


def _is_mark(token: str) -> bool:
    return any(token.startswith(key) and len(token) > len(key) for key in (_TAG, _GEN))


def _separator_at(text: str, index: int) -> str:
    """The separator that starts at `index` in `text`: a CRLF is one."""
    return "\r\n" if text.startswith("\r\n", index) else text[index]


def _take(marks: Marks, token: str) -> None:
    if token.startswith(_TAG):
        tag = nfc_text(token[len(_TAG) :])
        if tag not in marks.tags:
            marks.tags.append(tag)
    else:
        marks.generated_by.append(nfc_text(token[len(_GEN) :]))
    marks.count += 1


def split(comment: str) -> Marks:
    """`comment`'s marks, their values in NFC, and the comment without them."""
    marks = Marks(comment)
    if _TAG not in comment and _GEN not in comment:
        return marks
    tokens = list(_tokens(comment))
    is_mark = [_is_mark(comment[start:end]) for start, end in tokens]
    kept: list[str] = []
    cut_to = 0  # where the comment is kept from
    index = 0
    while index < len(tokens):
        if not is_mark[index]:
            index += 1
            continue
        first = index
        while index < len(tokens) and is_mark[index]:
            start, end = tokens[index]
            _take(marks, comment[start:end])
            index += 1
        # The marks, and the separators around them up to the tokens on
        # either side, or to the comment's start or end.
        cut_from = tokens[first - 1][1] if first else 0
        cut_until = tokens[index][0] if index < len(tokens) else len(comment)
        kept.append(comment[cut_to:cut_from])
        if first and index < len(tokens):
            kept.append(_separator_at(comment, tokens[index - 1][1]))
        cut_to = cut_until
    kept.append(comment[cut_to:])
    marks.comment = "".join(kept)
    return marks


def _texts(metadata: dict[str, Any], name: str) -> list[str] | None:
    """A field's value as a list of texts: an empty one when it is missing,
    an empty text or an empty list, and None when it isn't a value a field
    may hold."""
    if name not in metadata:
        return []
    value = metadata[name]
    if not is_field_value(value):
        return None
    if isinstance(value, str):
        return [value] if value else []
    return list(value)


def move(component: dict[str, Any]) -> int:
    """Move the marks in an old component's `comments` into its metadata, in
    place, and give how many were moved.

    A component that already has `tags` or `generated_by`, which only a file
    edited by hand can have, keeps them first: new tags that aren't among
    them follow, and the generators make a list with its own. A value the
    marks add nothing to is left exactly as it was, and an empty text or list
    counts as no value. Where the metadata isn't an object, or a `tags` or
    `generated_by` in it isn't a text or a list of texts, which the reader
    then refuses, nothing moves.
    """
    comments = component.get("comments")
    if not isinstance(comments, str):
        return 0
    marks = split(comments)
    if not marks.count:
        return 0
    metadata = component.get("metadata")
    if metadata is None:  # a null is a missing key
        metadata = {}
    if not isinstance(metadata, dict):
        return 0
    tags = _texts(metadata, "tags")
    generated_by = _texts(metadata, "generated_by")
    if tags is None or generated_by is None:
        return 0
    metadata = dict(metadata)
    had = {nfc_text(tag) for tag in tags}
    new_tags = [tag for tag in marks.tags if tag not in had]
    if new_tags:
        metadata["tags"] = tags + new_tags
    if marks.generated_by:
        generators = generated_by + marks.generated_by
        metadata["generated_by"] = generators[0] if len(generators) == 1 else generators
    component["metadata"] = metadata
    component["comments"] = marks.comment
    return marks.count
