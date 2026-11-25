"""What `check_timeline` finds when many components are at odds with each other.

Reading a timeline, it finds the others a component is at odds with as they are asked
for, where they are many, rather than list them for each component. What it gives is
what the rules' own functions give, each component checked with every other one.
"""

import collections
import copy
import math
import pickle
import random
import sys

import pytest

from tilia_core import rules, tla

MEDIA = 60.0
PAGES = 3
ROWS = [{"id": "Ab12Cd", "name": "Strings"}, {"id": "Ef34Gh", "name": "Winds"}]

# So that the few ones compared one by one are none, few or many of a timeline's.
FEW = pytest.mark.parametrize("few", [0, 1, 4, 32])


def component(kind, n, **attrs):
    return tla.Component(id=f"{kind}{n}", kind=kind, attrs=attrs)


def hierarchy(n, start, end, level=1):
    return component("hierarchy", n, start=start, end=end, level=level)


def at_one_time(count, time=1.0, kind="beat"):
    return [component(kind, n, time=time) for n in range(count)]


def all_crossing(count):
    return [hierarchy(n, n / count, 30 + n / count) for n in range(count)]


def each_inside_the_last(count):
    return [
        hierarchy(n, n / count, 60 - n / count, level=count - n) for n in range(count)
    ]


def joined_to_many(count):
    """Ranges that start together and join one of as many that start together
    later, none of which is at the start of the next ones' time."""
    first = [
        component("range", n, start=0.0, end=1.0, row_id="Ab12Cd", joined_right="x")
        for n in range(count)
    ]
    then = [
        component("range", n, start=1.0, end=2.0, row_id="Ab12Cd")
        for n in range(count, 2 * count)
    ]
    return first + then


# Hierarchies whose boundaries make the tolerance matter: values that are close, that
# are close to a close one, ulp neighbours, and numbers that a float can't hold.
TIMES = [
    0,
    0.0,
    1,
    1.0,
    2.5,
    5.0,
    60.0,
    -1.0,
    2**53,
    2**53 + 1,
    10**400,
    -(10**400),
]


def near(rng):
    base = rng.choice([0.0, 1.0, 60.0, 3600.0, 123456.789])
    k = rng.randrange(6)
    return rng.choice(
        [
            base + k * rng.choice([1e-10, 3e-10, 9e-10, 1.1e-9, 5e-9]),
            math.nextafter(base, math.inf) + k * 1e-16,
            base - k * 4e-10,
        ]
    )


def random_hierarchy(rng, n):
    start = rng.choice(TIMES) if rng.random() < 0.5 else near(rng)
    if rng.random() < 0.5 or abs(start) > 1e300:
        end = rng.choice(TIMES) if rng.random() < 0.3 else near(rng)
    else:
        end = start + rng.choice([0, 1e-10, 1e-9, 2e-9, 0.5, 1, 1.0, 3, -1])
    level = rng.choice([1, 1, 2, 2, 3, 1.0, 1.5, 0, -1, 10**30, True, None, "x"])
    return hierarchy(n, start, end, level)


def random_point(rng, kind, n):
    time = rng.choice([0.0, 0, 1.0, 1, 2.0, 60.5, True, None, "x", 10**400, math.nan])
    return component(kind, n, time=time)


def random_range(rng, n, count):
    start = rng.choice([0.0, 0, 0, 1.0, 2.0])
    attrs = {
        "start": start,
        "end": rng.choice([start + 1, start + 1, start + 2]),
        "row_id": rng.choice(["Ab12Cd", "Ab12Cd", "Ef34Gh", None, ["x"], 3]),
    }
    if rng.random() < 0.8:
        attrs["joined_right"] = rng.choice(
            [f"range{rng.randrange(count)}", "nope", 5, ["l"], None]
        )
    return component("range", n, **attrs)


def random_timeline(kind, seed):
    rng = random.Random(f"{kind} {seed}")
    count = rng.choice([2, 10, 40])
    if kind == "hierarchy":
        return [random_hierarchy(rng, n) for n in range(count)]
    if kind == "range":
        return [random_range(rng, n, count) for n in range(count)]
    return [random_point(rng, kind, n) for n in range(count)]


def by_the_functions(components, skip_broken):
    """What the kinds' functions give, each checked with every other one, or, as an
    import, with the earlier ones they kept."""
    found, kept = {}, []
    for c in components:
        others = list(kept) if skip_broken else [o for o in components if o is not c]
        if c.kind == "range":
            outcome = rules.range_(MEDIA, others, c.attrs, rows=ROWS)
        else:
            outcome = getattr(rules, c.kind)(MEDIA, others, c.attrs)
        found[c.id] = outcome
        if outcome:
            kept.append(c)
    return found


def at_once(components, **kwargs):
    return rules.check_timeline(
        MEDIA, components, rows=ROWS, page_count=PAGES, **kwargs
    )


