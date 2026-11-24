"""A time that can't be shown as a media time, an infinite one or an integer too
large for a float, is refused and reported like any other, however it comes: when
a component is created, imported from a CSV or made by an edit. The texts show it
as the core shows such a number ("inf")."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from tests.mock import Serve, patch_file_dialog
from tilia.requests import Get, Post, post
from tilia.timelines.base.shown_time import shown_time
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia.ui.format import format_media_time
from tilia_core import rules

INF = math.inf
TOO_LARGE = 10**400  # for a float

POINTS = {
    ComponentKind.MARKER: ("marker_tl", "Marker"),
    ComponentKind.BEAT: ("beat_tl", "Beat"),
    ComponentKind.HARMONY: ("harmony_tl", "Harmony"),
    ComponentKind.MODE: ("harmony_tl", "Mode"),
    ComponentKind.PDF_MARKER: ("pdf_tl", "PDF page marker"),
}
HIERARCHY, RANGE = ComponentKind.HIERARCHY, ComponentKind.RANGE
FIXTURES = {
    **{kind: fixture for kind, (fixture, _) in POINTS.items()},
    HIERARCHY: "hierarchy_tl",
    RANGE: "range_tl",
}

# (kind, attributes, text), with a media length of 01:40.0.
REFUSED = [
    *(
        (
            kind,
            {"time": value},
            f"{name} time '{value}' is bigger than media time" " '01:40.0'",
        )
        for kind, (_, name) in POINTS.items()
        for value in (INF, TOO_LARGE)
    ),
    *(
        (kind, {"time": -INF}, f"{name} time can't be negative. Got '-inf'")
        for kind, (_, name) in POINTS.items()
    ),
    (
        HIERARCHY,
        {"start": INF, "end": INF},
        "Hierarchy start 'inf' is bigger than media time '01:40.0'",
    ),
    *(
        (
            kind,
            {"start": 1.0, "end": value},
            f"{name} end '{value}' is bigger than" " media time '01:40.0'",
        )
        for kind, name in ((HIERARCHY, "Hierarchy"), (RANGE, "Range"))
        for value in (INF, TOO_LARGE)
    ),
    *(
        (
            kind,
            {"start": 1.0, "end": -INF},
            f"{name} end '-inf' should be bigger than start '00:01.0'",
        )
        for kind, name in ((HIERARCHY, "Hierarchy"), (RANGE, "Range"))
    ),
    (
        RANGE,
        {"start": INF, "end": INF},
        "Range end 'inf' should be bigger than start 'inf'",
    ),
    (
        RANGE,
        {"start": -INF, "end": 2.0},
        "Range start can't be negative. Got '-inf'",
    ),
    (
        RANGE,
        {"start": 1.0, "end": 2.0, "pre_start": -INF},
        "Range pre-start can't be negative. Got '-inf'",
    ),
    (
        RANGE,
        {"start": 1.0, "end": 2.0, "post_end": INF},
        "Range post-end 'inf' is bigger than media time '01:40.0'",
    ),
]


def with_the_rest(timeline, kind: ComponentKind, attrs: dict) -> dict:
    """`attrs`, with what else a component of `kind` is created with."""
    if kind == HIERARCHY:
        return {"level": 1, **attrs}
    if kind == RANGE:
        return {"row_id": timeline.rows[0].id, **attrs}
    if kind == ComponentKind.PDF_MARKER:
        return {"page_number": 1, **attrs}
    if kind == ComponentKind.HARMONY:
        return {"step": 0, "accidental": 0, "quality": "major", **attrs}
    if kind == ComponentKind.MODE:
        return {"step": 0, "accidental": 0, "type": "major", **attrs}
    return attrs


def short(value) -> str:
    if isinstance(value, dict):
        return "-".join(f"{k}={short(v)}" for k, v in value.items())
    if isinstance(value, ComponentKind):
        return value.name.lower()
    text = str(value)
    return text if len(text) < 20 else "too_large"


class TestCreate:
    @pytest.mark.parametrize("kind, attrs, text", REFUSED, ids=short)
    def test_is_refused_with_the_number_as_it_is(
        self, request, tilia_state, kind, attrs, text
    ):
        timeline = request.getfixturevalue(FIXTURES[kind])
        assert tilia_state.duration == 100
        attrs = with_the_rest(timeline, kind, attrs)
        assert timeline.create_component(kind, **attrs) == (None, text)
        assert timeline.is_empty

    @pytest.mark.parametrize("length", [INF, TOO_LARGE], ids=short)
    @pytest.mark.parametrize("kind", FIXTURES, ids=short)
    def test_a_media_length_that_cant_be_shown_refuses_nothing(
        self, request, tilia_state, kind, length
    ):
        # Every time is within it, and a text that isn't given isn't made.
        timeline = request.getfixturevalue(FIXTURES[kind])
        times = {"time": 1.0} if kind in POINTS else {"start": 1.0, "end": 2.0}
        attrs = with_the_rest(timeline, kind, times)
        with Serve(Get.MEDIA_DURATION, length):
            component, reason = timeline.create_component(kind, **attrs)
        assert component is not None
        assert reason is None

    @pytest.mark.parametrize("kind", FIXTURES, ids=short)
    def test_a_media_length_that_cant_be_shown_is_shown_as_it_is(
        self, request, tilia_state, kind
    ):
        # As the core shows it: the same text.
        length = -TOO_LARGE
        timeline = request.getfixturevalue(FIXTURES[kind])
        times = {"time": 1.0} if kind in POINTS else {"start": 1.0, "end": 2.0}
        attrs = with_the_rest(timeline, kind, times)
        with Serve(Get.MEDIA_DURATION, length):
            component, reason = timeline.create_component(kind, **attrs)
        assert component is None
        if kind == HIERARCHY:
            core = rules.hierarchy(length, [], attrs)
        elif kind == RANGE:
            rows = [{"id": row.id, "name": row.name} for row in timeline.rows]
            core = rules.range_(length, [], attrs, rows=rows)
        else:
            core = rules.marker(length, [], {"time": 1.0})
            assert core.reason.startswith("Marker ")
            assert reason == core.reason.replace("Marker", POINTS[kind][1], 1)
            return
        assert reason == core.reason


# What each kind's CSV, by time, holds besides the row with the wrong time: its
# header, the rows before and after, and the row, with the time as `{}`.
HARMONY_HEADER = "time,harmony_or_key,symbol"
CSVS = {
    "marker": ("time,label", ["1,a"], "{},b", ["3,c"], "Marker time"),
    "beat": ("time", ["1", "3"], "{}", [], "Beat time"),
    "harmony": (
        HARMONY_HEADER,
        ["1,harmony,D"],
        "{},harmony,D",
        ["3,harmony,D"],
        "Harmony time",
    ),
    "harmony, a key": (
        HARMONY_HEADER,
        ["1,key,C"],
        "{},key,G",
        ["3,key,D"],
        "Mode time",
    ),
    "pdf": ("time,page_number", ["1,1"], "{},1", ["3,1"], "PDF page marker time"),
    "hierarchy": (
        "start,end,level",
        ["0,1,1"],
        "1,{},1",
        ["3,4,1"],
        "Hierarchy end",
    ),
    "hierarchy, its start": (
        "start,end,level",
        ["0,1,1"],
        "{0},{0},1",
        ["3,4,1"],
        "Hierarchy start",
    ),
    "range": ("start,end,row", ["0,1,A"], "1,{},A", ["3,4,A"], "Range end"),
}
PAST_THE_END = " 'inf' is bigger than media time '01:40.0'"
# Rows whose time is minus infinity, by kind: a beat's is refused as out of order.
MINUS_INF = {
    "marker": "Marker time can't be negative. Got '-inf'",
    "harmony": "Harmony time can't be negative. Got '-inf'",
    "harmony, a key": "Mode time can't be negative. Got '-inf'",
    "pdf": "PDF page marker time can't be negative. Got '-inf'",
    "hierarchy": "Hierarchy end '-inf' should be bigger than start '00:01.0'",
    "range": "Range end '-inf' should be bigger than start '00:01.0'",
}


def import_by_time(request, tmp_path, case: str, value: str):
    """Runs the import command on a CSV whose middle row has `value` for its time,
    over a timeline that holds a component; the timeline, and what it reported."""
    name = case.partition(",")[0]
    header, before, row, after, _ = CSVS[case]
    timeline = request.getfixturevalue(f"{name}_tlui").timeline
    path = tmp_path / "components.csv"
    path.write_text("\n".join([header, *before, row.format(value), *after]))
    reported: list[str] = []
    post(Post.APP_STATE_RECORD, "before the import")
    with (
        Serve(Get.FROM_USER_YES_OR_NO, True),
        patch(
            "tilia.ui.timelines.collection.import_."
            "_get_by_time_or_by_measure_from_user",
            return_value=(True, "time"),
        ),
        patch_file_dialog(True, [str(path)]),
        patch(
            "tilia.errors.display",
            side_effect=lambda _, message: reported.extend(message.split("\n")),
        ),
    ):
        assert commands.execute(f"timelines.import.{name}")
    return timeline, reported


class TestImport:
    @pytest.mark.parametrize("value", ["inf", "Infinity", "1e999"])
    @pytest.mark.parametrize("case", CSVS)
    def test_the_row_is_reported_and_the_others_are_imported(
        self, request, qtui, tilia_state, tmp_path, case, value
    ):
        timeline, reported = import_by_time(request, tmp_path, case, value)
        assert reported == [CSVS[case][-1] + PAST_THE_END]
        assert len(timeline) == 2

    @pytest.mark.parametrize("case", MINUS_INF)
    def test_minus_infinity(self, request, qtui, tilia_state, tmp_path, case):
        timeline, reported = import_by_time(request, tmp_path, case, "-inf")
        assert reported == [MINUS_INF[case]]
        assert len(timeline) == 2

    @pytest.mark.parametrize("value", ["-inf", "inf"])
    def test_a_range_s_start(self, request, qtui, tilia_state, tmp_path, value):
        text = {
            "-inf": "Range start can't be negative. Got '-inf'",
            "inf": "Range end '00:50.0' should be bigger than start 'inf'",
        }[value]
        with patch.dict(
            CSVS,
            {
                "range": (
                    "start,end,row",
                    ["0,1,A"],
                    "{},50,A",
                    ["3,4,A"],
                    "Range start",
                )
            },
        ):
            timeline, reported = import_by_time(request, tmp_path, "range", value)
        assert reported == [text]
        assert len(timeline) == 2


class TestEdit:
    """An edit takes plus infinity today, since it asks only that a time isn't
    before 0. What matters here is what an operation that makes a component out of
    such a one does."""

    @pytest.mark.parametrize("kind", FIXTURES, ids=short)
    def test_setting_a_time_raises_nothing(self, request, tilia_state, kind):
        timeline = request.getfixturevalue(FIXTURES[kind])
        times = {"time": 1.0} if kind in POINTS else {"start": 1.0, "end": 2.0}
        attrs = with_the_rest(timeline, kind, times)
        component, _ = timeline.create_component(kind, **attrs)
        for attr in times:
            assert component.set_data(attr, -INF) == (None, False)
        last = list(times)[-1]
        assert component.set_data(last, INF) == (INF, True)

    def endless(self, hierarchy_tl, level: int):
        hierarchy, _ = hierarchy_tl.create_component(HIERARCHY, 1.0, 2.0, level)
        hierarchy.set_data("end", INF)
        return hierarchy

    def test_the_child_of_a_hierarchy_without_an_end(self, hierarchy_tl, tilia_state):
        hierarchy = self.endless(hierarchy_tl, 2)
        success, _ = hierarchy_tl.component_manager.create_child(hierarchy)
        assert not success
        assert list(hierarchy_tl) == [hierarchy]

    def test_a_split_of_a_hierarchy_without_an_end(self, hierarchy_tl, tilia_state):
        hierarchy = self.endless(hierarchy_tl, 1)
        assert hierarchy_tl.component_manager.split(hierarchy, 1.5) == (
            False,
            "Hierarchy end 'inf' is bigger than media time '01:40.0'",
        )


class TestShownTime:
    @pytest.mark.parametrize("time", [0, 0.0, 1, 59.94, 150.0, 7265.5, -1.0])
    def test_a_finite_one_is_a_media_time(self, time):
        assert shown_time(time) == format_media_time(time)

    @pytest.mark.parametrize(
        "time, shown",
        [
            (INF, "inf"),
            (-INF, "-inf"),
            (math.nan, "nan"),
            (TOO_LARGE, str(TOO_LARGE)),
            (-TOO_LARGE, str(-TOO_LARGE)),
        ],
        ids=short,
    )
    def test_another_is_shown_as_the_core_shows_it(self, time, shown):
        assert shown_time(time) == shown
        # A media length is what the core's texts can show such a number of.
        assert rules.media_length(time).reason == (
            f"{shown} is not a valid media length."
        )
