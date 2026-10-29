"""Time signatures from a source or an edit, as plans of beat-unit writes, and applying them."""

import builtins
import copy
import io
import logging
import os
import random
from fractions import Fraction as F

import pytest

from docs import beat_timeline, document
from tilia_core import tla
from tilia_core.timemap.plan import (
    BarRef,
    Change,
    Plan,
    PlanOutOfDate,
    TimeSignature,
    apply_plan,
    plan_time_signatures,
)
from tilia_core.timemap.table import build_rows, format_time_signature

# What TiLiA puts on the first beat, and WP3's migration on an old file's.
DEFAULT = {"denominator": 4, "units": "1", "assumed": True}


def unit(denominator, units, assumed=False):
    value = {"denominator": denominator, "units": units}
    if assumed:
        value["assumed"] = True
    return value


def piece(taps, marks=None, units=None, measure_source="tapped"):
    """
    A document with one beat timeline, of measures of `taps[i]` beats, a beat
    every second from 0. `marks` gives measures their marks ({measure index:
    mark}; {} by default, so numbered on from the one before), and `units`
    puts units on beats ({(measure index, beat index): unit}). The first beat
    has the default unit unless `units` says otherwise.
    """
    marks = marks or {}
    units = {(0, 0): DEFAULT, **(units or {})}
    beats = []
    for m, count in enumerate(taps):
        for b in range(count):
            beats.append(
                {
                    "time": float(len(beats)),
                    "measure": dict(marks.get(m, {})) if b == 0 else None,
                    # A copy, so that no two tests share a unit's dict.
                    "beat_unit": dict(units[m, b]) if units.get((m, b)) else None,
                }
            )
    timeline = beat_timeline(beats, measure_source=measure_source)
    return document(timeline), timeline


def downbeat(timeline, m):
    return timeline.measures.rows[m].id


def beat(timeline, m, b):
    return timeline.measures.rows[m].beats[b]


def add_beat(timeline, m, time):
    """Adds a beat to the end of measure m, as the table would have it."""
    component = tla.Component(id=tla.new_id(), kind="beat", attrs={"time": time})
    timeline.components[component.id] = component
    timeline.measures.rows[m].beats.append(component.id)


def ts(text):
    return TimeSignature.parse(text)


def bars(*numbers, text):
    """Settings giving the bars `numbers` the time signature `text`."""
    return [(BarRef(number), ts(text)) for number in numbers]


def plan(doc, timeline, settings, source="score", **after):
    """A plan, with `after` if given, else its default."""
    return plan_time_signatures(doc, timeline.id, settings, source=source, **after)


def read(doc, timeline):
    """Each measure's time signature, whether it is assumed, and its source."""
    return [(r.time_signature, r.assumed, r.source) for r in build_rows(doc, timeline)]


def written(p):
    """The components a plan writes to."""
    return {change.component_id for change in p.changes}


def set_bars(p):
    """The downbeats of the measures a plan sets: each records the source."""
    return {c.component_id for c in p.changes if c.key == "measure.source"}


def with_copies():
    """A file written outside TiLiA and the core: three bars of three taps
    reading 3/4 from the timeline's source, "import", which bars 1 and 3
    repeat in their own marks."""
    return piece(
        [3, 3, 3],
        marks={0: {"source": "import"}, 2: {"source": "import"}},
        units={(0, 0): unit(4, "1")},
        measure_source="import",
    )


class TestTimeSignature:
    @pytest.mark.parametrize(
        "beat_values, denominator, parts",
        [
            ([3, 3], 8, (6,)),
            ([2, 2, 3], 8, (2, 2, 3)),
            ([2, 3, 2], 8, (2, 3, 2)),
            ([F(1, 3)] * 4, 4, (F(4, 3),)),
            ([F(1, 2), 1], 8, (F(1, 2), 1)),
            ([F(1, 128)], 4, (F(1, 128),)),
            ([1], 1, (1,)),
            ([1], 128, (1,)),
        ],
    )
    def test_parse_reads_what_format_time_signature_writes(
        self, beat_values, denominator, parts
    ):
        text = format_time_signature([F(v) for v in beat_values], denominator)

        assert TimeSignature.parse(text) == TimeSignature(parts, denominator)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "6",
            "6/",
            "/8",
            "6/0",
            "6/129",
            "0/8",
            "-6/8",
            "6/8.0",
            "1.5/8",
            "3/2/8",
            "(3/2/8",
            "(4/3))/4",
            "()/4",
            "a/8",
            "6/x",
            "6/+8",
            "6/1_0",
            "2++3/8",
        ],
    )
    def test_parse_refuses_anything_else(self, text):
        with pytest.raises(ValueError):
            TimeSignature.parse(text)

    def test_a_grouping_is_read_as_scores_print_it(self):
        assert TimeSignature.parse("2+2+3/8") == TimeSignature((2, 2, 3), 8)

    def test_parts_are_fractions(self):
        assert TimeSignature((6,), 8).parts == (F(6),)
        assert isinstance(TimeSignature((6,), 8).parts[0], F)

    @pytest.mark.parametrize(
        "parts, denominator",
        [
            ((), 8),
            ((0,), 8),
            ((6,), 0),
            ((6,), 129),
            ((0.5,), 8),
            ((True,), 8),
            ("12", 8),
            ((F(10**32),), 8),  # 33 digits: longer than a unit can be
            ((F(1, 129),), 4),  # a fraction's denominator above 128, as in a unit
        ],
    )
    def test_a_time_signature_that_cant_be_written_is_refused(self, parts, denominator):
        with pytest.raises(ValueError):
            TimeSignature(parts, denominator)


