"""What the index asks of a corpus's settings: the seam with the corpus manifest.

The manifest is WP15's (fields, vocabularies and manifests,
TimeLineAnnotator/project-management#19): its name, its form and what it holds.
The index reads its answers through one object, :class:`CorpusSettings`. Until
WP15 lands, every corpus has :class:`NoSettings`.
"""

from __future__ import annotations

from typing import Protocol

from tilia_core import labels

from .documents import Document, TimelineDoc


class CorpusSettings(Protocol):
    """A corpus's settings, as the index uses them.

    ``manifest_paths`` are the files the scan watches, relative to the corpus
    folder. ``role`` gives the role the manifest sets for a timeline, or None to
    leave the file's own ``role`` field; ``grammar`` the label grammar in force
    for it; ``includes`` whether a file the walk takes in belongs to the corpus
    (a manifest may only narrow). The answers depend only on the timeline and
    its document, and reading them never writes."""

    manifest_paths: tuple[str, ...]

    def role(self, timeline: TimelineDoc, document: Document) -> str | None:
        ...

    def grammar(self, timeline: TimelineDoc, document: Document) -> labels.LabelGrammar:
        ...

    def includes(self, path: str) -> bool:
        ...


class NoSettings:
    """The settings of a corpus without a manifest: no manifest files, no role
    set (each timeline keeps its own), every label read whole
    (:class:`~tilia_core.labels.WholeLabel`, TimeLineAnnotator/project-management#62),
    and every file included."""

    manifest_paths: tuple[str, ...] = ()

    def role(self, timeline: TimelineDoc, document: Document) -> str | None:
        return None

    def grammar(self, timeline: TimelineDoc, document: Document) -> labels.LabelGrammar:
        return labels.WholeLabel()

    def includes(self, path: str) -> bool:
        return True
