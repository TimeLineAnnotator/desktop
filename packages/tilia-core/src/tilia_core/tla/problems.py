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
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from tilia_core import rules
from tilia_core.tla.errors import printable
from tilia_core.tla.layout import pointer_to
from tilia_core.tla.model import (
    TIMELINE_COMPONENTS,
    Component,
    Document,
    ReadProblem,
    ReadWarning,
    Timeline,
    UnknownKind,
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
    length: float = math.inf
    if not media_length:
        found.append(
            ReadProblem(
                code=media_length.code,
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
    its place decide: what it reads is its reason, and it may read otherwise."""
    codes: dict[str, set[str]] = {}
    states: dict[str, str] = {}
    for problem in read:
        codes.setdefault(problem.place, set()).add(problem.code)
        states[problem.place] = problem.state
        states.update(_between(problem))
    new = []
    for problem in written:
        place = problem.place
        if (
            problem.code == rules.PAST_MEDIA_END
            and read_unmeasured.get(place) == problem.state
        ):
            continue  # its time wasn't compared with any
        if problem.code not in codes.get(place, ()) or states[place] != problem.state:
            new.append(problem)
            continue
        changed = tuple(
            other for other in _between(problem) if states.get(other[0]) != other[1]
        )
        if changed:
            # A refusal names those that are new. A join's others are what comes
            # next in its row, whichever of them it was that changed.
            if problem.joined is None:
                problem = dataclasses.replace(problem, others=changed)
            new.append(problem)
    return new


# The rules a beat's `measure` mark breaks: a problem of one goes where the mark
# goes.
MARK_CODES = frozenset({rules.NEGATIVE_MEASURE_NUMBER})


def states_of(
    document: Document, timeline_id: str, component_ids: Iterable[str]
) -> dict[str, str]:
    """The state of each of `component_ids`, components of the timeline, by
    id, as a problem records it; none when `document` has no problems or
    states it was read with to compare them with, so that `keep_old` has
    nothing to do."""
    if not document.read_problems and not document.read_unmeasured:
        return {}
    timeline = document.timelines[timeline_id]
    held = pointer_to(pointer_to("/timelines", timeline_id), "components")
    holds = TIMELINE_COMPONENTS.get(timeline.kind, frozenset())
    return {
        component_id: _component_state(
            timeline.components[component_id],
            pointer_to(held, component_id),
            holds,
        )
        for component_id in component_ids
        if component_id in timeline.components
    }


def keep_old(
    document: Document,
    timeline_id: str,
    before: Mapping[str, str],
    moved: Mapping[str, str] | None = None,
) -> None:
    """Keep old the problems `document` was read with that an edit of
    `tla.edits` carried, rather than made
    (TimeLineAnnotator/project-management#528, point 4). `before` gives the
    states, by id, of the components of the timeline the edit may change, as
    `states_of` gave them before it; `moved`, a deleted downbeat's id and the
    beat its mark moved to.

    A problem on one of them, or naming one, that was old before the edit (its
    state then the one it was read with) is old with its state now. One of
    `MARK_CODES` on a downbeat whose mark moved is old on the beat it moved
    to. Any other problem is as it was: a change made since, or after, is
    still compared."""
    if not before:
        return
    held = pointer_to(pointer_to("/timelines", timeline_id), "components")
    moved = moved or {}
    was = {pointer_to(held, key): state for key, state in before.items()}
    now = {
        pointer_to(held, key): state
        for key, state in states_of(
            document, timeline_id, [*before, *moved.values()]
        ).items()
    }

    def kept(place: str, state: str) -> str:
        if was.get(place) == state and place in now:
            return now[place]
        return state

    targets = {
        pointer_to(held, old): pointer_to(held, new) for old, new in moved.items()
    }
    problems = []
    for problem in document.read_problems:
        problems.append(
            dataclasses.replace(
                problem,
                state=kept(problem.place, problem.state),
                # A join is between ranges, which these edits don't change.
                others=tuple((other, kept(other, s)) for other, s in problem.others),
            )
        )
        target = targets.get(problem.place)
        if (
            target in now
            and problem.code in MARK_CODES
            and was.get(problem.place) == problem.state
        ):
            problems.append(
                dataclasses.replace(
                    problem, place=target, pointer="", state=now[target], others=()
                )
            )
    document.read_problems = problems
    unmeasured = document.read_unmeasured
    for place, state in list(unmeasured.items()):
        unmeasured[place] = kept(place, state)


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