class TestTheUnit:
    def test_a_source_gives_an_assumed_two_four_six_eight(self):
        doc, tl = piece([2, 2, 2])
        assert read(doc, tl)[1] == ("2/4", True, "tapped")

        p = plan(doc, tl, bars(2, text="6/8"))

        d = downbeat(tl, 1)
        assert p == Plan(
            changes=[
                Change(tl.id, d, "beat_unit", None, unit(8, "3")),
                Change(tl.id, d, "measure.source", None, "score"),
                # Bar 3 keeps its 2/4, assumed.
                Change(tl.id, downbeat(tl, 2), "beat_unit", None, DEFAULT),
            ],
            unmatched=[],
            ambiguous=[],
        )

    @pytest.mark.parametrize("taps, units", [(2, "3"), (3, "2"), (4, "3/2"), (6, "1")])
    def test_the_numerator_is_divided_over_the_taps_exactly(self, taps, units):
        doc, tl = piece([2, taps, 2])

        p = plan(doc, tl, bars(2, text="6/8"))
        apply_plan(doc, p)

        assert p.changes[0].new == unit(8, units)
        assert read(doc, tl)[1] == ("6/8", False, "score")

    def test_a_grouping_with_a_part_per_tap_gives_the_units(self):
        doc, tl = piece([3, 3, 3])

        p = plan(doc, tl, bars(2, text="2+2+3/8"))
        apply_plan(doc, p)

        assert p.changes[0].new == unit(8, "2+2+3")
        assert read(doc, tl)[1] == ("2+2+3/8", False, "score")

    def test_a_grouping_of_equal_parts_is_written_as_one_unit(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(2, text="3+3/8"))

        assert p.changes[0].new == unit(8, "3")

    def test_a_grouping_without_a_part_per_tap_is_summed_and_divided(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(2, text="2+2+3/8"))
        apply_plan(doc, p)

        assert p.changes[0].new == unit(8, "7/2")
        assert read(doc, tl)[1] == ("7/8", False, "score")

    def test_a_six_eight_passage_tapped_in_two_and_in_three_keeps_both(self):
        doc, tl = piece([2, 3, 2, 3])

        p = plan(doc, tl, bars(1, 2, 3, 4, text="6/8"))
        apply_plan(doc, p)

        units = {c.component_id: c.new for c in p.changes if c.key == "beat_unit"}
        assert units == {
            beat(tl, 0, 0): unit(8, "3"),
            downbeat(tl, 1): unit(8, "2"),
            downbeat(tl, 2): unit(8, "3"),
            downbeat(tl, 3): unit(8, "2"),
        }
        assert read(doc, tl) == [("6/8", False, "score")] * 4

    def test_a_pickup_tapped_like_a_full_bar_comes_out_a_full_bar(self, caplog):
        doc, tl = piece([1] * 5, marks={0: {"number": 0}})

        with caplog.at_level(logging.WARNING):
            apply_plan(doc, plan(doc, tl, bars(0, 1, 2, 3, 4, text="3/4")))

        assert read(doc, tl) == [("3/4", False, "score")] * 5
        assert caplog.records == []

    def test_one_tap_per_bar_three_four_on_bars_1_to_120(self):
        # As BPSD's files are tapped.
        doc, tl = piece([1] * 120)

        p = plan(doc, tl, bars(*range(1, 121), text="3/4"), source="import")

        assert p.changes == [
            Change(tl.id, None, "measure_source", "tapped", "import"),
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "3")),
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("3/4", False, "import")] * 120

    def test_bars_1_to_120_of_more_record_the_source_on_each(self):
        doc, tl = piece([1] * 121)

        p = plan(doc, tl, bars(*range(1, 121), text="3/4"), source="import")

        assert p.changes == [
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "3")),
            *[
                Change(tl.id, downbeat(tl, m), "measure.source", None, "import")
                for m in range(120)
            ],
            Change(tl.id, downbeat(tl, 120), "beat_unit", None, DEFAULT),
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("3/4", False, "import")] * 120 + [
            ("1/4", True, "tapped")
        ]

    def test_a_unit_too_long_to_read_back_is_refused(self):
        doc, tl = piece([2, 3, 2])
        # 32 digits, the longest a part can be, over three taps: 34 characters.
        too_long = TimeSignature((F(10**31 + 1),), 8)

        with pytest.raises(ValueError):
            plan(doc, tl, [(BarRef(2), too_long)])

    def test_the_refusal_shows_the_time_signature_as_it_is_written(self):
        doc, tl = piece([2, 3])

        # 1/128 over two taps: 1/256, a denominator no unit can have.
        with pytest.raises(ValueError) as raised:
            plan(doc, tl, [(BarRef(1), ts("(1/128)/4"))])

        assert str(raised.value).startswith(
            "Measure 1: (1/128)/4 over 2 taps gives units that can't be read back: "
        )

    def test_of_two_settings_for_a_bar_the_later_wins(self):
        doc, tl = piece([3, 3, 3])

        p = plan(doc, tl, [(BarRef(2), ts("6/8")), (BarRef(2), ts("9/8"))])

        assert p.changes[0].new == unit(8, "3")


class TestWhereItGoes:
    def test_on_the_downbeat_of_a_measure_without_a_unit_of_its_own(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(2, text="6/8"))

        assert p.changes[0].component_id == downbeat(tl, 1)

    def test_the_unit_on_the_first_beat_is_edited(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(1, text="6/8"))

        assert p.changes[0] == Change(
            tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(8, "3")
        )

    @pytest.mark.parametrize(
        "units, edited",
        [
            ({(1, 1): unit(4, "1")}, 1),
            ({(1, 1): unit(4, "1"), (1, 2): unit(4, "2")}, 1),
        ],
        ids=["on a later beat", "the first of two"],
    )
    def test_the_unit_already_starting_in_the_measure_is_edited(self, units, edited):
        doc, tl = piece([3, 3, 3], units=units)

        p = plan(doc, tl, bars(2, text="6/8"))

        assert p.changes[0] == Change(
            tl.id, beat(tl, 1, edited), "beat_unit", unit(4, "1"), unit(8, "2")
        )
        assert downbeat(tl, 1) not in {
            c.component_id for c in p.changes if c.key == "beat_unit"
        }


