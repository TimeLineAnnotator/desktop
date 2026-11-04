"""The core's rules for a valid component, applied to a whole document.

The reader keeps what breaks a rule, with a warning per broken rule, and the
problems it found as they were read (FR-053). The writer refuses any other
problem, and writes back those it finds there, on what hasn't changed since
(FR-054). The rules are `tilia_core.rules`', and a beat pattern's is
`tilia_core.timemap.pattern.parse` (FR-084): this module has none of its own.

A problem between two components is found on each, so it is reported once, on
the first. Beyond that, what counts as one problem is a rule and what it is
about, as they were read: `ReadProblem`. A component in conflict with several
others has one of them for each, so that taking one of the others away leaves
the rest as they were read.

A beat without a time has its warning from the check, which names its
timeline (TimeLineAnnotator/project-management#285), so the rule it breaks adds
none. It is one of the document's problems all the same: written back while it
is unchanged, and refused when it is new.

A media length that isn't one says nothing about the components, so that they
aren't compared with it, as with one that is unknown (a quarters file has none
to compare its times with, FR-080). The PDF of a PDF timeline isn't opened, so
a page number is checked only against the rules that need no PDF
(TimeLineAnnotator/project-management#423).
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Callable, Iterator
from typing import Any

from tilia_core import rules
from tilia_core.tla.errors import printable
from tilia_core.tla.layout import pointer_to
from tilia_core.tla.model import (
    Component,
    Document,
    ReadProblem,
    ReadWarning,
    Timeline,
    UnknownKind,
)
from tilia_core.tla.parse import lines_of, text_of

# How many other components a warning names, and is compared on when written.
# In a file with thousands of components at one time, each is at odds with all
# the others, which no warning could list.
_NAMED_OTHERS = 10
# The reason the rules give for a beat without a time.
_NO_TIME = rules.not_valid("time", None)


def keep_problems(
    document: Document,
    source: str | bytes,
    where: Callable[[str], str] | None = None,
) -> None:
    """Give `document`, just read, what it breaks: its `read_problems`, and a
    warning for each, after those it has. `source` is what it was read from,
    for lines. `where` takes a place in the document to the place to name, in
    what it was read from."""
    document.read_problems = find_problems(document)
    not_warned = [p for p in document.read_problems if not p.warned]
    document.warnings.extend(warnings_of(not_warned, source, where))
    unable = cant_check(document)
    if unable is not None:
        document.warnings.append(
            ReadWarning(
                place="",
                line=None,
                message="a harmony's quality and inversion and a mode's type weren't"
                f" checked: {printable(str(unable))}",
            )
        )


def find_problems(document: Document) -> list[ReadProblem]:
    """Every rule `document` breaks, in the order of the file."""
    found = []
    media_length = rules.media_length(document.media_length)
    length: float = math.inf
    if not media_length:
        found.append(
            ReadProblem(
                reason=media_length.reason,
                place="/media/length",
                state=_state(document.media_length),
            )
        )
    elif document.time_unit == "seconds" and document.media_length is not None:
        length = document.media_length
    for timeline_id, timeline in document.timelines.items():
        place = pointer_to("/timelines", timeline_id)
        if timeline.kind == "beat":
            found.extend(_beat_pattern_problems(timeline, place))
        elif timeline.kind == "range":
            found.extend(_row_problems(timeline, place))
        if timeline.components:
            found.extend(_component_problems(timeline, place, length))
    return found


def new_problems(
    written: list[ReadProblem], read: list[ReadProblem]
) -> list[ReadProblem]:
    """Those of `written` that aren't among `read`, the problems a document
    was read with: for a component at odds with others, with those others
    that aren't. A problem about a component changed since has a state that
    isn't among them, and neither has one about an other component changed
    since."""
    others_read: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
    for problem in read:
        others_read.setdefault(_about(problem), set()).update(problem.others)
    new = []
    for problem in written:
        known = others_read.get(_about(problem))
        if known is None:
            new.append(problem)
            continue
        others = tuple(other for other in problem.others if other not in known)
        if others:
            new.append(dataclasses.replace(problem, others=others))
    return new


def warnings_of(
    problems: list[ReadProblem],
    source: str | bytes,
    where: Callable[[str], str] | None = None,
) -> list[ReadWarning]:
    """A warning for each of `problems`: its place and line in `source`, its
    reason, and the other components it is about, each named by its place, so
    that an old file's are in its own terms. `where` is `keep_problems`'."""
    if not problems:
        return []

    def named(place: str) -> str:
        return place if where is None else where(place)

    places = {problem.place for problem in problems}
    places.update(other for problem in problems for other, _ in problem.others)
    lines = lines_of(text_of(source), [named(place) for place in places])
    warnings = []
    for problem in problems:
        place = named(problem.place)
        message = printable(problem.reason)
        if problem.others:
            others = [
                f"line {lines[named(other)]}, {named(other)}"
                for other, _ in problem.others
            ]
            if problem.more:
                others.append(f"and {problem.more} more")
            what = "other component" if len(others) == 1 else "other components"
            message = f"{message} ({what}: {'; '.join(others)})"
        warnings.append(ReadWarning(place=place, line=lines[place], message=message))
    return warnings


def cant_check(document: Document) -> rules.CantCheck | None:
    """What can't be checked in `document` for want of music21: a harmony's
    quality and inversion and a mode's type. None when it has neither."""
    for timeline in document.timelines.values():
        if timeline.kind != "harmony":
            continue
        for component in timeline.components.values():
            # All a harmony timeline holds, but what is kept as it is.
            if not isinstance(component.kind, UnknownKind):
                return rules.cant_check(component.kind)
    return None


