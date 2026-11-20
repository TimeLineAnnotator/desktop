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
`unmeasured`, made from what was read when a write first needs them
(`unmeasured_later`). A known length that puts a time past it for the first time
is a new problem, since what the file came with kept to its length: TiLiA leaves
nothing past the end when it scales or crops
(TimeLineAnnotator/project-management#496, point 1). What a first length puts
past the end, which a write keeps as old, `past_a_first_length` lists, so that
it can be shown (TimeLineAnnotator/project-management#614, option c).

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
than one state that is old. With no media length read, a time it keeps past the
end is judged at the length written, not the one at the call, so that no
detour through another length keeps what a write at that length refuses
(TimeLineAnnotator/project-management#614, option c).
"""

from __future__ import annotations

import dataclasses
import json
import math
import threading
from collections.abc import Callable, Container, Iterable, Iterator, Mapping
from typing import Any, cast

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
    as_read: Callable[[], Document],
    long_integer: bool,
    where: Callable[[str], str] | None = None,
) -> None:
    """Give `document`, just read, what it breaks: its `read_problems`, and a
    warning for each, after those it has. `source` is what it was read from,
    for lines. `as_read` makes the same document again from `source`, and
    `long_integer` is whether `source` holds an integer a Python may not read
    or write, as `unmeasured_later` needs them. `where` takes a place in the
    document to the place to name, in what it was read from."""
    document.read_problems = find_problems(document)
    document.read_unmeasured = unmeasured_later(document, as_read, lambda: long_integer)
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


def unmeasured_later(
    document: Document,
    as_read: Callable[[], Document],
    long_integer: Callable[[], bool],
) -> Mapping[str, str]:
    """`unmeasured(document)`, for `document` just made from bytes, put off until
    it is looked at: most reads aren't written, and a write looks at it only for a
    time past the end. It is then made from `as_read()`, which makes the document
    again from those bytes, never from `document`, which may have changed by then.

    From bytes with an integer that a Python may not read or write, it is made
    now: what it raises for one is raised while reading, and a limit lowered since
    can't stop it being made. `long_integer()` says whether they hold one
    (`reader.has_long_integer`). It is asked only when there are states to make,
    so that a write with a media length, or in quarters, doesn't search what it
    wrote."""
    if document.media_length is not None or document.time_unit != "seconds":
        return {}
    if long_integer():
        return unmeasured(document)
    return _Unmeasured(as_read)


class _Unmeasured(Mapping[str, str]):
    """The states `unmeasured` gives for the document `as_read` makes, made the
    first time they are looked at, once, whichever thread looks first."""

    def __init__(self, as_read: Callable[[], Document]) -> None:
        self._as_read: Callable[[], Document] | None = as_read
        self._states: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _made(self) -> dict[str, str]:
        with self._lock:
            if self._states is None:
                assert self._as_read is not None  # dropped once they are made
                self._states = unmeasured(self._as_read())
                self._as_read = None  # it holds the file's bytes
            return self._states

    def __getitem__(self, place: str) -> str:
        return self._made()[place]

    def __iter__(self) -> Iterator[str]:
        return iter(self._made())

    def __len__(self) -> int:
        return len(self._made())

    def __repr__(self) -> str:
        return repr(self._made())

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, str]:
        # As `dataclasses.asdict` copies it: what it holds, as a dict.
        return dict(self._made())

    def __reduce__(self) -> tuple[Any, ...]:
        # A lock doesn't pickle or copy: the states once made, else a new one.
        with self._lock:
            if self._states is not None:
                return (dict, (self._states,))
            return (_Unmeasured, (self._as_read,))


def new_problems(
    written: list[ReadProblem],
    read: list[ReadProblem],
    read_unmeasured: Mapping[str, str],
    unmeasured_edits: Mapping[str, Iterable[tuple[str, str]]],
    document: Document,
) -> list[ReadProblem]:
    """Those of `written`, the problems of `document`, what a write would
    write, that aren't among `read`, the problems a document was read with,
    whose `read_unmeasured` were its components with no media length, and
    `unmeasured_edits` the changes an edit kept them through (`keep_old`).

    One on what has changed since, or for a rule it didn't break, is new. One
    between components, on what hasn't changed, is new for the others that have
    changed or been added, and is given with those others alone. Its code and
    its place decide: what it reads is its reason, and it may read otherwise.
    What an edit kept old (`keep_old`, `keep_read_problems`) is among `read`,
    beside what was read, which an undo gives back. A time past the end on a
    component read with no media length is old as `_uncompared_past_the_end`
    says, at the length `document` has."""
    was = _Read(read)
    new = []
    for problem in written:
        uncompared = _uncompared_past_the_end(
            problem, document, read_unmeasured, unmeasured_edits, was.kept_past
        )
        if uncompared is not None:
            if not uncompared:
                new.append(problem)
            continue
        if not was.has(problem):
            new.append(problem)
            continue
        changed = was.changed(problem)
        if changed:
            # A refusal names those that are new. They are among those it
            # names, so none is left to count beyond them: one that changed
            # past them has a problem of its own, which names this one. A join's
            # others are what comes next in its row, whichever of them it was
            # that changed.
            if problem.joined is None:
                problem = dataclasses.replace(problem, others=changed, more=0)
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
    nothing to do. Those states aren't made for it."""
    if not document.read_problems and not _has_unmeasured(document):
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
    `states_of` gave them before it; `moved`, by a downbeat's id, the beat its
    mark's problems go to: where a deleted downbeat's mark moved, or the beat
    a `restart` made state the number it reads from that downbeat's.

    A problem on one of them, or naming one, that was old before the edit (its
    state then one it was read with, or one an edit kept since) is old with its
    state now too. One of `MARK_CODES` on one of `moved` is old on the beat its
    mark moved to, or that states the number. Any other problem is as it was: a
    change made since, or after, is still compared. What was old before the
    edit stays old, as an undo gives it back, until a write. For a document
    read with no media length, each change of a state is kept in
    `unmeasured_edits`, without making the states read (`unmeasured_later`): a
    time is uncompared in a state such changes reach from the one read
    (`_uncompared`), the one read among them.

    It reads the document's `read_problems` and `unmeasured_edits` and sets
    them, as a write does: the two are not to run at once on one document,
    from two threads."""
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

    def as_now(place: str, state: str) -> str:
        if was.get(place) == state and place in now:
            return now[place]
        return state

    targets = {
        pointer_to(held, old): pointer_to(held, new) for old, new in moved.items()
    }
    have = set(document.read_problems)
    kept = []

    def keep(problem: ReadProblem) -> None:
        if problem not in have:
            have.add(problem)
            kept.append(problem)

    for problem in document.read_problems:
        again = dataclasses.replace(
            problem,
            state=as_now(problem.place, problem.state),
            # A join is between ranges, which these edits don't change.
            others=tuple((other, as_now(other, s)) for other, s in problem.others),
            kept=True,
            # A beat is past the end by its time alone.
            past_at_kept=(
                frozenset({"time"})
                if problem.code == rules.PAST_MEDIA_END
                else problem.past_at_kept
            ),
        )
        if again.state != problem.state or again.others != problem.others:
            keep(again)
        target = targets.get(problem.place)
        if (
            target in now
            and problem.code in MARK_CODES
            and was.get(problem.place) == problem.state
        ):
            keep(
                dataclasses.replace(
                    problem,
                    place=target,
                    pointer="",
                    state=now[target],
                    others=(),
                    kept=True,
                )
            )
    document.read_problems = [*document.read_problems, *kept]
    if _has_unmeasured(document):
        # Replaced, never changed: a copy of the document may share it.
        edited = dict(document.unmeasured_edits)
        for place, state in was.items():
            if now.get(place, state) != state:
                edited[place] = edited.get(place, frozenset()) | {(state, now[place])}
        document.unmeasured_edits = edited


def _has_unmeasured(document: Document) -> bool:
    """Whether `document` has states it was read with no media length, made or
    to be made, without making them."""
    return isinstance(document.read_unmeasured, _Unmeasured) or bool(
        document.read_unmeasured
    )


def _uncompared_past_the_end(
    problem: ReadProblem,
    document: Document,
    read_unmeasured: Mapping[str, str],
    unmeasured_edits: Mapping[str, Iterable[tuple[str, str]]],
    kept: Container[tuple[str, str]],
) -> bool | None:
    """For a time past the end of `document`'s media length, on a component
    read with no media length, or last written with none: whether it is old,
    never having been compared with a length. None for any other problem, and
    for one on a component in a state neither below gives, which is compared
    as every other is.

    In a state it was read in, or that an edit of `tla.edits` kept from one
    (`_uncompared`), it is old, by whichever of its times
    (TimeLineAnnotator/project-management#496, point 1, option B). In a state
    `keep_read_problems` kept a time of it past the end in (`kept`, by place
    and state), it is judged at the length `document` has, the one written,
    not the one the call was made at: old only while the component as it was
    read is past that length by the same rule
    (TimeLineAnnotator/project-management#614, option c). So shortening the
    length, editing and calling, then lengthening it again, leaves nothing a
    write at the longer one wouldn't refuse."""
    if problem.code != rules.PAST_MEDIA_END:
        return None
    states = _uncompared(problem.place, read_unmeasured, unmeasured_edits)
    if not states:
        return None  # read with a length, or added since
    if problem.state in states:
        return True
    if (problem.place, problem.state) not in kept:
        return None
    timeline_id, _ = ids_at(problem.place)
    assert timeline_id is not None  # a component's place
    return any(
        _was_past_the_end(document, timeline_id, state, problem.about)
        for state in states
    )


def _uncompared(
    place: str,
    read_unmeasured: Mapping[str, str],
    unmeasured_edits: Mapping[str, Iterable[tuple[str, str]]],
) -> set[str]:
    """The states of the component at `place` whose times weren't compared with
    a media length: the one it was read in, with none, and each an edit kept
    from one of those (`keep_old`); none for one read with a length."""
    read = read_unmeasured.get(place)
    if read is None:
        return set()
    states = {read}
    changes = list(unmeasured_edits.get(place, ()))
    grown = True
    while grown:
        grown = False
        for before, after in changes:
            if before in states and after not in states:
                states.add(after)
                grown = True
    return states


def warnings_of(
    problems: list[ReadProblem],
    source: str | bytes,
    where: Callable[[str], str] | None = None,
) -> list[ReadWarning]:
    """A warning for each of `problems`: its place and line in `source`, its
    reason, and the other components it is about, each named by its place, so
    that an old file's are in its own terms. `where` is `keep_problems`'. The
    warning's ids, its own and those of the others it names, are the
    document's, an old file's after its migration."""
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
        reason = printable(problem.reason)
        message = reason
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
            ReadWarning(
                place,
                lines[place],
                message,
                *ids_at(problem.place),
                # Each other is a component, which `ids_at` gives both ids of.
                other_ids=tuple(
                    cast(tuple[str, str], ids_at(other)) for other, _ in problem.others
                ),
                more=problem.more,
                reason=reason,
            )
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

    Problems are told apart by their rule's code; within one component, by
    what of it the rule checks too (`rules.Outcome.about`, `ReadProblem.about`);
    and between components, by the others they are between. TiLiA's check
    before an edit (WP6, TimeLineAnnotator/project-management#459) tells them
    apart the same way, so that it never allows an edit whose save is refused.

    A problem of the component alone is kept when the document was read with
    one of its code, about the same, on the component: another of that code
    that the edit adds elsewhere on it, such as a negative pre_start beside the
    negative start it was read with, is new
    (TimeLineAnnotator/project-management#557). In a document read with no
    media length, whose times weren't compared with any, a time past the end of
    the length it now has is kept too, and judged when the document is written,
    at the length it then has, not the one it has at the call: it stays old only
    while the component as it was read is past that length by the same rule, and
    so does any other of its times past it, in the state it was kept in
    (TimeLineAnnotator/project-management#614, option c). A call with nothing of
    the component past the end keeps none of its times past the end. A
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
    `KeyError` for a component the document doesn't have. For that timeline,
    with its measure table, it raises what `write` raises, with the same place
    and line: `UnreadableFile` when the reader would refuse it, and `ValueError`
    for a value in it that JSON can't hold. What the reader would refuse in
    another timeline, `write` raises.

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
    if place not in was.places and (
        document.media_length is None
        or not _uncompared(place, document.read_unmeasured, document.unmeasured_edits)
    ):
        return  # nothing read about it
    written = _as_written(document, timeline_id)
    found = find_problems(written)
    # What of it is past the end, kept or not, for a length given since.
    past = frozenset(
        problem.about
        for problem in found
        if problem.place == place and problem.code == rules.PAST_MEDIA_END
    )
    kept = []
    for problem in found:
        between = _between(problem)
        if problem.place == place:
            if between:
                came_with = all(
                    was.at_odds(problem, at, state) for at, state in between
                )
            else:
                # Past the end, read with no length: kept, and judged when the
                # document is written, at the length it then has.
                came_with = (place, problem.code, problem.about) in was.codes or (
                    problem.code == rules.PAST_MEDIA_END
                    and bool(
                        _uncompared(
                            place, document.read_unmeasured, document.unmeasured_edits
                        )
                    )
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
        if problem.code == rules.PAST_MEDIA_END and problem.state in _uncompared(
            problem.place, document.read_unmeasured, document.unmeasured_edits
        ):
            continue  # old as it is: its time wasn't compared with any
        kept.append(
            dataclasses.replace(
                problem,
                kept=True,
                past_at_kept=past
                if problem.code == rules.PAST_MEDIA_END
                else frozenset(),
            )
        )
    if kept:
        document.read_problems = [*document.read_problems, *kept]


def past_a_first_length(document: Document) -> list[ReadWarning]:
    """In `document`, read with no media length, or last written with none, that
    has one now: a warning for each of its components' times past that length
    which a write keeps as old, never having been compared with a length
    (FR-054; TimeLineAnnotator/project-management#496, point 1, option B):
    those of the components as they were read, and those
    `keep_read_problems` kept past the end that the component as it was read is
    past by the same rule (TimeLineAnnotator/project-management#614, option c).
    A time past the end that a write refuses isn't one of them.

    Each warning is the one a file written now would be read with: its rule's
    reason, the component's place and ids, and its line in what a write would
    write, in the order of the file. TiLiA shows them when it gives such a
    file its media's length (WP6's FR-034), and a script gets them so too.

    Nothing for a document read, or last written, with a length, whose times
    were compared with it, or with no length now, or in quarters, which has
    none to compare with (FR-080): found so without checking anything.
    Otherwise the document is checked as a write checks it, and raises what
    `write` raises for it, with the same place and line: `UnreadableFile`
    when the reader would refuse it, and `ValueError` for a value that JSON
    can't hold. It changes nothing in the document, but reads its
    `read_problems` as a write does: the two are not to run at once on one
    document, from two threads, nor is `keep_read_problems`."""
    if not _has_unmeasured(document) or _length(document) == math.inf:
        return []
    # Imported here: they read this module.
    from tilia_core.tla.reader import written_document
    from tilia_core.tla.writer import checked_bytes

    data = checked_bytes(document)
    written = written_document(data)
    kept = _Read(document.read_problems).kept_past
    return warnings_of(
        [
            problem
            for problem in find_problems(written)
            if _uncompared_past_the_end(
                problem,
                written,
                document.read_unmeasured,
                document.unmeasured_edits,
                kept,
            )
        ],
        data,
    )


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


def _was_past_the_end(
    written: Document, timeline_id: str, state: str, about: str
) -> bool:
    """Whether a component of `written`'s timeline `timeline_id`, as `state`
    holds it, as it was read with no media length, has a time past the end of
    the one `written` has, by the rule about `about`: it then came with that
    problem."""
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
        outcome.code == rules.PAST_MEDIA_END and outcome.about == about
        for outcome in (checked.outcome, *checked.also)
    )


class _Read:
    """The problems a document was read with, as a write compares them: each by
    its place, code and state, and each place by the state it was read in, its
    own or as one of the others a problem is between. A problem an edit kept
    (`ReadProblem.kept`: `keep_old`, `keep_read_problems`) is old too, as the
    edit left what it is about, and the others it is between are old for it
    alone: a component kept for one problem is still changed for every other."""

    def __init__(self, read: list[ReadProblem]) -> None:
        self.problems: set[tuple[str, str, str]] = set()
        self.read: set[tuple[str, str, str]] = set()  # not kept
        # Those kept, each told apart within its component by `about` too.
        self.kept_problems: set[tuple[str, str, str, str]] = set()
        # Those kept past the end, by place and state, with what of each was
        # past the end then: old by whichever of their times, as FR-054 has it
        # for a component as it was read, but for what was past it then and
        # wasn't kept.
        self.kept_past: dict[tuple[str, str], set[str]] = {}
        self.codes: set[tuple[str, str, str]] = set()
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
            self.codes.add((*key, problem.about))
            self.places.add(problem.place)
            others = self.others.setdefault(key, {})
            for at, state in between:
                self.places.add(at)
                others.setdefault(at, set()).add(state)
            if problem.kept:
                self.kept.setdefault(key, set()).update(between)
                self.kept_problems.add((*key, problem.about, problem.state))
                if problem.code == rules.PAST_MEDIA_END:
                    at = (problem.place, problem.state)
                    self.kept_past.setdefault(at, set()).update(problem.past_at_kept)
            else:
                self.read.add((problem.place, problem.code, problem.state))
                self.states[problem.place] = problem.state
                self.states.update(between)

    def has(self, problem: ReadProblem) -> bool:
        """Whether `problem` was read, or kept, on what it is about as it is.
        One read is told by its code alone, as FR-054 tells it on a component
        as it was read; one kept, on a component an edit fixed in part, by its
        `about` too, so that another of the same code that the edit added
        elsewhere on it is new (TimeLineAnnotator/project-management#557)."""
        if (problem.place, problem.code, problem.state) in self.read:
            return True
        past = self.kept_past.get((problem.place, problem.state))
        if (
            problem.code == rules.PAST_MEDIA_END
            and past is not None
            and problem.about not in past
        ):
            return True  # put past the end by another length, not by the edit
        key = (problem.place, problem.code, problem.about, problem.state)
        return key in self.kept_problems

    def changed(self, problem: ReadProblem) -> tuple[tuple[str, str], ...]:
        """The others `problem` is between that aren't as read, nor as kept
        with it. A problem old only as one kept, on a component not as it was
        read, is compared pair by pair (`at_odds`): another component read
        with a problem of its own, but never at odds with it, is new to it, as
        it becomes when a deletion brings it among those it names."""
        if (problem.place, problem.code, problem.state) not in self.read:
            return tuple(
                (at, state)
                for at, state in _between(problem)
                if not self.at_odds(problem, at, state)
            )
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
                about=outcome.about,
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
