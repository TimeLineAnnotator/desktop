"""The check at the end of each action: the core's rules, on what the action leaves.

Everything a person does in TiLiA ends in `App.on_record_state`, and each command of
TiLiA's command line in `App.on_edit_done`. There the gate compares the state the
action leaves with the last state it accepted, `accepted`. Each timeline that differs
is checked whole with the core's rules (`rules.check_timeline`), as it was and as it
is, since a change can break a rule of a component it doesn't touch, such as a join
(WP16's `contracts/rules.md`, decision 13). Then (FR-062):

- a component the action changed or added passes when it breaks no rule, or when it
  breaks fewer than it did and none it didn't, so that a component with two problems
  can be fixed one at a time (TimeLineAnnotator/project-management#405, point 2);
- one it didn't change passes unless it breaks a rule it didn't;
- one it deleted passes.

Problems are told apart as WP3's writer tells them, so that the two agree: by the
rule's code, never by its reason, which quotes values
(TimeLineAnnotator/project-management#536, point 4); within a component, by what of it
the rule checks (`Outcome.about`), so that a second problem of a code the component
came with, on another of its attributes, is new
(TimeLineAnnotator/project-management#557); and by the other components a problem is
between, each pair on its own, so that a component no longer at odds with one of its
others breaks one rule fewer, and one that loses one of them, deleted or moved away,
breaks no new one. A problem between a changed component and another the action
changed too is new, and so is a join to a range the action changed, as the writer
would find them (TimeLineAnnotator/project-management#496, point 2).

A component that passes with problems left has the ones it came with: the caller has
the core keep them (`tla.keep_read_problems`), so that its save isn't refused
(TimeLineAnnotator/project-management#436, point 1).

A range timeline's rows are checked the same way as its components. The rules see
each component as the document stores it: a `pre_start` or `post_end` equal to its
`start` or `end` is unset, and a beat that starts a measure has a mark, with its
number where it isn't the one before's plus one.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from tilia.file import tla_bridge
from tilia_core import rules, tla

State = Mapping[str, Any]

# A pre-start or post-end equal to the time it follows is unset in the document.
_FOLLOWS = {"pre_start": "start", "post_end": "end"}
# A row's key among a timeline's parts, apart from its components' ids.
_ROW = "rows/"
# How many timelines, as states give them, the gate keeps what it found in.
_KEPT = 32


@dataclass(frozen=True)
class Problem:
    """A rule a component or a row breaks, told apart as the writer tells them: by
    its code, by what of the component it checks, and by the others it is between.
    Its reason is for reading, and isn't compared."""

    code: str
    about: str
    between: frozenset[str]
    reason: str = field(compare=False)


@dataclass(frozen=True)
class Verdict:
    """What the gate finds in an action: the first reason to refuse it, or None;
    and the components it lets through with problems they came with, by the id of
    their timeline, for the core to keep."""

    reason: str | None = None
    kept: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _Found:
    """One timeline of a state, as the rules see it: each part, a component or a
    row, as it is compared, and what each breaks."""

    parts: Mapping[str, Any]
    problems: Mapping[str, tuple[Problem, ...]]


_NOTHING = _Found({}, {})