def told(outcome):
    """All that an outcome says."""
    return (*outcome, outcome.others, outcome.code, outcome.about)


class TestCrossings:
    @pytest.mark.parametrize("seed", range(120))
    def test_they_are_those_cross_finds(self, seed):
        rng = random.Random(seed)
        components = [random_hierarchy(rng, n) for n in range(rng.choice([2, 8, 40]))]
        crossings = rules._Crossings(components)

        for place, c in enumerate(components):
            start, end, level = (c.attrs[name] for name in ("start", "end", "level"))
            if not (
                rules._is_number(start)
                and rules._is_number(end)
                and rules._is_comparable(level)
            ):
                continue
            crossed = crossings.crossed_by(place)
            assert [
                other
                for other in range(len(components))
                if other in crossings.bits and crossed >> crossings.bits[other] & 1
            ] == [
                other
                for other, o in enumerate(components)
                if other != place and rules._cross(start, end, level, o.attrs)
            ]

    @pytest.mark.parametrize("seed", range(20))
    def test_those_with_a_rank_below_one_are_told_at_any_size(self, seed):
        rng = random.Random(seed)
        ranks = [rng.randrange(40) for _ in range(rng.choice([1, 7, 8, 9, 100]))]
        below = rules._Below(ranks)

        for rank in range(42):
            assert below.below(rank) == sum(
                1 << item for item, at in enumerate(ranks) if at < rank
            )


class TestOthers:
    @FEW
    @pytest.mark.parametrize("skip_broken", [False, True], ids=["read", "imported"])
    @pytest.mark.parametrize("kind", ["marker", "beat", "hierarchy", "range"])
    def test_they_are_what_the_functions_find_on_random_timelines(
        self, kind, skip_broken, few, monkeypatch
    ):
        monkeypatch.setattr(rules, "_FEW_OTHERS", few)
        for seed in range(40):
            components = random_timeline(kind, seed)

            found = at_once(components, skip_broken=skip_broken)

            assert {id_: told(c.outcome) for id_, c in found.items()} == {
                id_: told(outcome)
                for id_, outcome in by_the_functions(components, skip_broken).items()
            }, seed

    @FEW
    @pytest.mark.parametrize("kind", ["marker", "hierarchy", "range"])
    def test_every_rule_names_the_same_others(self, kind, few, monkeypatch):
        everything = [
            at_once(random_timeline(kind, s), every_rule=True) for s in range(30)
        ]
        monkeypatch.setattr(rules, "_FEW_OTHERS", few)

        for seed, expected in enumerate(everything):
            found = at_once(random_timeline(kind, seed), every_rule=True)

            assert {
                id_: [told(outcome) for outcome in (c.outcome, *c.also)]
                for id_, c in found.items()
            } == {
                id_: [told(outcome) for outcome in (c.outcome, *c.also)]
                for id_, c in expected.items()
            }, seed

    @pytest.mark.parametrize(
        "components",
        [
            at_one_time(50),
            at_one_time(50, kind="marker"),
            all_crossing(50),
            [hierarchy(n, 0.0, 10.0) for n in range(50)],
            each_inside_the_last(50),
            joined_to_many(50),
        ],
        ids=[
            "at one time",
            "markers at one time",
            "all crossing",
            "at one place",
            "nested",
            "joined",
        ],
    )
    def test_they_are_what_the_functions_find_past_the_few(self, components):
        found = at_once(components, every_rule=True)

        for id_, outcome in by_the_functions(components, False).items():
            assert told(found[id_].outcome) == told(outcome)

    def test_they_are_listed_in_the_order_given(self):
        beats = at_one_time(100)

        found = at_once(beats, every_rule=True)

        assert [found[b.id].outcome.others for b in beats] == [
            tuple(other.id for other in beats if other is not b) for b in beats
        ]


class TestNaming:
    @FEW
    @pytest.mark.parametrize("kind", ["beat", "hierarchy", "range"])
    def test_it_gives_what_listing_them_gives(self, kind, few, monkeypatch):
        monkeypatch.setattr(rules, "_FEW_OTHERS", few)
        for seed in range(25):
            rng = random.Random(f"naming {kind} {seed}")
            components = random_timeline(kind, seed)
            ids = [c.id for c in components]
            for c in at_once(components, every_rule=True).values():
                for outcome in (c.outcome, *c.also):
                    if outcome.ok:
                        continue
                    limit = rng.choice([0, 1, 3, 10])
                    named = set(rng.sample(ids, rng.randrange(len(ids) + 1)))

                    kept, more, any_others = outcome.naming(limit, named)

                    left = [other for other in outcome.others if other not in named]
                    assert (kept, more) == (left[:limit], max(0, len(left) - limit))
                    assert any_others is (len(outcome.others) > 0)

    @pytest.mark.parametrize(
        "components", [at_one_time(200), all_crossing(200), joined_to_many(200)]
    )
    def test_it_lists_no_more_than_it_gives(self, components):
        found = at_once(components, every_rule=True)

        for c in found.values():
            if c.outcome:
                continue
            kept, more, any_others = c.outcome.naming(10)
            assert len(kept) == 10
            assert any_others
            # Not found: the others are as they are, until they are asked for.
            assert isinstance(c.outcome._others, rules._AtOdds)
            assert len(kept) + more == len(c.outcome.others)
            assert not isinstance(c.outcome._others, rules._AtOdds)

    def test_one_named_by_another_is_counted_out(self):
        beats = at_one_time(60)
        outcome = at_once(beats, every_rule=True)[beats[0].id].outcome

        kept, more, _ = outcome.naming(3, {beats[1].id, beats[2].id, "nope"})

        assert kept == [b.id for b in beats[3:6]]
        assert more == 59 - 2 - 3