class TestSources:
    def test_every_set_measure_records_the_source_whether_or_not_its_unit_is_written(
        self,
    ):
        doc, tl = piece([3] * 5)

        p = plan(doc, tl, bars(1, 2, 3, text="3/4"), source="import")

        assert p.changes == [
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "1")),
            *[
                Change(tl.id, downbeat(tl, m), "measure.source", None, "import")
                for m in range(3)
            ],
            Change(tl.id, downbeat(tl, 3), "beat_unit", None, DEFAULT),
        ]

    def test_when_every_measure_is_set_from_it_the_marks_lose_their_own(self):
        doc, tl = piece([2, 2, 2], marks={1: {"source": "score"}})

        p = plan(doc, tl, bars(1, 2, 3, text="2/4"), source="import")

        assert p.changes == [
            Change(tl.id, None, "measure_source", "tapped", "import"),
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "1")),
            Change(tl.id, downbeat(tl, 1), "measure.source", "score", None),
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("2/4", False, "import")] * 3
        assert "source" not in tl.components[downbeat(tl, 1)].attrs["measure"]

    def test_with_a_measure_not_set_the_timeline_s_source_stays(self):
        # Bar 3 came from an earlier import; bars 1 and 2 come from this one.
        doc, tl = piece([2, 2, 2], marks={2: {"source": "import"}})

        p = plan(doc, tl, bars(1, 2, text="2/4"), source="import")
        apply_plan(doc, p)

        assert p.changes == [
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "1")),
            Change(tl.id, downbeat(tl, 0), "measure.source", None, "import"),
            Change(tl.id, downbeat(tl, 1), "measure.source", None, "import"),
            Change(tl.id, downbeat(tl, 2), "beat_unit", None, DEFAULT),
        ]
        assert read(doc, tl) == [
            ("2/4", False, "import"),
            ("2/4", False, "import"),
            ("2/4", True, "import"),
        ]

    def test_when_every_measure_reads_it_through_its_own_mark_it_moves_to_the_timeline(
        self,
    ):
        # Bars 1 and 2 imported in one plan and bar 3 in another: each mark
        # records the source, and the timeline doesn't
        # (TimeLineAnnotator/project-management#340).
        doc, tl = piece([3, 3, 3])
        for numbers in [(1, 2), (3,)]:
            apply_plan(doc, plan(doc, tl, bars(*numbers, text="3/4"), source="import"))
        assert read(doc, tl) == [("3/4", False, "import")] * 3
        assert tl.attrs["measure_source"] == "tapped"

        p = plan(doc, tl, bars(1, 2, 3, text="3/4"), source="import")

        assert p.changes == [
            Change(tl.id, None, "measure_source", "tapped", "import"),
            *[
                Change(tl.id, downbeat(tl, m), "measure.source", "import", None)
                for m in range(3)
            ],
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("3/4", False, "import")] * 3
        assert [tl.components[downbeat(tl, m)].attrs["measure"] for m in range(3)] == [
            {}
        ] * 3

    def test_a_table_set_in_several_plans_is_written_as_one_set_in_one(self):
        # With "carry": with "restore", bar 3 keeps the unit plan (1, 2) wrote
        # back on it (TimeLineAnnotator/project-management#361).
        doc, tl = piece([3, 3, 3])
        once = copy.deepcopy(doc)
        carry = {"source": "import", "after": "carry"}

        for numbers in [(1, 2), (3,), (1, 2, 3)]:
            apply_plan(doc, plan(doc, tl, bars(*numbers, text="3/4"), **carry))
        apply_plan(
            once,
            plan(once, once.timelines[tl.id], bars(1, 2, 3, text="3/4"), **carry),
        )

        assert tla.canonical_bytes(doc) == tla.canonical_bytes(once)

    def test_a_plan_of_every_measure_from_the_timeline_s_source_drops_the_copies(
        self,
    ):
        # TimeLineAnnotator/project-management#343
        doc, tl = with_copies()
        assert read(doc, tl) == [("3/4", False, "import")] * 3

        p = plan(doc, tl, bars(1, 2, 3, text="3/4"), source="import")

        assert p.changes == [
            Change(tl.id, downbeat(tl, 0), "measure.source", "import", None),
            Change(tl.id, downbeat(tl, 2), "measure.source", "import", None),
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("3/4", False, "import")] * 3
        assert [tl.components[downbeat(tl, m)].attrs["measure"] for m in range(3)] == [
            {}
        ] * 3

    def test_a_plan_of_some_measures_leaves_the_copies(self):
        doc, tl = with_copies()

        p = plan(doc, tl, bars(1, 2, text="3/4"), source="import")

        assert p == Plan([], [], [])

    def test_a_timeline_without_its_source_stored_has_its_table_s(self):
        doc, tl = piece([2, 2])
        del tl.attrs["measure_source"]

        p = plan(doc, tl, bars(1, 2, text="2/4"), source="import")
        apply_plan(doc, p)
        apply_plan(
            doc,
            Plan(
                [
                    Change(c.timeline_id, c.component_id, c.key, c.new, c.old)
                    for c in reversed(p.changes)
                ]
            ),
        )

        assert p.changes[0] == Change(tl.id, None, "measure_source", "tapped", "import")
        assert tl.attrs["measure_source"] == tl.measures.source == "tapped"
        assert [row.source for row in tl.measures.rows] == ["tapped"] * 2

    def test_an_edit_records_edited_unless_the_measure_is_tapped(self):
        doc, tl = piece(
            [2, 2, 2], marks={1: {"source": "tapped"}}, measure_source="unknown"
        )

        p = plan(doc, tl, bars(1, 2, 3, text="2/4"), source="edit")
        apply_plan(doc, p)

        assert [c for c in p.changes if c.key != "beat_unit"] == [
            Change(tl.id, downbeat(tl, 0), "measure.source", None, "edited"),
            Change(tl.id, downbeat(tl, 2), "measure.source", None, "edited"),
        ]
        assert [source for *_, source in read(doc, tl)] == [
            "edited",
            "tapped",
            "edited",
        ]

    def test_an_edit_of_every_measure_changes_the_timeline_s_source(self):
        doc, tl = piece([2, 2], measure_source="unknown")

        p = plan(doc, tl, bars(1, 2, text="2/4"), source="edit")

        assert p.changes == [
            Change(tl.id, None, "measure_source", "unknown", "edited"),
            Change(tl.id, beat(tl, 0, 0), "beat_unit", DEFAULT, unit(4, "1")),
        ]

    def test_an_edit_of_tapped_measures_leaves_their_source(self):
        doc, tl = piece([2, 2])

        p = plan(doc, tl, bars(1, 2, text="2/4"), source="edit")

        assert written(p) == {beat(tl, 0, 0)}

    def test_a_source_replaces_a_person_s_unit_and_a_later_edit_the_source_s(self):
        # A person set bar 2 of an imported table to 6/8.
        doc, tl = piece(
            [3, 3, 3],
            marks={1: {"source": "edited"}},
            units={(1, 0): unit(8, "2")},
            measure_source="import",
        )
        assert read(doc, tl)[1] == ("6/8", False, "edited")

        p = plan(doc, tl, bars(2, text="9/8"), source="score")
        apply_plan(doc, p)

        assert p.changes[0] == Change(
            tl.id, downbeat(tl, 1), "beat_unit", unit(8, "2"), unit(8, "3")
        )
        assert read(doc, tl)[1] == ("9/8", False, "score")

        apply_plan(doc, plan(doc, tl, bars(2, text="3/4"), source="edit"))

        assert read(doc, tl)[1] == ("3/4", False, "edited")


