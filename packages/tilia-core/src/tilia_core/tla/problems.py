"""The core's rules for a valid component, applied to a whole document.

The reader keeps what breaks a rule, with a warning per broken rule, and the
problems it found as they were read (FR-053). The writer refuses any other
problem, and writes back those it finds there, on what hasn't changed since
(FR-054). The rules are `tilia_core.rules`', and a beat pattern's is
`tilia_core.timemap.pattern.parse` (FR-084): this module has none of its own.

A problem between two components is found on each, so it is reported once, on
the first.

What tells an old problem from a new one is what is wrong, not how it reads
(TimeLineAnnotator/project-management#494): the rule's code, and the id of what
it is about. A reason quotes values and a position moves with an edit made
elsewhere, so neither is compared. A problem is old while what it is about hasn't
changed: its state, everything a component or a row holds, as the writer writes
it. A problem between components is about the others too, and is new when one of
them has changed or been added; one taken away takes nothing from the rest. A
rule between two components reads only those two, so if neither has changed, they
were at odds when read, and no pair needs keeping.

The rules read a media length, so a new one can change what an unchanged component
breaks. For one read past the end of the old one, past the end of the new one is
the same problem. When no length was read, no time was compared with any, so the
same goes for every component once one is given. Their states are kept for that:
`unmeasured`. A known length that puts a time past it for the first time is a new
problem, since what the file came with kept to its length: TiLiA leaves nothing
past the end when it scales or crops (TimeLineAnnotator/project-management#496,
point 1).

A beat without a time has its warning from the check, which names its
timeline (TimeLineAnnotator/project-management#285), so the rule it breaks adds
none. It is one of the document's problems all the same: written back while it
is unchanged, and refused when it is new.

A media length that isn't one says nothing about the components, so that they
aren't compared with it, as with one that is unknown (a quarters file has none
to compare its times with, FR-080). The PDF of a PDF timeline isn't opened, so
a page number is checked only against the rules that need no PDF
(TimeLineAnnotator/project-management#423).

TiLiA allows an edit that fixes one of a component's problems and adds none, so
that a component with two can be fixed one at a time (WP6's FR-062), and then
calls `keep_read_problems`: the problems the component still has, which it was
read with, are old as it now is too, beside what it was read as, which an undo
gives back (TimeLineAnnotator/project-management#439). A place can so have more
than one state that is old.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from tilia_core import rules
from tilia_core.tla.errors import UnreadableFile, printable
from tilia_core.tla.layout import ids_at, pointer_to
from tilia_core.tla.model import (
    TIMELINE_COMPONENTS,
    Component,
    Document,
    ReadProblem,
    ReadWarning,
    Timeline,
    UnknownKind,
    component_kind_from_file,
)
from tilia_core.tla.parse import lines_of, text_of

# How many other components a warning names. In a file with thousands of
# components at one time, each is at odds with all the others, which no warning
# could list. Everything at odds with another is among those named, or has a
# problem of its own, so this is for reading and takes nothing from what a write
# compares.
_NAMED_OTHERS = 10
# A beat pattern's rule is `tilia_core.timemap.pattern.parse`'s, which has no code.
_BAD_BEAT_PATTERN = rules.bad_code("beat_pattern")
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
    document.read_unmeasured = unmeasured(document)
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
    if not media_length:
        found.append(
            ReadProblem(
                code=media_length.code,
                reason=media_length.reason,
                place="/media/length",
                state=_state(document.media_length),
            )
        )
    length = _length(document)
    for timeline_id, timeline in document.timelines.items():
        place = pointer_to("/timelines", timeline_id)
        if timeline.kind == "beat":
            found.extend(_beat_pattern_problems(timeline, place))
        elif timeline.kind == "range":
            found.extend(_row_problems(timeline, place))
        if timeline.components:
            found.extend(_component_problems(timeline, place, length))
    return found


def _length(document: Document) -> float:
    """The media length `document`'s times are compared with: none, when it has
    none, or none in seconds, or one that isn't one."""
    length = document.media_length
    if length is None or document.time_unit != "seconds":
        return math.inf
    return length if rules.media_length(length) else math.inf


