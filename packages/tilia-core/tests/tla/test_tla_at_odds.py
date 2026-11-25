"""What a file with many components at odds reads as (FR-053).

The warnings and the problems are what naming every other component of a problem, one
component at a time, gives: the first ten, how many more, and never a pair twice. The
reader finds them as they are asked for, so they are compared here with a reference that
lists every other: as the rules' own functions find them, and as the reader named them.
"""

import collections
import json
import uuid

import pytest

from tilia_core import rules, tla
from tilia_core.tla import problems
from tilia_core.tla.model import ReadProblem

BASE_MS = 1_767_225_600_000
ROWS = [{"id": "abcdef", "name": "Row 1"}, {"id": "ghijkl", "name": "Row 2"}]
NAMED = 10


def make_id(n):
    return str(uuid.UUID(int=(BASE_MS + n) << 80 | 7 << 76 | 0b10 << 62 | n))


TIMELINE = make_id(1)


def a_file(kind, components, length, **timeline):
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": make_id(0),
        "time_unit": "seconds",
        "media": {"path": "", "length": length},
        "metadata": {"title": "At odds", "notes": ""},
        "timelines": {
            TIMELINE: {
                "kind": kind,
                "ordinal": 1,
                "height": 60,
                **timeline,
                "components": {
                    make_id(10 + n): component for n, component in enumerate(components)
                },
            }
        },
        "scores": [],
    }
    return (json.dumps(content, indent=2) + "\n").encode("utf-8")


def beats(count):
    return a_file("Beat", [{"kind": "BEAT", "time": 1.0}] * count, 10.0)


def markers(count):
    return a_file("Marker", [{"kind": "MARKER", "time": 1.0}] * count, 10.0)


def hierarchy(start, end, level=1):
    return {"kind": "HIERARCHY", "start": start, "end": end, "level": level}


def all_crossing(count):
    parts = [hierarchy(n / 100, 30 + n / 100) for n in range(count)]
    return a_file("Hierarchy", parts, 60.0)


def at_one_place(count):
    return a_file("Hierarchy", [hierarchy(0.0, 10.0)] * count, 60.0)


def inside_one(count):
    """Hierarchies that start with the first, and end after it, at one level."""
    parts = [hierarchy(0.0, 1.0), *(hierarchy(0.0, 5.0 + n / 10) for n in range(count))]
    return a_file("Hierarchy", parts, 60.0)


def nested(count):
    """Each inside the last, at a level below it: no rule broken."""
    parts = [hierarchy(n / 100, 60 - n / 100, count - n) for n in range(count)]
    return a_file("Hierarchy", parts, 60.0)


def two_crossing_groups(count):
    """Some that cross, and some at levels above them, which they lie inside."""
    parts = [hierarchy(n / 100, 20 + n / 100) for n in range(count)]
    parts += [hierarchy(30 + n / 100, 50 + n / 100, 1 + n % 3) for n in range(count)]
    parts += [hierarchy(0.0, 59.0, 5)]
    return a_file("Hierarchy", parts, 60.0)


def joined_to_many(count):
    """Ranges that start together, each joined to one of as many that start
    together later, at a time its end isn't."""
    parts = [
        {
            "kind": "RANGE",
            "start": 0.0,
            "end": 1.0,
            "row_id": "abcdef",
            "joined_right": make_id(10 + count + n),
        }
        for n in range(count)
    ]
    parts += [
        {"kind": "RANGE", "start": 1.5, "end": 2.0, "row_id": "abcdef"}
        for _ in range(count)
    ]
    return a_file("Range", parts, 10.0, rows=ROWS)


def one_by_one(timeline, length):
    """What the rules find of each component, checked with every other one, as the
    functions of its kind find it: every rule it breaks, in their order."""
    components = list(timeline.components.values())
    context = rules._Context(page_count=0, rows=timeline.attrs.get("rows") or [])
    found = {}
    for component in components:
        others = [other for other in components if other is not component]
        checks = rules._RULES[component.kind](length, others, component.attrs, context)
        outcomes = []
        for at, check in enumerate(checks):
            outcome = check()
            if outcome is not None and not outcome:
                outcomes.append(outcome)
                if at == 0:
                    break
        found[component.id] = outcomes
    return found


def expected(doc):
    """The problems a file comes with: each rule's, on the first component it is
    found on that isn't the one it was named on already."""
    ((timeline_id, timeline),) = doc.timelines.items()
    held = f"/timelines/{timeline_id}/components"
    states = problems.states_of(doc, timeline_id, timeline.components)

    def as_read(component_id):
        return f"{held}/{component_id}", states[component_id]

    named = set()
    found = []
    for component_id, outcomes in one_by_one(timeline, doc.media_length).items():
        attrs = timeline.components[component_id].attrs
        for outcome in outcomes:
            others = [
                other
                for other in outcome.others
                if (outcome.reason, other, component_id) not in named
            ]
            if outcome.others and not others:
                continue
            kept = others[:NAMED]
            named.update((outcome.reason, component_id, other) for other in kept)
            found.append(
                ReadProblem(
                    code=outcome.code,
                    reason=outcome.reason,
                    place=as_read(component_id)[0],
                    state=as_read(component_id)[1],
                    others=tuple(as_read(other) for other in kept),
                    joined=(
                        as_read(attrs["joined_right"])
                        if outcome.code == rules.BAD_JOIN
                        else None
                    ),
                    more=len(others) - len(kept),
                    about=outcome.about,
                )
            )
    return found