class TestNoNeedlessWrites:
    @pytest.mark.parametrize(
        "taps, settings, source",
        [
            ([2, 2, 2], bars(2, text="6/8"), "score"),
            ([3, 3], bars(1, text="3/4"), "import"),
            ([1] * 120, bars(*range(1, 121), text="3/4"), "import"),
            ([2, 3, 2, 3], bars(1, 2, 3, 4, text="6/8"), "score"),
            ([3, 3, 3], bars(2, 3, text="2+2+3/8"), "edit"),
            ([2, 2, 4], bars(3, text="6/8"), "edit"),
        ],
    )
    def test_planning_again_after_applying_gives_an_empty_plan(
        self, taps, settings, source
    ):
        doc, tl = piece(taps)
        apply_plan(doc, plan(doc, tl, settings, source=source))

        assert plan(doc, tl, settings, source=source) == Plan([], [], [])

    @pytest.mark.parametrize(
        "units", [{}, {(0, 0): None}], ids=["default unit", "no unit at all"]
    )
    def test_a_bar_that_reads_it_assumed_is_confirmed(self, units):
        doc, tl = piece([3, 3], units=units)
        assert read(doc, tl)[0] == ("3/4", True, "tapped")

        p = plan(doc, tl, bars(1, text="3/4"), source="import")

        assert [(c.key, c.new) for c in p.changes] == [
            ("beat_unit", unit(4, "1")),
            ("measure.source", "import"),
            ("beat_unit", DEFAULT),  # bar 2 stays assumed
        ]
        apply_plan(doc, p)
        assert read(doc, tl) == [("3/4", False, "import"), ("3/4", True, "tapped")]
        assert plan(doc, tl, bars(1, text="3/4"), source="import").changes == []

    def test_a_bar_that_reads_it_from_the_source_is_skipped(self):
        doc, tl = piece(
            [2, 2], marks={0: {"source": "score"}}, units={(0, 0): unit(8, "3")}
        )

        assert plan(doc, tl, bars(1, text="6/8")) == Plan([], [], [])

    def test_planning_again_after_the_source_moves_to_the_timeline_gives_an_empty_plan(
        self,
    ):
        doc, tl = piece([3, 3, 3])
        for numbers in [(1, 2), (3,), (1, 2, 3)]:
            apply_plan(doc, plan(doc, tl, bars(*numbers, text="3/4"), source="import"))
        assert tl.attrs["measure_source"] == "import"

        p = plan(doc, tl, bars(1, 2, 3, text="3/4"), source="import")

        assert p == Plan([], [], [])

    def test_planning_again_after_the_copies_of_the_timeline_s_source_go_is_empty(
        self,
    ):
        doc, tl = with_copies()
        settings = bars(1, 2, 3, text="3/4")
        apply_plan(doc, plan(doc, tl, settings, source="import"))
        assert "source" not in tl.components[downbeat(tl, 0)].attrs["measure"]

        p = plan(doc, tl, settings, source="import")

        assert p == Plan([], [], [])

    def test_every_bar_that_reads_it_from_the_timeline_is_skipped(self):
        doc, tl = piece(
            [3, 3, 3], units={(0, 0): unit(4, "1")}, measure_source="import"
        )
        assert read(doc, tl) == [("3/4", False, "import")] * 3

        p = plan(doc, tl, bars(1, 2, 3, text="3/4"), source="import")

        assert p == Plan([], [], [])

    def test_a_bar_whose_unit_is_carried_needs_none_of_its_own(self):
        doc, tl = piece([2, 2, 2], units={(0, 0): unit(8, "3")})

        assert plan(doc, tl, bars(3, text="6/8"), source="edit").changes == []

    def test_a_bar_that_reads_it_from_another_source_gets_only_the_source(self):
        doc, tl = piece([2, 2], units={(0, 0): unit(8, "3")})

        p = plan(doc, tl, bars(2, text="6/8"))

        assert p.changes == [
            Change(tl.id, downbeat(tl, 1), "measure.source", None, "score")
        ]

    def test_a_unit_written_the_other_way_is_the_same_unit(self):
        doc, tl = piece([2, 2], units={(0, 0): unit(8, "6/2")})

        assert plan(doc, tl, bars(1, text="6/8"), source="edit").changes == []


class TestAfter:
    def test_carry_writes_nothing_more_so_the_measures_after_take_the_unit(self):
        doc, tl = piece([2, 2, 2, 2])

        p = plan(doc, tl, bars(2, text="6/8"), after="carry")
        apply_plan(doc, p)

        assert written(p) == {downbeat(tl, 1)}
        assert read(doc, tl) == [
            ("2/4", True, "tapped"),
            ("6/8", False, "score"),
            ("6/8", False, "tapped"),
            ("6/8", False, "tapped"),
        ]

    def test_restore_is_the_default(self):
        doc, tl = piece([2, 2, 2])
        settings = bars(2, text="6/8")

        default = plan_time_signatures(doc, tl.id, settings, source="score")

        assert default == plan(doc, tl, settings, after="restore")
        assert default != plan(doc, tl, settings, after="carry")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"after": "until the next"},
            {"source": "tapped"},
            {"source": "edited"},
        ],
    )
    def test_other_values_are_refused(self, kwargs):
        doc, tl = piece([2, 2, 2])

        with pytest.raises(ValueError):
            plan(doc, tl, bars(2, text="6/8"), **kwargs)

    def test_a_timeline_that_isnt_a_beat_timeline_of_the_document_is_refused(self):
        doc, tl = piece([2, 2, 2])

        with pytest.raises(ValueError):
            plan_time_signatures(
                doc, "elsewhere", bars(2, text="6/8"), source="score", after="carry"
            )