def unmeasured(document: Document) -> dict[str, str]:
    """The state of each component of `document`, by its place, when it has no
    media length for their times to be compared with; else nothing. A quarters
    file's aren't compared with one anyway."""
    if document.media_length is not None or document.time_unit != "seconds":
        return {}
    states = {}
    for timeline_id, timeline in document.timelines.items():
        held = pointer_to(pointer_to("/timelines", timeline_id), "components")
        holds = TIMELINE_COMPONENTS.get(timeline.kind, frozenset())
        for component_id, component in timeline.components.items():
            if component.kind in rules.KINDS:
                at = pointer_to(held, component_id)
                states[at] = _component_state(component, at, holds)
    return states


def new_problems(
    written: list[ReadProblem],
    read: list[ReadProblem],
    read_unmeasured: Mapping[str, str],
) -> list[ReadProblem]:
    """Those of `written` that aren't among `read`, the problems a document was
    read with, whose `read_unmeasured` were its components with no media length.

    One on what has changed since, or for a rule it didn't break, is new. One
    between components, on what hasn't changed, is new for the others that have
    changed or been added, and is given with those others alone. Its code and
    its place decide: what it reads is its reason, and it may read otherwise.
    What `keep_read_problems` kept is among `read`."""
    was = _Read(read)
    new = []
    for problem in written:
        place = problem.place
        if (
            problem.code == rules.PAST_MEDIA_END
            and read_unmeasured.get(place) == problem.state
        ):
            continue  # its time wasn't compared with any
        if not was.has(problem):
            new.append(problem)
            continue
        changed = was.changed(problem)
        if changed:
            # A refusal names those that are new. A join's others are what comes
            # next in its row, whichever of them it was that changed.
            if problem.joined is None:
                problem = dataclasses.replace(problem, others=changed)
            new.append(problem)
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

    places = {problem.pointer or problem.place for problem in problems}
    places.update(other for problem in problems for other, _ in problem.others)
    lines = lines_of(text_of(source), [named(place) for place in places])
    warnings = []
    for problem in problems:
        place = named(problem.pointer or problem.place)
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
        warnings.append(
            ReadWarning(place, lines[place], message, *ids_at(problem.place))
        )
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


def keep_read_problems(document: Document, component_id: str) -> None:
    """Keep the problems the component `component_id` of `document` still has,
    which the document was read with, as ones it came with: a write then writes
    them back with the component as it is now, as it would were it unchanged
    (FR-054). TiLiA calls it after an edit that fixes one of the component's
    problems and adds none, which it allows, so that its save isn't refused
    (WP6's FR-062; TimeLineAnnotator/project-management#436, point 1). For any
    other caller, such as a bulk edit or a script, FR-054 is as it was.

    A problem of the component alone is kept when the document was read with
    one of its code on the component. In a document read with no media length,
    whose times weren't compared with any, a time past the end is kept too when
    the component as it was read is past the end of the length it now has. A
    problem between the component and others, such as a crossing, is kept when
    it was read between them by the same rule, whichever of them it was named
    on, with the others as they were then; its join, when it was read joining the
    same range, as that range was. A join to it is the problem of the range that
    joins, and stays new (TimeLineAnnotator/project-management#496, point 2).
    Any other problem stays new, and so does a change made after the call. What
    the component was read as stays old too, as an undo gives it back, until a
    write.

    A component that no problem read is about, and that is either in a document
    with no media length or was read with one, has nothing to keep, and is
    found so without checking anything: a document made in memory has nothing
    read at all. Otherwise the component's timeline is checked as a write
    checks it, with the beat timeline it names as its measure table. Raises
    `KeyError` for a component the document doesn't have, and, as `write` does,
    `UnreadableFile` for a document the reader would refuse and `ValueError`
    for a value in that timeline that JSON can't hold.

    It reads the document's `read_problems` and sets them, as a write does: the
    two are not to run at once on one document, from two threads."""
    timeline_id = next(
        (
            key
            for key, timeline in document.timelines.items()
            if component_id in timeline.components
        ),
        None,
    )
    if timeline_id is None:
        raise KeyError(component_id)
    held = pointer_to(pointer_to("/timelines", timeline_id), "components")
    place = pointer_to(held, component_id)
    was = _Read(document.read_problems)
    unmeasured = document.read_unmeasured
    if place not in was.places and (
        document.media_length is None or place not in unmeasured
    ):
        return  # nothing read about it
    written = _as_written(document, timeline_id)
    kept = []
    for problem in find_problems(written):
        between = _between(problem)
        if problem.place == place:
            if between:
                came_with = all(
                    was.at_odds(problem, at, state) for at, state in between
                )
            else:
                came_with = (place, problem.code) in was.codes or (
                    problem.code == rules.PAST_MEDIA_END
                    and _was_past_the_end(written, timeline_id, unmeasured.get(place))
                )
        elif problem.joined is None and any(at == place for at, _ in between):
            # Named on another, which hasn't changed.
            came_with = was.has(problem) and all(
                was.were_at_odds(problem, at)
                if at == place
                else was.at_odds(problem, at, state)
                for at, state in between
            )
        else:
            continue  # not one of its problems
        if not came_with:
            continue  # new, or new with another
        if was.has(problem) and not was.changed(problem):
            continue  # old as it is
        if (
            problem.code == rules.PAST_MEDIA_END
            and unmeasured.get(problem.place) == problem.state
        ):
            continue  # old as it is: its time wasn't compared with any
        kept.append(dataclasses.replace(problem, kept=True))
    if kept:
        document.read_problems = [*document.read_problems, *kept]