class EditGate:
    """The state last accepted, and the check of each action against it."""

    def __init__(self) -> None:
        self.accepted: State | None = None
        # What the rules found in a timeline of a state, by what they depend on:
        # undo and redo come back to states seen before.
        self._found: OrderedDict[tuple[Any, ...], _Found] = OrderedDict()

    def check(
        self,
        current: State,
        *,
        media_length: float,
        page_counts: Mapping[str, float],
    ) -> Verdict:
        """What the action that leaves `current` breaks, since `accepted`.

        `media_length` is the one the document has once it follows `current`, or
        `math.inf` when it is unknown; both states are checked with it, as a write
        would check them. `page_counts` gives a PDF timeline's page count, by its id,
        `math.inf` when the PDF wasn't found. With nothing accepted, there is
        nothing to compare with, and the action passes."""
        if self.accepted is None:
            return Verdict()
        accepted = self.accepted["timelines"]
        refused: str | None = None  # by a component the action changed
        broken: str | None = None  # by one it didn't change
        kept: list[tuple[str, str]] = []
        for timeline_id, timeline in current["timelines"].items():
            was = accepted.get(timeline_id)
            if was is not None and not _differs(was, timeline):
                continue
            page_count = page_counts.get(timeline_id, math.inf)
            after = self._find(timeline_id, timeline, media_length, page_count)
            if not after.parts:
                continue
            before = (
                _NOTHING
                if was is None
                else self._find(timeline_id, was, media_length, page_count)
            )
            changed = {
                key
                for key, part in after.parts.items()
                if before.parts.get(key) != part
            }
            for key, problems in after.problems.items():
                was_problems = before.problems.get(key, ())
                if key in changed:
                    new, fixed = _changed(problems, was_problems, changed)
                    if new or not fixed or key.startswith(_ROW):
                        # Something new, or nothing fixed: the core keeps a problem
                        # only for a component.
                        refused = refused or (new or problems)[0].reason
                    else:
                        kept.append((timeline_id, key))
                else:
                    new = _unchanged(problems, was_problems, changed)
                    if new:
                        broken = broken or new[0].reason
        reason = refused or broken
        if reason is not None:
            return Verdict(reason)
        return Verdict(kept=tuple(kept))

    def _find(
        self, timeline_id: str, timeline: State, media_length: float, page_count: float
    ) -> _Found:
        components = timeline.get("components", {})
        key = (
            timeline_id,
            timeline.get("hash"),
            timeline.get("components_hash"),
            tuple(components),
            media_length,
            page_count,
        )
        found = self._found.get(key)
        if found is None:
            found = _find(timeline, media_length, page_count)
            self._found[key] = found
            while len(self._found) > _KEPT:
                self._found.popitem(last=False)
        else:
            self._found.move_to_end(key)
        return found


def _changed(
    problems: tuple[Problem, ...], was: tuple[Problem, ...], changed: set[str]
) -> tuple[list[Problem], bool]:
    """What a component the action changed breaks that it didn't, and whether it
    breaks fewer rules than it did. A pair it wasn't at odds with is new, and so is
    one with another the action changed."""
    if set(problems) == set(was):
        # The same: nothing fixed, and new only with another the action changed.
        return [p for p in problems if p.between & changed], False
    pairs, was_pairs = _pairs(problems), _pairs(was)
    new = [
        problem
        for (code, about, other), problem in pairs.items()
        if (code, about, other) not in was_pairs or other in changed
    ]
    return new, len(pairs) < len(was_pairs)


def _unchanged(
    problems: tuple[Problem, ...], was: tuple[Problem, ...], changed: set[str]
) -> list[Problem]:
    """What a component the action didn't change breaks that it didn't: a pair it
    wasn't at odds with, or a join to a range the action changed."""
    if set(problems) == set(was):
        return [p for p in problems if p.code == rules.BAD_JOIN and p.between & changed]
    was_pairs = _pairs(was)
    return [
        problem
        for (code, about, other), problem in _pairs(problems).items()
        if (code, about, other) not in was_pairs
        or (code == rules.BAD_JOIN and other in changed)
    ]


def _pairs(problems: Iterable[Problem]) -> dict[tuple[str, str, str], Problem]:
    """Each problem by its code, what it is about, and each of the others it is
    between, one at a time; "" for a problem of the component alone."""
    pairs: dict[tuple[str, str, str], Problem] = {}
    for problem in problems:
        for other in problem.between or ("",):
            pairs.setdefault((problem.code, problem.about, other), problem)
    return pairs