def warning_of(problem, lines):
    """The warning for a problem: what its message says, by hand."""
    place = problem.place
    message = problem.reason
    if problem.others:
        parts = [f"line {lines[other]}, {other}" for other, _ in problem.others]
        if problem.more:
            parts.append(f"and {problem.more} more")
        what = "other component" if len(parts) == 1 else "other components"
        message += f" ({what}: {'; '.join(parts)})"
    _, _, timeline_id, _, component_id = place.split("/")
    return tla.ReadWarning(
        place=place,
        line=lines[place],
        message=message,
        timeline_id=timeline_id,
        component_id=component_id,
        other_ids=tuple(
            (other.split("/")[2], other.split("/")[4]) for other, _ in problem.others
        ),
        more=problem.more,
        reason=problem.reason,
    )


def lines_by_place(data, doc):
    """The line of each component's key."""
    lines = data.decode("utf-8").split("\n")
    return {
        f"/timelines/{timeline_id}/components/{component_id}": next(
            n for n, line in enumerate(lines, 1) if f'"{component_id}":' in line
        )
        for timeline_id, timeline in doc.timelines.items()
        for component_id in timeline.components
    }


SHAPES = [
    beats,
    markers,
    all_crossing,
    at_one_place,
    inside_one,
    nested,
    two_crossing_groups,
    joined_to_many,
]


@pytest.mark.parametrize("few", [0, 32], ids=["none listed", "a few listed"])
@pytest.mark.parametrize("count", [12, 40])
@pytest.mark.parametrize("make", SHAPES, ids=[shape.__name__ for shape in SHAPES])
def test_a_file_reads_with_the_warnings_that_listing_every_other_gives(
    make, count, few, monkeypatch
):
    monkeypatch.setattr(rules, "_FEW_OTHERS", few)
    data = make(count)

    doc = tla.loads(data)

    problems_expected = expected(doc)
    assert doc.read_problems == problems_expected
    lines = lines_by_place(data, doc)
    # In this order, with these texts, places, lines, and ids.
    assert doc.warnings == [warning_of(p, lines) for p in problems_expected]


def test_the_shapes_break_the_rules_that_name_others():
    # So that the test above compares what it says it does.
    codes = {
        (make.__name__, p.code)
        for make in SHAPES
        for p in expected(tla.loads(make(12)))
    }
    assert {code for _, code in codes} == {
        rules.SAME_TIME,
        rules.SAME_PLACE,
        rules.CROSSING,
        rules.BAD_JOIN,
    }
    assert ("nested", rules.CROSSING) not in codes


@pytest.mark.parametrize("make", SHAPES, ids=[shape.__name__ for shape in SHAPES])
def test_a_file_at_odds_is_written_back_with_the_same_problems(make, tmp_path):
    path = tmp_path / "at odds.tla"
    path.write_bytes(make(40))
    doc = tla.read(path)

    tla.write(path, doc)

    again = tla.read(path)
    assert again.read_problems == doc.read_problems == expected(doc)
    assert [(w.place, w.reason, w.other_ids, w.more) for w in again.warnings] == [
        (w.place, w.reason, w.other_ids, w.more) for w in doc.warnings
    ]


AT_ODDS = [beats, all_crossing, at_one_place, inside_one, joined_to_many]
EACH_AT_ODDS = pytest.mark.parametrize(
    "make", AT_ODDS, ids=[shape.__name__ for shape in AT_ODDS]
)


@EACH_AT_ODDS
def test_the_others_of_a_component_are_never_all_listed(make, monkeypatch):
    def listed(outcome):
        raise AssertionError("every other was listed")

    monkeypatch.setattr(rules.Outcome, "others", property(listed))

    doc = tla.loads(make(60))

    assert any(w.more for w in doc.warnings)


@EACH_AT_ODDS
def test_about_as_many_others_are_found_as_are_named(make, monkeypatch):
    found = collections.Counter()
    of = rules._Ids.of

    def counted(self, place):
        found["ids"] += 1
        return of(self, place)

    monkeypatch.setattr(rules._Ids, "of", counted)

    doc = tla.loads(make(400))

    named = sum(len(p.others) for p in doc.read_problems)
    assert named > 0
    # And those that named it already, which are passed over: ten at most name one.
    assert found["ids"] <= 2 * named + 400 * NAMED


@EACH_AT_ODDS
def test_a_components_place_and_state_are_made_once(make, monkeypatch):
    states, places = collections.Counter(), collections.Counter()
    component_state, pointer_to = problems._component_state, problems.pointer_to

    def counted_state(component, place, holds):
        states[place] += 1
        return component_state(component, place, holds)

    def counted_place(held, key):
        places[held, key] += 1
        return pointer_to(held, key)

    monkeypatch.setattr(problems, "_component_state", counted_state)
    monkeypatch.setattr(problems, "pointer_to", counted_place)

    doc = tla.loads(make(40))

    ((_, timeline),) = doc.timelines.items()
    assert set(states.values()) == {1}
    assert all(
        count == 1 for (_, key), count in places.items() if key in timeline.components
    )
    assert len(states) <= len(timeline.components)