def _as_written(document: Document, timeline_id: str) -> Document:
    """What a write of `document` checks of the timeline `timeline_id`: the
    bytes it would write, read back, so that a float given for an integer is
    checked as the integer it is written as (FR-051a). Only that timeline, with
    the beat timeline it names as its measure table, which is all the reader
    needs of the others for it, unless the reader refuses them so: then the
    whole document."""
    # Imported here: they read this module.
    from tilia_core.tla.reader import written_document
    from tilia_core.tla.writer import checked_bytes

    timeline = document.timelines[timeline_id]
    table = timeline.attrs.get("measure_table")
    part = dataclasses.replace(
        document,
        timelines={
            key: value
            for key, value in document.timelines.items()
            if key in (timeline_id, table)
        },
    )
    try:
        return written_document(checked_bytes(part))
    except UnreadableFile:
        return written_document(checked_bytes(document))


def _was_past_the_end(written: Document, timeline_id: str, state: str | None) -> bool:
    """Whether a component of `written`'s timeline `timeline_id`, as `state`
    holds it, as it was read with no media length, has a time past the end of
    the one `written` has: it then came with a time past the end. False with no
    `state`, for a component read with a length."""
    if state is None:
        return False
    timeline = written.timelines[timeline_id]
    as_read = json.loads(state)
    as_read.pop("metadata", None)
    kind = component_kind_from_file(as_read.pop("kind"))
    component = Component(id="", kind=kind, attrs=as_read)
    checked = rules.check_timeline(
        _length(written),
        [component],
        rows=timeline.attrs.get("rows") or [],
        page_count=math.inf,
        every_rule=True,
    ).get("")
    return checked is not None and any(
        outcome.code == rules.PAST_MEDIA_END
        for outcome in (checked.outcome, *checked.also)
    )


class _Read:
    """The problems a document was read with, as a write compares them: each by
    its place, code and state, and each place by the state it was read in, its
    own or as one of the others a problem is between. A problem
    `keep_read_problems` kept is old too, as the component is now, and the
    others it is between are old for it alone: a component kept for one problem
    is still changed for every other."""

    def __init__(self, read: list[ReadProblem]) -> None:
        self.problems: set[tuple[str, str, str]] = set()
        self.codes: set[tuple[str, str]] = set()
        self.places: set[str] = set()
        self.states: dict[str, str] = {}
        self.kept: dict[tuple[str, str], set[tuple[str, str]]] = {}
        # By a problem's place and code, read or kept: the states of each of
        # the others it is between.
        self.others: dict[tuple[str, str], dict[str, set[str]]] = {}
        for problem in read:
            key = (problem.place, problem.code)
            between = _between(problem)
            self.problems.add((problem.place, problem.code, problem.state))
            self.codes.add(key)
            self.places.add(problem.place)
            others = self.others.setdefault(key, {})
            for at, state in between:
                self.places.add(at)
                others.setdefault(at, set()).add(state)
            if problem.kept:
                self.kept.setdefault(key, set()).update(between)
            else:
                self.states[problem.place] = problem.state
                self.states.update(between)

    def has(self, problem: ReadProblem) -> bool:
        """Whether `problem` was read, or kept, on what it is about as it is."""
        return (problem.place, problem.code, problem.state) in self.problems

    def changed(self, problem: ReadProblem) -> tuple[tuple[str, str], ...]:
        """The others `problem` is between that aren't as read, nor as kept
        with it."""
        kept = self.kept.get((problem.place, problem.code), ())
        return tuple(
            other
            for other in _between(problem)
            if self.states.get(other[0]) != other[1] and other not in kept
        )

    def at_odds(self, problem: ReadProblem, other: str, state: str) -> bool:
        """Whether `problem`'s place and `other`, as `state` holds it, were read
        or kept at odds by its rule: `other` among those a problem of its code
        there was between, or, for a rule between two components, which names
        the pair on either, `problem`'s place among those of `other`'s own
        problem of that code, in that state. A join is its range's alone."""
        if state in self.others.get((problem.place, problem.code), {}).get(other, ()):
            return True
        return (
            problem.joined is None
            and (other, problem.code, state) in self.problems
            and problem.place in self.others.get((other, problem.code), {})
        )

    def were_at_odds(self, problem: ReadProblem, other: str) -> bool:
        """Whether `problem`'s place and `other` were read or kept at odds by
        its rule, a rule between two components, on either, as `other` was then,
        whatever it is now."""
        return other in self.others.get(
            (problem.place, problem.code), {}
        ) or problem.place in self.others.get((other, problem.code), {})