class TestOutcomesFoundAsAskedFor:
    @pytest.mark.parametrize("components", [at_one_time(60), all_crossing(60)])
    @pytest.mark.parametrize(
        "duplicate",
        [
            copy.copy,
            copy.deepcopy,
            lambda outcome: pickle.loads(pickle.dumps(outcome)),
        ],
        ids=["copy", "deepcopy", "pickle"],
    )
    def test_they_copy_and_pickle_whole(self, components, duplicate):
        for c in at_once(components, every_rule=True).values():
            copied = duplicate(c.outcome)

            # Found by now, so that none of the timeline goes with them.
            assert isinstance(copied._others, tuple)
            assert told(copied) == told(c.outcome)

    def test_they_are_the_outcomes_the_rules_give_otherwise(self):
        (one, two) = at_once(at_one_time(2), every_rule=True).values()
        many = at_once(at_one_time(60), every_rule=True)

        assert one.outcome == many["beat0"].outcome
        assert (one.outcome.code, one.outcome.ok) == (rules.SAME_TIME, False)
        assert two.outcome.others == ("beat0",)


class TestWhatIsCompared:
    """The comparisons that grow with the square of the components: none when a
    timeline is read."""

    @pytest.mark.parametrize(
        "components", [at_one_time(400), at_one_time(400, kind="marker")]
    )
    def test_no_point_is_given_the_others_at_its_time(self, components, monkeypatch):
        given = []
        same_time = rules._same_time

        def counted(kind, time, others):
            others = list(others)
            given.append(len(others))
            return same_time(kind, time, others)

        monkeypatch.setattr(rules, "_same_time", counted)

        found = at_once(components, every_rule=True)

        assert all(c.outcome.code == rules.SAME_TIME for c in found.values())
        assert max(given) <= rules._FEW_OTHERS + 1

    @pytest.mark.parametrize(
        "components",
        [
            all_crossing(400),
            each_inside_the_last(400),
        ],
    )
    def test_no_hierarchy_is_compared_with_all_that_overlap_it(
        self, components, monkeypatch
    ):
        compared = collections.Counter()
        cross = rules._cross

        def counted(*args):
            compared["times"] += 1
            return cross(*args)

        monkeypatch.setattr(rules, "_cross", counted)

        at_once(components, every_rule=True)

        # A few for each hierarchy, where `every_rule` checks it twice at most.
        assert compared["times"] <= 2 * len(components) * (rules._FEW_OTHERS + 1)

    def test_the_hierarchies_that_cross_are_looked_for_one_by_one_until_they_are_many(
        self, monkeypatch
    ):
        looked = []
        overlapping = rules._Spans.overlapping

        def counted(self, start, end, most=None):
            looked.append(start)
            return overlapping(self, start, end, most)

        monkeypatch.setattr(rules._Spans, "overlapping", counted)

        at_once(all_crossing(400), every_rule=True)

        # The first overlaps more than a few. The others are told without it.
        assert len(looked) == 1

    def test_no_set_of_the_hierarchies_one_crosses_is_kept(self):
        # A set for each of them would take a bit for each pair.
        for c in at_once(all_crossing(3000), every_rule=True).values():
            for held in vars(c.outcome._others).values():
                assert sys.getsizeof(held) < 200

    def test_no_range_is_given_every_range_that_follows(self, monkeypatch):
        given = []
        joined = rules._joined

        def counted(attrs, others, rows):
            others = list(others)
            given.append(len(others))
            return joined(attrs, others, rows)

        monkeypatch.setattr(rules, "_joined", counted)

        found = at_once(joined_to_many(300), every_rule=True)

        # Each joins one that isn't there, so all of them are named...
        firsts = [found[f"range{n}"].outcome for n in range(300)]
        assert {outcome.code for outcome in firsts} == {rules.BAD_JOIN}
        assert {len(outcome.others) for outcome in firsts} == {300}
        # ...and none of them was given all.
        assert max(given) <= rules._FEW_OTHERS + 2