def unit_writes(p):
    """The units a plan writes, by component."""
    return {c.component_id: c.new for c in p.changes if c.key == "beat_unit"}


# Two songs of three bars of two taps, the second marked as a restart. Only the
# first bar has a unit, the default, so the second song reads it, assumed.
SONGS = {3: {"number": 1, "restart": True}}


class TestRestore:
    def test_the_bar_after_a_run_gets_its_old_unit_back(self):
        doc, tl = piece([2, 2, 2, 2])

        p = plan(doc, tl, bars(2, text="6/8"))
        apply_plan(doc, p)

        assert p.changes == [
            Change(tl.id, downbeat(tl, 1), "beat_unit", None, unit(8, "3")),
            Change(tl.id, downbeat(tl, 1), "measure.source", None, "score"),
            Change(tl.id, downbeat(tl, 2), "beat_unit", None, DEFAULT),
        ]
        assert read(doc, tl) == [
            ("2/4", True, "tapped"),
            ("6/8", False, "score"),
            ("2/4", True, "tapped"),
            ("2/4", True, "tapped"),
        ]

    def test_with_its_old_assumed(self):
        doc, tl = piece([2, 2, 2], units={(0, 0): unit(4, "1")})

        p = plan(doc, tl, bars(2, text="6/8"))

        assert p.changes[-1] == Change(
            tl.id, downbeat(tl, 2), "beat_unit", None, unit(4, "1")
        )

    def test_confirming_a_bar_keeps_the_next_one_assumed(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(2, text="2/4"))
        apply_plan(doc, p)

        assert unit_writes(p) == {
            downbeat(tl, 1): unit(4, "1"),
            downbeat(tl, 2): DEFAULT,
        }
        assert [assumed for _, assumed, _ in read(doc, tl)] == [True, False, True]

    def test_each_run_gets_its_own_write_back(self):
        # TimeLineAnnotator/project-management#194's example: bars 45-50 and
        # 55-60 set, write-backs on 51 and 61.
        doc, tl = piece([2] * 65)
        matched = [*range(45, 51), *range(55, 61)]

        p = plan(doc, tl, bars(*matched, text="6/8"))
        apply_plan(doc, p)

        assert unit_writes(p) == {
            downbeat(tl, 44): unit(8, "3"),
            downbeat(tl, 50): DEFAULT,
            downbeat(tl, 54): unit(8, "3"),
            downbeat(tl, 60): DEFAULT,
        }
        assert read(doc, tl) == [
            ("6/8", False, "score") if n in matched else ("2/4", True, "tapped")
            for n in range(1, 66)
        ]

    @pytest.mark.parametrize("b", [0, 1], ids=["on its downbeat", "on a later beat"])
    def test_a_bar_after_a_run_that_starts_its_own_unit_gets_none(self, b):
        doc, tl = piece([2, 2, 2], units={(2, b): unit(4, "1")})

        p = plan(doc, tl, bars(2, text="6/8"))

        assert written(p) == {downbeat(tl, 1)}

    def test_a_run_at_the_end_needs_none(self):
        doc, tl = piece([2, 2, 2])

        p = plan(doc, tl, bars(2, 3, text="6/8"))

        assert written(p) == {downbeat(tl, 1), downbeat(tl, 2)}

    def test_the_bars_before_the_timeline_s_first_unit_keep_their_reading(self):
        # TimeLineAnnotator/project-management#322: four bars of two taps,
        # with no unit, and bar 3 set to 6/8.
        doc, tl = piece([2, 2, 2, 2], units={(0, 0): None})
        assert read(doc, tl) == [("2/4", True, "tapped")] * 4

        p = plan(doc, tl, bars(3, text="6/8"))
        apply_plan(doc, p)

        assert p.changes == [
            Change(tl.id, downbeat(tl, 0), "beat_unit", None, DEFAULT),
            Change(tl.id, downbeat(tl, 2), "beat_unit", None, unit(8, "3")),
            Change(tl.id, downbeat(tl, 2), "measure.source", None, "score"),
            Change(tl.id, downbeat(tl, 3), "beat_unit", None, DEFAULT),
        ]
        assert read(doc, tl) == [
            ("2/4", True, "tapped"),
            ("2/4", True, "tapped"),
            ("6/8", False, "score"),
            ("2/4", True, "tapped"),
        ]

    def test_they_keep_the_values_they_took_from_a_later_unit(self):
        doc, tl = piece([2, 2, 2, 2], units={(0, 0): None, (3, 0): unit(8, "3")})
        assert read(doc, tl)[0] == ("6/8", True, "tapped")

        p = plan(doc, tl, bars(2, text="3/4"))
        apply_plan(doc, p)

        assert unit_writes(p) == {
            downbeat(tl, 0): unit(8, "3", assumed=True),
            downbeat(tl, 1): unit(4, "3/2"),
            downbeat(tl, 2): unit(8, "3", assumed=True),
        }
        assert read(doc, tl) == [
            ("6/8", True, "tapped"),
            ("3/4", False, "score"),
            ("6/8", True, "tapped"),
            ("6/8", False, "tapped"),
        ]

    def test_the_first_bar_set_needs_no_opening_unit(self):
        doc, tl = piece([2, 2, 2], units={(0, 0): None})

        p = plan(doc, tl, bars(1, text="6/8"))

        assert unit_writes(p) == {
            downbeat(tl, 0): unit(8, "3"),
            downbeat(tl, 1): DEFAULT,
        }

    class TestOnlyWhereABarWouldReadDifferently:
        # TimeLineAnnotator/project-management#356

        def test_no_write_back_where_the_bar_after_reads_the_same(self):
            # 3/4 set by a person; a score gives bars 3-5 the same 3/4.
            doc, tl = piece(
                [3] * 8, units={(0, 0): unit(4, "1")}, measure_source="edited"
            )

            p = plan(doc, tl, bars(3, 4, 5, text="3/4"))

            assert {c.key for c in p.changes} == {"measure.source"}

        def test_no_opening_unit_where_the_bars_before_read_the_same(self):
            doc, tl = piece([2, 2, 2, 2], units={(0, 0): None})

            p = plan(doc, tl, bars(3, text="2/4"))

            assert unit_writes(p) == {
                downbeat(tl, 2): unit(4, "1"),
                downbeat(tl, 3): DEFAULT,  # it would lose "assumed"
            }

    class TestMovements:
        # TimeLineAnnotator/project-management#357

        def test_a_movement_s_first_unit_keeps_its_bars_before_it(self):
            doc, tl = piece([2] * 6, marks=SONGS)

            p = plan(doc, tl, [(BarRef(3, movement=2), ts("6/8"))])
            apply_plan(doc, p)

            assert unit_writes(p) == {
                downbeat(tl, 3): DEFAULT,
                downbeat(tl, 5): unit(8, "3"),
            }
            assert read(doc, tl) == [("2/4", True, "tapped")] * 5 + [
                ("6/8", False, "score")
            ]

        def test_a_run_that_ends_a_movement_keeps_the_next_one_s_reading(self):
            doc, tl = piece([2] * 6, marks=SONGS)

            p = plan(doc, tl, [(BarRef(3, movement=1), ts("6/8"))])
            apply_plan(doc, p)

            assert unit_writes(p) == {
                downbeat(tl, 2): unit(8, "3"),
                downbeat(tl, 3): DEFAULT,
            }
            assert read(doc, tl) == [
                ("2/4", True, "tapped"),
                ("2/4", True, "tapped"),
                ("6/8", False, "score"),
                *[("2/4", True, "tapped")] * 3,
            ]

        def test_a_movement_with_a_unit_of_its_own_needs_none(self):
            # Song 2's bar 1 reads a copy of the unit on its bar 2.
            doc, tl = piece([2] * 6, marks=SONGS, units={(4, 0): unit(4, "1")})

            p = plan(doc, tl, [(BarRef(3, movement=1), ts("6/8"))])

            assert written(p) == {downbeat(tl, 2)}

    def test_the_reverse_plan_restores_the_components(self):
        doc, tl = piece([2, 2, 2, 2], units={(0, 0): None})
        components = copy.deepcopy(tl.components)
        p = plan(doc, tl, bars(3, text="6/8"))
        apply_plan(doc, p)

        apply_plan(
            doc,
            Plan(
                [
                    Change(c.timeline_id, c.component_id, c.key, c.new, c.old)
                    for c in reversed(p.changes)
                ]
            ),
        )

        assert tl.components == components