def _between(problem: ReadProblem) -> tuple[tuple[str, str], ...]:
    """The other components `problem` is between, each as a place and a state: the
    range a join joins, whatever comes next in its row, or those it names. So a
    change to that range makes the join new, and TiLiA checks it with the edit
    (TimeLineAnnotator/project-management#496, point 2)."""
    return problem.others if problem.joined is None else (problem.joined,)


def _beat_pattern_problems(timeline: Timeline, place: str) -> Iterator[ReadProblem]:
    # Imported here: the time map's package reads `tla`.
    from tilia_core.timemap.pattern import parse

    pattern = timeline.attrs.get("beat_pattern")
    if isinstance(pattern, str) and not parse(pattern).is_complete:
        name = f"the timeline {json.dumps(timeline.name, ensure_ascii=False)}"
        shown = json.dumps(pattern, ensure_ascii=False)
        yield ReadProblem(
            code=_BAD_BEAT_PATTERN,
            reason=f"the beat pattern {shown} of {name} isn't a valid pattern",
            place=pointer_to(place, "beat_pattern"),
            state=_state(pattern),
        )


def _row_problems(timeline: Timeline, place: str) -> Iterator[ReadProblem]:
    rows = timeline.attrs.get("rows")
    if not isinstance(rows, list):
        return
    held = pointer_to(place, "rows")
    for index, row in enumerate(rows):
        # Two rows with one id are refused as a broken structure.
        for outcome in (
            rules.range_rows([{**row, "color": None}]),
            rules.color(row.get("color")),
        ):
            if not outcome:
                yield ReadProblem(
                    code=outcome.code,
                    reason=outcome.reason,
                    place=pointer_to(held, row["id"]),
                    pointer=pointer_to(held, index),
                    state=_row_state(row, held, index),
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
    holds = TIMELINE_COMPONENTS.get(timeline.kind, frozenset())
    states: dict[str, str] = {}

    def as_read(component_id: str) -> tuple[str, str]:
        # Its place and state, each state made once: a group at odds names them
        # often.
        at = pointer_to(held, component_id)
        state = states.get(component_id)
        if state is None:
            state = _component_state(components[component_id], at, holds)
            states[component_id] = state
        return at, state

    named: set[tuple[str, str, str]] = set()  # each rule's pairs named so far
    for component_id, checked in found.items():
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
            attrs = components[component_id].attrs
            at, state = as_read(component_id)
            yield ReadProblem(
                code=outcome.code,
                reason=reason,
                place=at,
                state=state,
                others=tuple(as_read(other) for other in kept),
                joined=(
                    as_read(attrs["joined_right"])
                    if outcome.code == rules.BAD_JOIN
                    else None
                ),
                more=len(others) - len(kept),
                warned=components[component_id].kind == "beat" and reason == _NO_TIME,
            )


def _component_state(component: Component, place: str, holds: frozenset[str]) -> str:
    """Everything a component has, as the writer writes it, as a text to compare."""
    # Imported here: the writer reads this module.
    from tilia_core.tla.writer import component_as_written

    return _state(component_as_written(component, place, holds))


def _row_state(row: Mapping[str, Any], held: str, index: int) -> str:
    """Everything a row has, as the writer writes it, as a text to compare."""
    # Imported here: the writer reads this module.
    from tilia_core.tla.writer import row_as_written

    return _state(row_as_written(row, held, index))


# `value` as a text to compare: 1 and 1.0 and True aren't the same.
_state = json.JSONEncoder(sort_keys=True, ensure_ascii=False).encode
