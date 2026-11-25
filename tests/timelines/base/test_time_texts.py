"""TiLiA's own checks of a component's times give the core's texts: each names the
component's kind, as TiLiA names it, and which of its times is wrong, and gives the
times as media times, as the core shows them (WP16's `contracts/rules.md`, *A
component's times*; TimeLineAnnotator/project-management#610 and #679)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia_core import rules

LENGTH = 100.0  # the tests' media length: 01:40.0

# Each kind TiLiA checks the times of, which the core has rules for: its timeline's
# fixture, the core's kind, and its name in the texts.
POINTS = {
    ComponentKind.MARKER: ("marker_tl", "marker", "Marker"),
    ComponentKind.BEAT: ("beat_tl", "beat", "Beat"),
    ComponentKind.HARMONY: ("harmony_tl", "harmony", "Harmony"),
    ComponentKind.MODE: ("harmony_tl", "mode", "Mode"),
    ComponentKind.PDF_MARKER: ("pdf_tl", "pdf_marker", "PDF page marker"),
}
SEGMENTS = {
    ComponentKind.HIERARCHY: ("hierarchy_tl", "hierarchy", "Hierarchy"),
    ComponentKind.RANGE: ("range_tl", "range", "Range"),
}
HIERARCHY, RANGE = SEGMENTS
KINDS = {**POINTS, **SEGMENTS}

# Each of the rules TiLiA's own checks have, as (kinds, attributes, text after the
# kind's name). Only TiLiA's rules: it checks neither a hierarchy's start before 0
# nor its pre-start and post-end, nor a range's pre-start after its start or post-end
# before its end.
TEXTS = [
    (POINTS, {"time": -1.0}, "time can't be negative. Got '-00:01.0'"),
    (POINTS, {"time": 150.0}, "time '02:30.0' is bigger than media time '01:40.0'"),
    (
        [HIERARCHY],
        {"start": 150.0, "end": 160.0},
        "start '02:30.0' is bigger than media time '01:40.0'",
    ),
    (
        SEGMENTS,
        {"start": 1.0, "end": 150.0},
        "end '02:30.0' is bigger than media time '01:40.0'",
    ),
    (
        SEGMENTS,
        {"start": 2.0, "end": 1.0},
        "end '00:01.0' should be bigger than start '00:02.0'",
    ),
    (
        SEGMENTS,
        {"start": 2.0, "end": 2.0},
        "end '00:02.0' should be bigger than start '00:02.0'",
    ),
    ([RANGE], {"start": -1.0, "end": 2.0}, "start can't be negative. Got '-00:01.0'"),
    (
        [RANGE],
        {"start": 1.0, "end": 2.0, "pre_start": -1.0},
        "pre-start can't be negative. Got '-00:01.0'",
    ),
    (
        [RANGE],
        {"start": 1.0, "end": 2.0, "post_end": 150.0},
        "post-end '02:30.0' is bigger than media time '01:40.0'",
    ),
    # A time just under a minute is rounded before its minutes are counted.
    (POINTS, {"time": 119.97}, "time '02:00.0' is bigger than media time '01:40.0'"),
    (
        SEGMENTS,
        {"start": 1.0, "end": 119.97},
        "end '02:00.0' is bigger than media time '01:40.0'",
    ),
    # As many digits as tell two times apart (#679).
    (POINTS, {"time": 100.04}, "time '01:40.04' is bigger than media time '01:40.00'"),
    (
        POINTS,
        {"time": 100.0000001},
        "time '01:40.0000001' is bigger than media time '01:40.0000000'",
    ),
    (
        [HIERARCHY],
        {"start": 100.01, "end": 101.0},
        "start '01:40.01' is bigger than media time '01:40.00'",
    ),
    (
        SEGMENTS,
        {"start": 1.0, "end": 100.04},
        "end '01:40.04' is bigger than media time '01:40.00'",
    ),
    (
        SEGMENTS,
        {"start": 60.0, "end": 59.96},
        "end '00:59.96' should be bigger than start '01:00.00'",
    ),
    (
        SEGMENTS,
        {"start": 2.0, "end": math.nextafter(2.0, 0)},
        "end '00:01.9999999999999998' should be bigger than start"
        " '00:02.0000000000000000'",
    ),
    (
        [RANGE],
        {"start": 1.0, "end": 2.0, "post_end": 100.01},
        "post-end '01:40.01' is bigger than media time '01:40.00'",
    ),
    # And a time just before 0 doesn't read as zero (#679).
    (POINTS, {"time": -0.04}, "time can't be negative. Got '-00:00.04'"),
    ([RANGE], {"start": -0.04, "end": 2.0}, "start can't be negative. Got '-00:00.04'"),
    (
        [RANGE],
        {"start": 1.0, "end": 2.0, "pre_start": -0.004},
        "pre-start can't be negative. Got '-00:00.004'",
    ),
]
CASES = [(kind, attrs, text) for kinds, attrs, text in TEXTS for kind in kinds]


def case_id(case) -> str:
    kind, attrs, _ = case
    return f"{kind.name.lower()}-" + "-".join(f"{k}={v}" for k, v in attrs.items())


def refused(request, kind: ComponentKind, attrs: dict[str, Any]) -> tuple[str, list]:
    """What TiLiA's checks say when a component of `kind` is created with `attrs`,
    and the rows of its timeline, for a range."""
    timeline = request.getfixturevalue(KINDS[kind][0])
    rows = []
    if kind == HIERARCHY:
        attrs = {"level": 1, **attrs}
    elif kind == RANGE:
        rows = [{"id": row.id, "name": row.name} for row in timeline.rows]
        attrs = {"row_id": rows[0]["id"], **attrs}
    component, reason = timeline.create_component(kind, **attrs)
    assert component is None
    return reason, rows


def the_core_s(kind: ComponentKind, attrs: dict[str, Any], rows: list) -> str:
    """The core's reason for a component of `kind` with `attrs`."""
    core_kind = KINDS[kind][1]
    if core_kind == "hierarchy":
        attrs = {"level": 1, **attrs}
    if core_kind == "range":
        attrs = {"row_id": rows[0]["id"], **attrs}
        return rules.range_(LENGTH, [], attrs, rows=rows).reason
    if core_kind == "pdf_marker":
        return rules.pdf_marker(LENGTH, [], attrs, page_count=1).reason
    return getattr(rules, core_kind)(LENGTH, [], attrs).reason


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_the_text_names_the_kind_and_the_time(request, tilia_state, case):
    kind, attrs, text = case
    assert tilia_state.duration == LENGTH
    reason, _ = refused(request, kind, attrs)
    assert reason == f"{KINDS[kind][2]} {text}"


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_the_text_is_the_core_s(request, tilia_state, case):
    kind, attrs, _ = case
    reason, rows = refused(request, kind, attrs)
    assert reason == the_core_s(kind, attrs, rows)