class TestRestoreOnAnyTable:
    """Plans for tables made at random: units of every kind on any beat,
    restarts, and time signatures on any bars."""

    UNITS = [
        unit(4, "1"),
        DEFAULT,
        unit(8, "3"),
        unit(8, "2", assumed=True),
        unit(4, "3/2"),
        unit(8, "2+3"),
        {"denominator": 200, "units": "x"},  # one that can't be read
    ]
    TIME_SIGNATURES = ["2/4", "3/4", "6/8", "2+2+3/8", "(3/2)/4"]

    def case(self, seed):
        rng = random.Random(seed)
        taps = [rng.randint(1, 4) for _ in range(rng.randint(1, 7))]
        marks = {
            m: {"restart": True} for m in range(1, len(taps)) if rng.random() < 0.2
        }
        units = {
            (m, b): rng.choice(self.UNITS) if rng.random() < 0.2 else None
            for m, count in enumerate(taps)
            for b in range(count)
        }
        doc, tl = piece(taps, marks=marks, units=units)
        settings = [
            (row.id, ts(rng.choice(self.TIME_SIGNATURES)))
            for row in tl.measures.rows
            if rng.random() < 0.4
        ]
        return doc, tl, settings, rng.choice(["score", "import", "edit"])

    @staticmethod
    def readings(doc, tl):
        return [
            (r.meter.denominator, r.meter.units, r.assumed) for r in build_rows(doc, tl)
        ]

    def test_only_the_bars_set_change(self):
        for seed in range(300):
            doc, tl, settings, source = self.case(seed)
            before = self.readings(doc, tl)
            wanted = dict(settings)

            apply_plan(doc, plan(doc, tl, settings, source))

            rows = build_rows(doc, tl)
            for row, old, new in zip(rows, before, self.readings(doc, tl), strict=True):
                time_signature = wanted.get(row.id)
                if time_signature is None:
                    assert new == old, f"seed {seed}, bar {row.label}"
                else:
                    assert not row.assumed, f"seed {seed}, bar {row.label}"
                    assert row.ts_numerator == sum(time_signature.parts)
                    assert row.ts_denominator == time_signature.denominator

    def test_planning_again_gives_an_empty_plan(self):
        for seed in range(300):
            doc, tl, settings, source = self.case(seed)

            apply_plan(doc, plan(doc, tl, settings, source))

            assert plan(doc, tl, settings, source).changes == [], f"seed {seed}"

    def test_a_bar_not_set_is_written_only_where_it_must_be(self):
        # On the downbeat of a bar after one set, or of a movement's first
        # bar, and only where the bars not set would read differently without it.
        for seed in range(300):
            doc, tl, settings, source = self.case(seed)
            rows = build_rows(doc, tl)
            wanted = {bar for bar, _ in settings}
            before = self.readings(doc, tl)
            p = plan(doc, tl, settings, source)

            set_beats = {b for row in rows if row.id in wanted for b in row.beat_ids}
            for change in p.changes:
                if change.component_id is None or change.component_id in set_beats:
                    continue
                index = next(
                    i for i, row in enumerate(rows) if row.id == change.component_id
                )
                assert change.key == "beat_unit", f"seed {seed}"
                assert index == 0 or (
                    rows[index - 1].id in wanted
                    or rows[index].movement != rows[index - 1].movement
                ), f"seed {seed}"
                without = copy.deepcopy(doc)
                apply_plan(without, Plan([c for c in p.changes if c != change]))
                after = self.readings(without, without.timelines[tl.id])
                assert any(
                    old != new
                    for row, old, new in zip(rows, before, after, strict=True)
                    if row.id not in wanted
                ), f"seed {seed}: a needless write on bar {rows[index].label}"


