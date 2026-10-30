"""Tags and generator marks in old files' comments, moved into metadata.

The prototype in `tla-corpus-ui` keeps a component's tags, and marks of what
it generated, in the component's comments, as tokens among the analyst's own
text: `tag=VALUE` and `gen=VALUE`. Tokens are separated by whitespace or `|`,
as the prototype's `_split_provenance` splits them, and a token is a mark
when its text before the first `=` is `tag` or `gen`, in that letter case.

The migration moves each mark into the component's metadata: `tag=` values
into `tags`, in order and without repeats, and `gen=` values into
`generated_by`, a text, or a list in order when there are several. The
comment is rebuilt by cutting each mark out of the original text, with one
separator next to it: the one before it, or, when the one before was cut with
an earlier mark or there is none, the one after it. So the rest keeps its
spacing character for character, where joining the remaining tokens again,
as the prototype does, would change it. Other `key=value` tokens, the s4
pipeline's `src_start=`, `src_end=` and `true_end=` among them, stay in the
comment (TimeLineAnnotator/project-management#180).
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


def split(comment: str) -> Marks:
    """`comment`'s marks, their values in NFC, and the comment without them."""
    marks = Marks(comment)
    if _TAG not in comment and _GEN not in comment:
        return marks
    kept: list[str] = []
    cut_to = 0  # where the last cut ended
    for start, end in _tokens(comment):
        token = comment[start:end]
        if token.startswith(_TAG):
            tag = nfc_text(token[len(_TAG) :])
            if tag not in marks.tags:
                marks.tags.append(tag)
        elif token.startswith(_GEN):
            marks.generated_by.append(nfc_text(token[len(_GEN) :]))
        else:
            continue
        marks.count += 1
        # A token is a run between separators, so a separator is next to it
        # wherever it doesn't start or end the comment.
        if start > cut_to:
            start -= 1  # the separator before it
        elif end < len(comment):
            end += 1  # the separator after it
        kept.append(comment[cut_to:start])
        cut_to = end
    kept.append(comment[cut_to:])
    marks.comment = "".join(kept)
    return marks


def _texts(metadata: dict[str, Any], name: str) -> list[str] | None:
    """A field's value as a list of texts: an empty one when it is missing,
    and None when it isn't a value a field may hold."""
    if name not in metadata:
        return []
    value = metadata[name]
    if not is_field_value(value):
        return None
    return [value] if isinstance(value, str) else list(value)


def move(component: dict[str, Any]) -> int:
    """Move the marks in an old component's `comments` into its metadata, in
    place, and give how many were moved.

    A component that already has `tags` or `generated_by`, which only a file
    edited by hand can have, keeps them first: new tags that aren't among
    them follow, and the generators make a list with its own. Where the
    metadata isn't an object, or a `tags` or `generated_by` in it isn't a
    text or a list of texts, which the reader then refuses, nothing moves.
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
    if marks.tags:
        had = {nfc_text(tag) for tag in tags}
        metadata["tags"] = tags + [tag for tag in marks.tags if tag not in had]
    if marks.generated_by:
        generators = generated_by + marks.generated_by
        metadata["generated_by"] = generators[0] if len(generators) == 1 else generators
    component["metadata"] = metadata
    component["comments"] = marks.comment
    return marks.count