def _about(problem: ReadProblem) -> tuple[str, str, str]:
    return problem.reason, problem.place, problem.state


def _beat_pattern_problems(timeline: Timeline, place: str) -> Iterator[ReadProblem]:
    # Imported here: the time map's package reads `tla`.
    from tilia_core.timemap.pattern import parse

    pattern = timeline.attrs.get("beat_pattern")
    if isinstance(pattern, str) and not parse(pattern).is_complete:
        name = f"the timeline {json.dumps(timeline.name, ensure_ascii=False)}"
        shown = json.dumps(pattern, ensure_ascii=False)
        yield ReadProblem(
            reason=f"the beat pattern {shown} of {name} isn't a valid pattern",
            place=pointer_to(place, "beat_pattern"),
            state=_state(pattern),
        )


def _row_problems(timeline: Timeline, place: str) -> Iterator[ReadProblem]:
    rows = timeline.attrs.get("rows")
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows):
        # Two rows with one id are refused as a broken structure.
        for outcome in (
            rules.range_rows([{**row, "color": None}]),
            rules.color(row.get("color")),
        ):
            if not outcome:
                yield ReadProblem(
                    reason=outcome.reason,
                    place=pointer_to(pointer_to(place, "rows"), index),
                    state=_state(row),
                )


def _component_problems(
    timeline: Timeline, place: str, length: float
) -> Iterator[ReadProblem]:
    components = timeline.components
    found = rules.check_timeline(
        length,
        components.values(),
        rows=timeline.attrs.get("rows"),
        page_count=math.inf,
        every_rule=True,
    )
    held = pointer_to(place, "components")
    named: set[tuple[str, str, str]] = set()  # each rule's pairs named so far
    for component_id, checked in found.items():
        at = pointer_to(held, component_id)
        state = _component_state(components[component_id])
        for outcome in (checked.outcome, *checked.also, checked.color):
            if outcome.ok:
                continue
            reason = outcome.reason
            others = [
                other
                for other in outcome.others
                if (reason, other, component_id) not in named
            ]
            if outcome.others and not others:
                continue  # all of them named this one
            kept = others[:_NAMED_OTHERS]
            named.update((reason, component_id, other) for other in kept)
            yield ReadProblem(
                reason=reason,
                place=at,
                state=state,
                others=tuple(
                    (
                        pointer_to(held, other),
                        _component_state(components[other]),
                    )
                    for other in kept
                ),
                more=len(others) - len(kept),
                warned=components[component_id].kind == "beat" and reason == _NO_TIME,
            )


def _component_state(component: Component) -> str:
    """Everything a component has, as a text to compare."""
    return _state(
        [str(component.kind), component.attrs, component.metadata, component.extra]
    )


def _state(value: Any) -> str:
    """`value` as it was read, to compare: 1 and 1.0 and True aren't the same."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