class TestMatching:
    # Bars 11, 12, 13, then 12 and 13 again.
    REPEAT = {0: {"number": 11}, 3: {"number": 12}}

    def test_a_bar_number_sets_every_time_through(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, bars(12, text="6/8"))
        apply_plan(doc, p)

        assert set_bars(p) == {downbeat(tl, 1), downbeat(tl, 3)}
        rows = read(doc, tl)
        assert rows[1] == rows[3] == ("6/8", False, "score")

    def test_a_pass_narrows_it_to_one_time_through(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, [(BarRef(12, pass_=2), ts("6/8"))])

        assert set_bars(p) == {downbeat(tl, 3)}

    def test_a_bar_the_table_doesnt_have_is_reported_and_nothing_written(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)
        missing = [BarRef(14), BarRef(12, pass_=3), BarRef()]

        p = plan(doc, tl, [(bar, ts("6/8")) for bar in missing])

        assert p == Plan(changes=[], unmatched=missing, ambiguous=[])

    def test_only_the_bars_it_has_are_written(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, bars(14, 11, text="6/8"))

        assert p.unmatched == [BarRef(14)]
        assert set_bars(p) == {downbeat(tl, 0)}

    def test_a_cadenza_is_matched_by_its_label_only(self):
        # Bars 1, 2, 2c and 3.
        marks = {2: {"number": 2, "label": "2c", "cadenza": True}}
        doc, tl = piece([2] * 4, marks=marks)

        by_number = plan(doc, tl, bars(2, text="6/8"))
        by_label = plan(doc, tl, [(BarRef(label="2c"), ts("6/8"))])

        assert set_bars(by_number) == {downbeat(tl, 1)}
        assert set_bars(by_label) == {downbeat(tl, 2)}

    def test_a_downbeat_s_id_names_its_measure(self):
        doc, tl = piece([2, 2, 2])
        not_a_downbeat = beat(tl, 1, 1)

        p = plan(
            doc,
            tl,
            [(downbeat(tl, 2), ts("6/8")), (not_a_downbeat, ts("6/8"))],
        )

        assert written(p) == {downbeat(tl, 2)}
        assert p.unmatched == [not_a_downbeat]

    class TestMovements:
        # Bars 1, 2, 3, then a second song's 1 and 2.
        SONGS = {3: {"number": 1, "restart": True}}

        @pytest.mark.parametrize("bar", [BarRef(1), BarRef(1, pass_=1)])
        def test_a_bar_found_in_more_than_one_movement_is_ambiguous(self, bar):
            doc, tl = piece([2] * 5, marks=self.SONGS)

            p = plan(doc, tl, [(bar, ts("6/8"))])

            assert p == Plan(changes=[], unmatched=[], ambiguous=[bar])

        def test_a_movement_names_one(self):
            doc, tl = piece([2] * 5, marks=self.SONGS)

            p = plan(doc, tl, [(BarRef(1, movement=2), ts("6/8"))])

            assert set_bars(p) == {downbeat(tl, 3)}

        def test_a_bar_found_in_one_movement_needs_none(self):
            doc, tl = piece([2] * 5, marks=self.SONGS)

            p = plan(doc, tl, bars(3, text="6/8"))

            assert set_bars(p) == {downbeat(tl, 2)}

        def test_a_movement_without_the_bar_finds_nothing(self):
            doc, tl = piece([2] * 5, marks=self.SONGS)
            bar = BarRef(3, movement=2)

            assert plan(doc, tl, [(bar, ts("6/8"))]).unmatched == [bar]

        def test_a_plan_across_a_restart_reads_as_planned(self):
            doc, tl = piece([2] * 5, marks=self.SONGS)
            settings = [(BarRef(n, movement=2), ts("6/8")) for n in (1, 2)]

            apply_plan(doc, plan(doc, tl, settings))

            assert [r[0] for r in read(doc, tl)][3:] == ["6/8", "6/8"]
            assert plan(doc, tl, settings).changes == []