def changed_components(accepted: State, current: State) -> list[str]:
    """The ids of the components of `current` added or changed since `accepted`,
    of the kinds the rules cover."""
    changed = []
    for timeline_id, timeline in current["timelines"].items():
        was = accepted["timelines"].get(timeline_id, {}).get("components", {})
        for component_id, component in timeline.get("components", {}).items():
            if tla_bridge.COMPONENT_KINDS.get(component.get("kind")) not in rules.KINDS:
                continue
            before = was.get(component_id)
            if before is None or before.get("hash") != component.get("hash"):
                changed.append(component_id)
    return changed


def _differs(was: State, timeline: State) -> bool:
    """Whether a timeline differs between two states: its attributes, or its
    components, whose digest doesn't know their ids."""
    return (
        was.get("hash") != timeline.get("hash")
        or was.get("components_hash") != timeline.get("components_hash")
        or was.get("components", {}).keys() != timeline.get("components", {}).keys()
    )


def _find(timeline: State, media_length: float, page_count: float) -> _Found:
    """What the rules find in a timeline of a state."""
    components = {
        component_id: component
        for component_id, state in timeline.get("components", {}).items()
        if (component := _for_rules(component_id, state)).kind in rules.KINDS
    }
    if timeline.get("kind") == "Beat":
        _number_measures(timeline, components)
    rows = timeline.get("rows")
    parts: dict[str, Any] = {
        component_id: component.attrs for component_id, component in components.items()
    }
    problems: dict[str, tuple[Problem, ...]] = {}
    if components:
        checked = rules.check_timeline(
            media_length,
            components.values(),
            rows=rows,
            page_count=page_count,
            every_rule=True,
        )
        for component_id, result in checked.items():
            attrs = components[component_id].attrs
            found = _problems(
                (result.outcome, *result.also, result.color), attrs.get("joined_right")
            )
            if found:
                problems[component_id] = found
    for row in rows or ():
        key = f"{_ROW}{row.get('id')}"
        parts[key] = dict(row)
        # As WP3's reader checks a row: its id and name, then its color.
        found = _problems(
            (rules.range_rows([{**row, "color": None}]), rules.color(row.get("color")))
        )
        if found:
            problems[key] = found
    return _Found(parts, problems)


def _for_rules(component_id: str, state: State) -> tla.Component:
    """A component of the state as the document stores it, for the rules."""
    component = tla_bridge.component_for_rules(component_id, state["kind"], state)
    for attr, followed in _FOLLOWS.items():
        if attr in component.attrs and component.attrs[attr] == component.attrs.get(
            followed
        ):
            del component.attrs[attr]
    return component


def _number_measures(timeline: State, beats: dict[str, tla.Component]) -> None:
    """Gives each beat that starts a measure a mark, as the document stores it: with
    the number TiLiA shows for it where that isn't the one before's plus one, as
    `tla_bridge` writes it. So the rules check the numbers stored, and a number that
    only follows another that changed doesn't change its beat."""
    states = {beat_id: timeline["components"][beat_id] for beat_id in beats}
    # The bridge's order and measures, so that the numbers are those it writes.
    order = tla_bridge._beats_in_order(states)
    counts = timeline.get("beats_in_measure") or [len(order)]
    numbers = timeline.get("measure_numbers") or []
    following = 1
    starts = sorted(
        tla_bridge._measure_starts(order, counts).items(), key=lambda start: start[1]
    )
    for beat_id, index in starts:
        number = numbers[index] if index < len(numbers) else following
        beats[beat_id].attrs["measure"] = (
            {} if number == following else {"number": number}
        )
        following = number + 1


def _problems(
    outcomes: Iterable[rules.Outcome], joined: Any = None
) -> tuple[Problem, ...]:
    """The rules `outcomes` say are broken, each once. A join is between its range
    and the one it joins, as the writer has it; another problem, between its
    component and the others its outcome names."""
    found: dict[Problem, None] = {}
    for outcome in outcomes:
        if outcome.ok:
            continue
        if outcome.code == rules.BAD_JOIN:
            between = frozenset({joined}) if isinstance(joined, str) else frozenset()
        else:
            between = frozenset(outcome.others)
        found.setdefault(Problem(outcome.code, outcome.about, between, outcome.reason))
    return tuple(found)
