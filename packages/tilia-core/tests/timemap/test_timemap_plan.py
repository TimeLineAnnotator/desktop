"""Time signatures from a source or an edit, as plans of beat-unit writes, and applying them."""

import builtins
import copy
import io
import logging
import os
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


def ts(text):
    return TimeSignature.parse(text)


def bars(*numbers, text):
    """Settings giving the bars `numbers` the time signature `text`."""
    return [(BarRef(number), ts(text)) for number in numbers]


def plan(doc, timeline, settings, source="score", after="carry"):
    return plan_time_signatures(doc, timeline.id, settings, source=source, after=after)


def read(doc, timeline):
    """Each measure's time signature, whether it is assumed, and its source."""
    return [(r.time_signature, r.assumed, r.source) for r in build_rows(doc, timeline)]


def written(p):
    """The components a plan writes to."""
    return {change.component_id for change in p.changes}


class TestTimeSignature:
    @pytest.mark.parametrize(
        "beat_values, denominator, parts",
        [
            ([3, 3], 8, (6,)),
            ([2, 2, 3], 8, (2, 2, 3)),
            ([2, 3, 2], 8, (2, 3, 2)),
            ([F(1, 3)] * 4, 4, (F(4, 3),)),
            ([F(1, 2), 1], 8, (F(1, 2), 1)),
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

    def test_parts_are_fractions(self):
        assert TimeSignature((6,), 8).parts == (F(6),)
        assert isinstance(TimeSignature((6,), 8).parts[0], F)

    @pytest.mark.parametrize(
        "parts, denominator", [((), 8), ((0,), 8), ((6,), 0), ((6,), 129)]
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
        ]
        apply_plan(doc, p)
        assert read(doc, tl)[:120] == [("3/4", False, "import")] * 120

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
        ]

    def test_when_every_measure_ends_with_it_the_marks_lose_their_own(self):
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

    def test_a_measure_not_set_keeps_its_mark_when_the_timeline_s_source_changes(
        self,
    ):
        # Bar 3 came from an earlier import; bars 1 and 2 come from this one.
        doc, tl = piece([2, 2, 2], marks={2: {"source": "import"}})

        p = plan(doc, tl, bars(1, 2, text="2/4"), source="import")
        apply_plan(doc, p)

        assert p.changes[0] == Change(tl.id, None, "measure_source", "tapped", "import")
        assert downbeat(tl, 2) not in written(p)
        assert read(doc, tl) == [("2/4", False, "import")] * 3

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
        ]
        apply_plan(doc, p)
        assert read(doc, tl)[0] == ("3/4", False, "import")
        assert plan(doc, tl, bars(1, text="3/4"), source="import").changes == []

    def test_a_bar_that_reads_it_from_the_source_is_skipped(self):
        doc, tl = piece(
            [2, 2], marks={0: {"source": "score"}}, units={(0, 0): unit(8, "3")}
        )

        assert plan(doc, tl, bars(1, text="6/8")) == Plan([], [], [])

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

    def test_restore_waits_for_its_decision(self):
        doc, tl = piece([2, 2, 2])

        with pytest.raises(ValueError, match="#194"):
            plan(doc, tl, bars(2, text="6/8"), after="restore")

    def test_after_has_no_default(self):
        doc, tl = piece([2, 2, 2])

        with pytest.raises(TypeError):
            plan_time_signatures(doc, tl.id, bars(2, text="6/8"), source="score")

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


class TestMatching:
    # Bars 11, 12, 13, then 12 and 13 again.
    REPEAT = {0: {"number": 11}, 3: {"number": 12}}

    def test_a_bar_number_sets_every_time_through(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, bars(12, text="6/8"))
        apply_plan(doc, p)

        assert written(p) == {downbeat(tl, 1), downbeat(tl, 3)}
        rows = read(doc, tl)
        assert rows[1] == rows[3] == ("6/8", False, "score")

    def test_a_pass_narrows_it_to_one_time_through(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, [(BarRef(12, pass_=2), ts("6/8"))])

        assert written(p) == {downbeat(tl, 3)}

    def test_a_bar_the_table_doesnt_have_is_reported_and_nothing_written(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)
        missing = [BarRef(14), BarRef(12, pass_=3), BarRef()]

        p = plan(doc, tl, [(bar, ts("6/8")) for bar in missing])

        assert p == Plan(changes=[], unmatched=missing, ambiguous=[])

    def test_only_the_bars_it_has_are_written(self):
        doc, tl = piece([2] * 5, marks=self.REPEAT)

        p = plan(doc, tl, bars(14, 11, text="6/8"))

        assert p.unmatched == [BarRef(14)]
        assert written(p) == {beat(tl, 0, 0), downbeat(tl, 0)}

    def test_a_cadenza_is_matched_by_its_label_only(self):
        # Bars 1, 2, 2c and 3.
        marks = {2: {"number": 2, "label": "2c", "cadenza": True}}
        doc, tl = piece([2] * 4, marks=marks)

        by_number = plan(doc, tl, bars(2, text="6/8"))
        by_label = plan(doc, tl, [(BarRef(label="2c"), ts("6/8"))])

        assert written(by_number) == {downbeat(tl, 1)}
        assert written(by_label) == {downbeat(tl, 2)}

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

            assert written(p) == {downbeat(tl, 3)}

        def test_a_bar_found_in_one_movement_needs_none(self):
            doc, tl = piece([2] * 5, marks=self.SONGS)

            p = plan(doc, tl, bars(3, text="6/8"))

            assert written(p) == {downbeat(tl, 2)}

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
            ("4/8", False, "tapped"),  # two taps under the unit carried on
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
    # changes are the plan's last, and the change each makes stale.
    STALE = [
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)].attrs.update(
                beat_unit=unit(4, "2")
            ),
            2,
            id="a unit set",
        ),
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)]
            .attrs["measure"]
            .update(source="import"),
            3,
            id="a source set",
        ),
        pytest.param(
            lambda tl: tl.components[downbeat(tl, 3)].attrs.pop("measure"),
            3,
            id="no longer a downbeat",
        ),
        pytest.param(lambda tl: tl.components.pop(downbeat(tl, 3)), 2, id="deleted"),
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

    def test_a_unit_edited_in_place_after_planning_is_stale(self):
        doc, tl = piece([2, 2])
        p = plan(doc, tl, bars(1, text="6/8"))
        tl.components[beat(tl, 0, 0)].attrs["beat_unit"]["units"] = "2"
        before = copy.deepcopy(doc)

        with pytest.raises(PlanOutOfDate):
            apply_plan(doc, p)

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