class TestApply:
    def test_planning_changes_nothing(self):
        doc, tl = piece([2, 2, 2], marks={1: {"source": "score"}})
        before = copy.deepcopy(doc)

        plan(doc, tl, bars(1, 2, 3, text="6/8"), source="import")

        assert doc == before

    def test_the_new_time_signatures_not_assumed_with_the_new_source(self):
        doc, tl = piece([2, 3, 2])

        apply_plan(doc, plan(doc, tl, bars(2, text="6/8")))

        assert read(doc, tl) == [
            ("2/4", True, "tapped"),
            ("6/8", False, "score"),
            ("2/4", True, "tapped"),  # its old unit, written back
        ]

    def test_the_measure_table_follows(self):
        doc, tl = piece([2, 2, 2])

        apply_plan(doc, plan(doc, tl, bars(2, text="6/8")))

        rows = tl.measures.rows
        assert [row.source for row in rows] == ["tapped", "score", "tapped"]
        assert rows[1].beat_units == [tla.BeatUnit(denominator=8, units="3")]

        apply_plan(doc, plan(doc, tl, bars(1, 2, 3, text="6/8"), source="import"))

        assert tl.measures.source == tl.attrs["measure_source"] == "import"
        assert [row.source for row in rows] == ["import"] * 3
        assert rows[0].beat_units == [tla.BeatUnit(denominator=8, units="3")]

    # Edits to bar 4 after planning bar 2 to 6/8 and bar 4 to 2/4, whose two
    # changes are the plan's last (after bar 3's write-back), and the change
    # each makes stale.
    STALE = [
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)].attrs.update(
                beat_unit=unit(4, "2")
            ),
            3,
            id="a unit set",
        ),
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)]
            .attrs["measure"]
            .update(source="import"),
            4,
            id="a source set",
        ),
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)].attrs.pop("measure"),
            4,
            id="no longer a downbeat",
        ),
        pytest.param(lambda tl: tl.components.pop(downbeat(tl, 3)), 3, id="deleted"),
    ]

    @pytest.mark.parametrize("edit, refused", STALE)
    def test_a_stale_plan_is_refused_and_the_document_unchanged(self, edit, refused):
        doc, tl = piece([2, 2, 2, 2])
        p = plan(doc, tl, [(BarRef(2), ts("6/8")), (BarRef(4), ts("2/4"))])
        edit(tl)
        before = copy.deepcopy(doc)

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(doc, p)

        assert raised.value.change == p.changes[refused]
        assert doc == before

    # Edits after planning that change no value the plan writes, but what it
    # was made from.
    UNDER_IT = [
        pytest.param(
            {},
            lambda tl: add_beat(tl, 1, 3.5),
            bars(2, text="6/8"),
            id="a beat added to the measure",
        ),
        pytest.param(
            {"units": {(0, 0): unit(8, "3")}},
            lambda tl: tl.components[beat(tl, 0, 0)].attrs.update(
                beat_unit=unit(4, "1")
            ),
            bars(3, text="6/8"),
            id="the unit carried into it changed",
        ),
        pytest.param(
            {"marks": {1: {"source": "score"}}, "measure_source": "import"},
            lambda tl: tl.attrs.update(measure_source="tapped"),
            bars(2, text="2/4"),
            id="the timeline's source changed",
        ),
    ]

    @pytest.mark.parametrize("setup, edit, settings", UNDER_IT)
    def test_a_plan_whose_measures_changed_is_refused(self, setup, edit, settings):
        doc, tl = piece([2, 2, 2], **setup)
        p = plan(doc, tl, settings, source="import")
        edit(tl)
        before = copy.deepcopy(doc)

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(doc, p)

        assert raised.value.change is None
        assert doc == before

    def test_a_unit_edited_in_place_after_planning_is_stale(self):
        # A unit the table can't read, which it ignores: only the old value
        # the plan kept shows the edit.
        doc, tl = piece([2, 2], units={(1, 0): {"denominator": 200, "units": "x"}})
        p = plan(doc, tl, bars(2, text="6/8"))
        tl.components[downbeat(tl, 1)].attrs["beat_unit"]["denominator"] = 300
        before = copy.deepcopy(doc)

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(doc, p)

        assert raised.value.change == p.changes[0]
        assert doc == before

    def test_a_stale_timeline_source_is_refused(self):
        doc, tl = piece([2, 2])
        p = plan(doc, tl, bars(1, 2, text="6/8"))
        tl.attrs["measure_source"] = "unknown"
        before = copy.deepcopy(doc)

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(doc, p)

        assert raised.value.change.key == "measure_source"
        assert doc == before

    def test_changes_apply_in_order_and_the_last_wins(self):
        doc, tl = piece([2, 2])
        d = downbeat(tl, 1)

        apply_plan(
            doc,
            Plan(
                [
                    Change(tl.id, d, "beat_unit", None, unit(8, "3")),
                    Change(tl.id, d, "beat_unit", unit(8, "3"), unit(8, "2")),
                ]
            ),
        )

        assert tl.components[d].attrs["beat_unit"] == unit(8, "2")

    def test_a_change_is_checked_against_the_changes_before_it(self):
        doc, tl = piece([2, 2])
        d = downbeat(tl, 1)
        before = copy.deepcopy(doc)
        second = Change(tl.id, d, "beat_unit", None, unit(8, "2"))

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(
                doc,
                Plan([Change(tl.id, d, "beat_unit", None, unit(8, "3")), second]),
            )

        assert raised.value.change == second
        assert doc == before

    def test_changes_to_the_timeline_s_source_are_checked_against_each_other(self):
        doc, tl = piece([2, 2])
        before = copy.deepcopy(doc)
        # A component id means nothing for the timeline's source.
        second = Change(tl.id, "elsewhere", "measure_source", "tapped", "score")

        with pytest.raises(PlanOutOfDate) as raised:
            apply_plan(
                doc,
                Plan(
                    [Change(tl.id, None, "measure_source", "tapped", "import"), second]
                ),
            )

        assert raised.value.change == second
        assert doc == before

    def test_the_table_lists_the_units_the_measure_table_reads(self):
        unreadable = {"denominator": 200, "units": "x"}
        doc, tl = piece([3, 3], units={(1, 2): unreadable})

        apply_plan(doc, plan(doc, tl, bars(2, text="6/8")))

        assert tl.measures.rows[1].beat_units == [
            tla.BeatUnit(denominator=8, units="2")
        ]

    def test_the_reverse_plan_restores_the_components_and_the_timeline(self):
        doc, tl = piece([2, 2, 2], marks={1: {"source": "score"}})
        components, attrs = copy.deepcopy(tl.components), copy.deepcopy(tl.attrs)
        p = plan(doc, tl, bars(1, 2, 3, text="6/8"), source="import")
        apply_plan(doc, p)

        apply_plan(
            doc,
            Plan(
                [
                    Change(c.timeline_id, c.component_id, c.key, c.new, c.old)
                    for c in reversed(p.changes)
                ]
            ),
        )

        assert tl.components == components
        assert tl.attrs == attrs

    def test_apply_then_plan_again_gives_an_empty_plan(self):
        doc, tl = piece([2, 3, 2], marks={2: {"source": "score"}})
        settings = bars(1, 2, 3, text="6/8")

        apply_plan(doc, plan(doc, tl, settings, source="edit"))

        assert plan(doc, tl, settings, source="edit") == Plan([], [], [])

    def test_no_file_is_opened(self, monkeypatch):
        doc, tl = piece([2, 2, 2])

        def refuse(*args, **kwargs):
            raise AssertionError("a file was opened")

        for module in (builtins, io, os):
            monkeypatch.setattr(module, "open", refuse)
        apply_plan(doc, plan(doc, tl, bars(1, 2, 3, text="6/8")))
        monkeypatch.undo()

        assert read(doc, tl) == [("6/8", False, "score")] * 3
