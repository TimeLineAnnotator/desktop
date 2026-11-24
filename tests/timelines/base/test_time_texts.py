"""TiLiA's own checks of a component's times give the core's texts: each names the
component's kind, as TiLiA names it, and which of its times is wrong, and gives
the times as media times (WP16's `contracts/rules.md`, *A component's times*;
TimeLineAnnotator/project-management#610)."""

from __future__ import annotations

from typing import Any

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.format import format_media_time
from tilia_core import rules

LENGTH = 100.0  # the tests' media length: 01:40.0

# Each kind TiLiA checks the times of: its timeline's fixture, and the core's kind.
POINTS = {
    ComponentKind.MARKER: ("marker_tl", "marker"),
    ComponentKind.BEAT: ("beat_tl", "beat"),
    ComponentKind.HARMONY: ("harmony_tl", "harmony"),
    ComponentKind.MODE: ("harmony_tl", "mode"),
    ComponentKind.PDF_MARKER: ("pdf_tl", "pdf_marker"),
}
SEGMENTS = {
    ComponentKind.HIERARCHY: ("hierarchy_tl", "hierarchy"),
    ComponentKind.RANGE: ("range_tl", "range"),
}
SHOWN = {
    ComponentKind.MARKER: "Marker",
    ComponentKind.BEAT: "Beat",
    ComponentKind.HARMONY: "Harmony",
    ComponentKind.MODE: "Mode",
    ComponentKind.PDF_MARKER: "PDF page marker",
    ComponentKind.HIERARCHY: "Hierarchy",
    ComponentKind.RANGE: "Range",
}

# Each of the rules TiLiA's own checks have, as (kind, attributes, text), with
# the times in the text as `{name}`, for `format_media_time` to show. Only TiLiA's
# rules: it checks neither a hierarchy's start before 0 nor its pre-start and
# post-end, nor a range's pre-start after its start or post-end before its end.
CASES = [
    *(
        (kind, {"time": -1.0}, "{kind} time can't be negative. Got '{time}'")
        for kind in POINTS
    ),
    *(
        (
            kind,
            {"time": 150.0},
            "{kind} time '{time}' is bigger than media time '{length}'",
        )
        for kind in POINTS
    ),
    (
        ComponentKind.HIERARCHY,
        {"start": 150.0, "end": 160.0},
        "{kind} start '{start}' is bigger than media time '{length}'",
    ),
    *(
        (
            kind,
            {"start": 1.0, "end": 150.0},
            "{kind} end '{end}' is bigger than media time '{length}'",
        )
        for kind in SEGMENTS
    ),
    *(
        (
            kind,
            {"start": 2.0, "end": end},
            "{kind} end '{end}' should be bigger than start '{start}'",
        )
        for kind in SEGMENTS
        for end in (1.0, 2.0)
    ),
    (
        ComponentKind.RANGE,
        {"start": -1.0, "end": 2.0},
        "{kind} start can't be negative. Got '{start}'",
    ),
    (
        ComponentKind.RANGE,
        {"start": 1.0, "end": 2.0, "pre_start": -1.0},
        "{kind} pre-start can't be negative. Got '{pre_start}'",
    ),
    (
        ComponentKind.RANGE,
        {"start": 1.0, "end": 2.0, "post_end": 150.0},
        "{kind} post-end '{post_end}' is bigger than media time '{length}'",
    ),
]


def case_id(case) -> str:
    kind, attrs, _ = case
    return f"{kind.name.lower()}-" + "-".join(f"{k}={v}" for k, v in attrs.items())


def refused(request, kind: ComponentKind, attrs: dict[str, Any]) -> str:
    """What TiLiA's checks say when a component of `kind` is created with `attrs`."""
    fixture, _ = {**POINTS, **SEGMENTS}[kind]
    timeline = request.getfixturevalue(fixture)
    if kind == ComponentKind.HIERARCHY:
        attrs = {"level": 1, **attrs}
    elif kind == ComponentKind.RANGE:
        attrs = {"row_id": timeline.rows[0].id, **attrs}
    component, reason = timeline.create_component(kind, **attrs)
    assert component is None
    return reason


def the_core_s(kind: ComponentKind, attrs: dict[str, Any], rows) -> str:
    """The core's reason for a component of `kind` with `attrs`."""
    _, core_kind = {**POINTS, **SEGMENTS}[kind]
    if core_kind == "hierarchy":
        attrs = {"level": 1, **attrs}
    if core_kind == "range":
        attrs = {"row_id": rows[0]["id"], **attrs}
        return rules.range_(LENGTH, [], attrs, rows=rows).reason
    if core_kind == "pdf_marker":
        return rules.pdf_marker(LENGTH, [], attrs, page_count=1).reason
    return getattr(rules, core_kind)(LENGTH, [], attrs).reason


def both(request, case) -> tuple[str, str]:
    """TiLiA's text for a case, and the core's."""
    kind, attrs = case
    reason = refused(request, kind, attrs)
    rows = []
    if kind == ComponentKind.RANGE:
        timeline = request.getfixturevalue("range_tl")
        rows = [{"id": row.id, "name": row.name} for row in timeline.rows]
    return reason, the_core_s(kind, attrs, rows)


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_the_text_names_the_kind_and_the_time(request, tilia_state, case):
    kind, attrs, text = case
    times = {name: format_media_time(value) for name, value in attrs.items()}
    expected = text.format(kind=SHOWN[kind], length=format_media_time(LENGTH), **times)
    assert tilia_state.duration == LENGTH
    assert refused(request, kind, attrs) == expected


# A time before 0 is shown with a minus sign in the core, and in TiLiA once dev's
# fix for TimeLineAnnotator/project-management#289 reaches this branch.
BEFORE_0 = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="TiLiA's format_media_time shows a time before 0 without its minus sign"
    " until dev's fix for TimeLineAnnotator/project-management#289 is merged",
)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, marks=BEFORE_0 if min(case[1].values()) < 0 else ())
        for case in CASES
    ],
    ids=case_id,
)
def test_the_text_is_the_core_s(request, tilia_state, case):
    kind, attrs, _ = case
    reason, core = both(request, (kind, attrs))
    assert reason == core


# A time just under a minute is rounded before its minutes are counted in the core.
JUST_UNDER_A_MINUTE = [
    *((kind, {"time": 119.97}) for kind in POINTS),
    *((kind, {"start": 1.0, "end": 119.97}) for kind in SEGMENTS),
    *((kind, {"start": 60.0, "end": 59.96}) for kind in SEGMENTS),
]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="TiLiA's format_media_time shows a time just under a minute as 01:60.0"
    " until TimeLineAnnotator/project-management#304 is built",
)
@pytest.mark.parametrize("case", JUST_UNDER_A_MINUTE, ids=lambda c: case_id((*c, "")))
def test_a_time_just_under_a_minute_is_the_core_s(request, tilia_state, case):
    reason, core = both(request, case)
    assert reason == core


@pytest.mark.parametrize("case", JUST_UNDER_A_MINUTE, ids=lambda c: case_id((*c, "")))
def test_a_time_just_under_a_minute_is_their_only_difference(
    request, tilia_state, case
):
    reason, core = both(request, case)
    for tilia_s, core_s in {"01:60.0": "02:00.0", "00:60.0": "01:00.0"}.items():
        reason = reason.replace(tilia_s, core_s)
    assert reason == core
