"""The check at the end of each action: the core's rules, on what it leaves.

An action is refused when it leaves a component it changed or added breaking one of
the core's rules, unless it fixes one of that component's problems and adds none, or
when it breaks a rule of a component it didn't change (FR-062, FR-070, FR-071). A
refused action leaves the timelines as they were and records nothing, and TiLiA says
why in the core's words (FR-073; `contracts/controls.md`, row 12). The reasons are
taken from the core here, since TiLiA shows them as the core gives them.

The files that break a rule are laid out by the core (`tla.canonical_bytes`), since
neither TiLiA nor the core's `write` makes one.
"""

from __future__ import annotations

import math
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pypdf
import pytest

import tilia.errors
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tests.ui.timelines.interact import drag_mouse_in_timeline_view
from tests.ui.timelines.range.interact import click_range_ui
from tilia.file import tla_bridge
from tilia.requests import Get, Post, get, post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.edit_gate import EditGate
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.undo_manager import PauseUndoManager
from tilia_core import rules, tla

LENGTH = 100.0
REFUSED = tilia.errors.EDIT_REFUSED.title


def make_id(number: int) -> str:
    return f"019b76da-f000-7000-8000-{number:012d}"


FORM, TEXTURE, EDITION = make_id(1), make_id(2), make_id(3)
A, B, C, D = make_id(11), make_id(12), make_id(13), make_id(14)
ROW = {"id": "aZ3k9P", "name": "Melody"}
EXAMPLE_PDF = Path(EXAMPLE_MEDIA_PATH).with_name("example.pdf")


# Files, as the core lays them out


def a_file(tmp_path: Path, *timelines: tla.Timeline, length=LENGTH) -> Path:
    """A file holding `timelines`, which may break the rules: the core's `write`
    would refuse them, so it is laid out as the core lays out a file."""
    document = tla.new_document()
    document.media_length = length
    for ordinal, timeline in enumerate(timelines, start=1):
        timeline.ordinal = ordinal
        document.timelines[timeline.id] = timeline
    path = tmp_path / "file.tla"
    path.write_bytes(tla.canonical_bytes(document))
    return path


def hierarchies(*components: tuple[str, dict]) -> tla.Timeline:
    return tla.Timeline(
        id=FORM,
        kind="hierarchy",
        ordinal=1,
        name="Form",
        attrs={"height": 60},
        components={
            id: tla.Component(id=id, kind="hierarchy", attrs=attrs)
            for id, attrs in components
        },
    )


def ranges(*components: tuple[str, dict]) -> tla.Timeline:
    return tla.Timeline(
        id=TEXTURE,
        kind="range",
        ordinal=1,
        name="Texture",
        attrs={"height": 60, "rows": [dict(ROW)]},
        components={
            id: tla.Component(id=id, kind="range", attrs={"row_id": ROW["id"], **attrs})
            for id, attrs in components
        },
    )


def open_file(path: Path) -> None:
    """Opens `path` as the File menu does, closing the warnings it opens with."""
    with (
        Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_SHOW_PROBLEMS, None),
    ):
        assert commands.execute("file.open", path)


def save() -> bool:
    return commands.execute("file.save")


def as_if_allowed(tilia, *component_ids: str) -> None:
    """What an action the check allows does: the document follows it, and the core
    keeps the problems its components came with."""
    file = tilia.file_manager.file
    file.sync(get(Get.APP_STATE))
    file.keep_read_problems(component_ids)


def record() -> None:
    """Ends an action made through the timelines, as each of TiLiA's actions ends."""
    post(Post.APP_STATE_RECORD, "test")


# What the core says


def components_of(kind: str, **components: dict) -> list[tla.Component]:
    return [
        tla.Component(id=id, kind=kind, attrs=attrs) for id, attrs in components.items()
    ]


def the_core_s_reason(
    of: str,
    components: list[tla.Component],
    *,
    rows=None,
    length=LENGTH,
    code: str | None = None,
    about: str = "",
) -> str:
    """The first rule the core finds broken by the component `of`, checked with the
    others, as the gate checks a timeline; or the one of `code`, about `about`."""
    checked = rules.check_timeline(
        length, components, rows=rows, page_count=math.inf, every_rule=True
    )[of]
    broken = [
        outcome
        for outcome in (checked.outcome, *checked.also)
        if not outcome
        and (code is None or (outcome.code, outcome.about) == (code, about))
    ]
    assert broken, f"{of} breaks no such rule"
    return broken[0].reason


def a_hierarchy(start, end, level, **attrs) -> dict:
    return {"start": start, "end": end, "level": level, **attrs}


def crossing() -> str:
    """The core's reason for two hierarchies that cross."""
    return the_core_s_reason(
        "b",
        components_of("hierarchy", a=a_hierarchy(0, 10, 1), b=a_hierarchy(5, 15, 1)),
    )


# What TiLiA shows


def timelines_now() -> dict:
    return get(Get.APP_STATE)["timelines"]


def refusals(tilia_errors) -> list[str]:
    return [
        error["message"] for error in tilia_errors.errors if error["title"] == REFUSED
    ]


class Refused:
    """Asserts that what is done inside is refused with `reason`, and leaves the
    timelines and the undo history as they were."""

    def __init__(self, tilia, tilia_errors, reason: str | None = None):
        self.tilia, self.errors, self.reason = tilia, tilia_errors, reason

    def __enter__(self):
        self.before = timelines_now()
        self.undo = list(self.tilia.undo_manager.stack)
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is not None:
            return False
        found = refusals(self.errors)
        assert found, "not refused"
        if self.reason is not None:
            assert found == [self.reason]
        assert timelines_now() == self.before
        assert self.tilia.undo_manager.stack == self.undo
        return False


def assert_not_refused(tilia_errors) -> None:
    assert refusals(tilia_errors) == []


@pytest.fixture
def open_hierarchies(qtui, tilia, tls, tmp_path):
    def _open(*components: tuple[str, dict]) -> Path:
        path = a_file(tmp_path, hierarchies(*components))
        open_file(path)
        return path

    return _open


def element(tluis, timeline_id: str, component_id: str):
    return tluis.get_timeline_ui(timeline_id).get_element(component_id)


def select(tluis, timeline_id: str, component_id: str) -> None:
    timeline_ui = tluis.get_timeline_ui(timeline_id)
    timeline_ui.deselect_all_elements()
    timeline_ui.select_element(timeline_ui.get_element(component_id))


def edit_label(tluis, timeline_id: str, component_id: str, label: str) -> None:
    """Types a label in the inspector, as the inspector posts it."""
    select(tluis, timeline_id, component_id)
    post(Post.INSPECTOR_FIELD_EDITED, "Label", label, component_id, 0)


class TestTheMessage:
    def test_is_row_12_s_with_the_rule_s_reason(
        self, tilia, hierarchy_tlui, tilia_errors
    ):
        commands.execute("timeline.hierarchy.add", start=10, end=20, level=0)

        # `contracts/controls.md`, row 12, word for word.
        assert tilia_errors.errors[-1] == {
            "title": "Can't make this change",
            "message": the_core_s_reason(
                "new", components_of("hierarchy", new=a_hierarchy(10, 20, 0))
            ),
        }


class TestEachRuleAUserCanReach:
    """Each of `rules.md`'s rows a person can break through TiLiA, past the checks
    TiLiA still makes of its own: the action is refused with the rule's reason, and
    the state is as it was."""

    @pytest.mark.parametrize(
        "attrs",
        [
            pytest.param(a_hierarchy(10, 20, 0), id="a level below 1"),
            pytest.param(a_hierarchy(-1, 20, 1), id="a start before 0"),
            pytest.param(
                a_hierarchy(10, 20, 1, pre_start=-1), id="a pre-start before 0"
            ),
            pytest.param(
                a_hierarchy(10, 20, 1, post_end=120), id="a post-end past the end"
            ),
            pytest.param(
                a_hierarchy(10, 20, 1, post_end=15), id="a post-end before the end"
            ),
        ],
    )
    def test_a_hierarchy_s(self, tilia, hierarchy_tlui, tilia_errors, attrs):
        reason = the_core_s_reason("new", components_of("hierarchy", new=attrs))

        with Refused(tilia, tilia_errors, reason):
            commands.execute("timeline.hierarchy.add", **attrs)

    def test_a_hierarchy_crossing_another(self, tilia, hierarchy_tlui, tilia_errors):
        commands.execute("timeline.hierarchy.add", start=0, end=10, level=1)
        reason = the_core_s_reason(
            "new",
            components_of(
                "hierarchy", old=a_hierarchy(0, 10, 1), new=a_hierarchy(5, 15, 1)
            ),
        )

        with Refused(tilia, tilia_errors, reason):
            commands.execute("timeline.hierarchy.add", start=5, end=15, level=1)

    def test_a_time_that_isn_t_a_number(self, tilia, tls, cli, tilia_errors):
        cli.parse_and_run("timeline add beat --beat-pattern 4")
        reason = the_core_s_reason(
            "new", components_of("beat", new={"time": float("nan")})
        )

        with Refused(tilia, tilia_errors, reason):
            cli.parse_and_run("component beat --tl-ordinal 1 --time nan")

    def test_a_measure_number_below_0(self, tilia, tls, cli, tilia_errors, tmp_path):
        cli.parse_and_run("timeline add beat --beat-pattern 4")
        csv = tmp_path / "beats.csv"
        csv.write_text("time,measure\n0,-1\n1,\n2,\n3,\n4,\n", encoding="utf-8")
        reason = the_core_s_reason(
            "new", components_of("beat", new={"time": 0.0, "measure": {"number": -1}})
        )

        with Refused(tilia, tilia_errors, reason):
            cli.parse_and_run(
                f'timelines import beat --file "{csv.resolve()}" --target-ordinal 1'
            )

    def test_a_join_over_a_range_between(self, tilia, range_tlui, tilia_errors):
        for start, end in [(0, 10), (20, 30), (40, 50)]:
            commands.execute("timeline.range.add_range", start=start, end=end)
        first, between, last = range_tlui[0], range_tlui[1], range_tlui[2]
        rows = timelines_now()[range_tlui.id]["rows"]
        row_id = rows[0]["id"]
        # TiLiA's join fills the gap to the range joined, over the one between.
        reason = the_core_s_reason(
            first.id,
            components_of(
                "range",
                **{
                    first.id: {
                        "start": 0,
                        "end": 40,
                        "row_id": row_id,
                        "joined_right": last.id,
                    },
                    between.id: {"start": 20, "end": 30, "row_id": row_id},
                    last.id: {"start": 40, "end": 50, "row_id": row_id},
                },
            ),
            rows=rows,
        )
        click_range_ui(first)
        click_range_ui(last, modifier="ctrl")

        with Refused(tilia, tilia_errors, reason):
            commands.execute("timeline.range.join_ranges")


class TestCrossingHierarchies:
    """A hierarchy that crosses another is refused by every path that makes one
    (TimeLineAnnotator/project-management#295)."""

    def test_by_the_ui(self, tilia, hierarchy_tlui, tilia_errors):
        commands.execute("timeline.hierarchy.add", start=0, end=20, level=2)

        with Refused(tilia, tilia_errors, crossing()):
            commands.execute("timeline.hierarchy.add", start=10, end=30, level=1)

    def test_by_the_command_line(self, tilia, tls, cli, tilia_errors, tmp_path):
        cli.parse_and_run("timeline add hierarchy --name Form")
        csv = tmp_path / "hierarchies.csv"
        csv.write_text("start,end,level\n0,10,1\n5,15,1\n", encoding="utf-8")

        with Refused(tilia, tilia_errors, crossing()):
            cli.parse_and_run(
                "timelines import hierarchy by-time"
                f' --file "{csv.resolve()}" --target-ordinal 1'
            )

    def test_by_pasting_what_crosses(
        self, open_hierarchies, tilia, tluis, tilia_errors
    ):
        # A file whose two children of A cross: pasted into B, with their
        # children, they cross there too.
        open_hierarchies(
            (A, a_hierarchy(0, 10, 2)),
            (C, a_hierarchy(0, 6, 1)),
            (D, a_hierarchy(4, 10, 1)),
            (B, a_hierarchy(20, 30, 2)),
        )
        select(tluis, FORM, A)
        commands.execute("timeline.component.copy")
        select(tluis, FORM, B)

        with Refused(tilia, tilia_errors, crossing()):
            commands.execute("timeline.component.paste_complete")


class TestJoins:
    def test_a_range_dragged_between_two_joined_goes_back_on_release(
        self, tilia, range_tlui, tilia_errors
    ):
        # `rules.md`, decision 13: the drag breaks the join of a range it doesn't
        # move.
        for start, end in [(10, 20), (20, 30)]:
            commands.execute("timeline.range.add_range", start=start, end=end)
        first, second = range_tlui[0], range_tlui[1]
        range_tlui.select_element(first)
        range_tlui.select_element(second)
        commands.execute("timeline.range.join_ranges")
        commands.execute("timeline.range.add_range", start=60, end=70)
        moved = range_tlui.get_element(
            next(
                component.id
                for component in range_tlui.timeline
                if component.start == 60
            )
        )
        range_tlui.deselect_all_elements()
        before = timelines_now()
        click_range_ui(moved)
        drag_mouse_in_timeline_view(
            time_x_converter.get_x_by_time(65), 0, release=False
        )
        drag_mouse_in_timeline_view(
            time_x_converter.get_x_by_time(20), 0, release=False
        )
        dragged = timelines_now()[range_tlui.id]
        rows = dragged["rows"]
        reason = the_core_s_reason(
            first.id,
            [
                tla.Component(
                    id=id,
                    kind="range",
                    attrs={
                        key: component[key]
                        for key in ("start", "end", "row_id", "joined_right")
                    },
                )
                for id, component in dragged["components"].items()
            ],
            rows=rows,
        )

        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)

        assert refusals(tilia_errors) == [reason]
        assert timelines_now() == before

    def test_an_edit_to_the_range_a_bad_join_joins_is_refused(
        self, qtui, tilia, tls, tluis, tilia_errors, tmp_path
    ):
        # TimeLineAnnotator/project-management#496, point 2: the file joins A to C,
        # over B. The join is A's, and the writer refuses it once C changes, so
        # TiLiA does on the edit.
        joined = ranges(
            (A, {"start": 0, "end": 10, "joined_right": C}),
            (B, {"start": 5, "end": 8}),
            (C, {"start": 10, "end": 20}),
        )
        reason = the_core_s_reason(
            A, list(joined.components.values()), rows=joined.attrs["rows"]
        )
        open_file(a_file(tmp_path, joined))

        with Refused(tilia, tilia_errors, reason):
            edit_label(tluis, TEXTURE, C, "changed")

    def test_an_edit_to_a_range_it_passes_over_is_allowed(
        self, qtui, tilia, tls, tluis, tilia_errors, tmp_path
    ):
        path = a_file(
            tmp_path,
            ranges(
                (A, {"start": 0, "end": 10, "joined_right": C}),
                (B, {"start": 5, "end": 8}),
                (C, {"start": 10, "end": 20}),
            ),
        )
        open_file(path)

        edit_label(tluis, TEXTURE, B, "changed")

        assert_not_refused(tilia_errors)
        assert save()


class TestAFileWithTwoCrossingHierarchies:
    """User story 7, scenario 4: A holds B at its own level."""

    @pytest.fixture
    def crossing(self, open_hierarchies):
        return open_hierarchies((A, a_hierarchy(0, 20, 1)), (B, a_hierarchy(5, 15, 1)))

    def test_changing_a_label_is_refused(self, crossing, tilia, tluis, tilia_errors):
        reason = the_core_s_reason(
            A,
            components_of(
                "hierarchy", **{A: a_hierarchy(0, 20, 1), B: a_hierarchy(5, 15, 1)}
            ),
        )

        with Refused(tilia, tilia_errors, reason):
            edit_label(tluis, FORM, A, "changed")

    def test_changing_a_level_so_they_no_longer_cross_is_allowed(
        self, crossing, tluis, tilia_errors
    ):
        select(tluis, FORM, A)

        commands.execute("timeline.hierarchy.increase_level")

        assert_not_refused(tilia_errors)
        assert element(tluis, FORM, A).get_data("level") == 2
        assert save()

    def test_moving_an_end_so_they_no_longer_cross_is_allowed(
        self, crossing, tls, tilia_errors
    ):
        # TiLiA's drags can't take a boundary past another (FR-070), so the end
        # moves through the timeline.
        tls.get_timeline(FORM).set_component_data(A, "end", 5)
        record()

        assert_not_refused(tilia_errors)
        assert tls.get_timeline(FORM).get_component(A).end == 5
        assert save()

    @pytest.mark.parametrize("deleted", [A, B])
    def test_deleting_either_is_allowed(self, crossing, tluis, tilia_errors, deleted):
        select(tluis, FORM, deleted)

        commands.execute("timeline.component.delete")

        assert_not_refused(tilia_errors)
        assert deleted not in timelines_now()[FORM]["components"]
        assert save()


class TestAComponentFixedInPart:
    def test_is_allowed_and_saves(self, open_hierarchies, tluis, tilia_errors):
        # A has a level of 0 and crosses B: its level is fixed, the crossing stays.
        open_hierarchies((A, a_hierarchy(0, 20, 0)), (B, a_hierarchy(5, 15, 1)))
        select(tluis, FORM, A)

        commands.execute("timeline.hierarchy.increase_level")

        assert_not_refused(tilia_errors)
        assert element(tluis, FORM, A).get_data("level") == 1
        assert save()

    def test_then_changing_its_label_is_refused(
        self, open_hierarchies, tilia, tluis, tilia_errors
    ):
        open_hierarchies((A, a_hierarchy(0, 20, 0)), (B, a_hierarchy(5, 15, 1)))
        select(tluis, FORM, A)
        commands.execute("timeline.hierarchy.increase_level")

        with Refused(tilia, tilia_errors, crossing()):
            edit_label(tluis, FORM, A, "changed")

    def test_a_second_problem_of_a_code_it_came_with_is_refused_as_its_save_is(
        self, open_hierarchies, tilia, tls, tilia_errors
    ):
        # TimeLineAnnotator/project-management#557: read at a level of 0 and a start
        # of -1, the action fixes the level and gives it a pre-start of -5, which is
        # also before 0. TiLiA's own check of a time refuses -5 until it goes
        # (TimeLineAnnotator/project-management#460), so the pre-start is set on
        # the component.
        open_hierarchies((A, a_hierarchy(-1, 20, 0)))

        def edit():
            timeline = tls.get_timeline(FORM)
            timeline.set_component_data(A, "level", 1)
            timeline.get_component(A).pre_start = -5

        reason = the_core_s_reason(
            A,
            components_of("hierarchy", **{A: a_hierarchy(-1, 20, 1, pre_start=-5)}),
            code=rules.NEGATIVE_TIME,
            about="pre_start",
        )
        with Refused(tilia, tilia_errors, reason):
            edit()
            record()

        # Allowed, as if the check let it through, the save refuses it.
        edit()
        as_if_allowed(tilia, A)
        assert not save()

    def test_past_the_end_by_another_rule_is_refused_as_its_save_is(
        self, open_hierarchies, tilia, tls, tilia_errors
    ):
        # TimeLineAnnotator/project-management#557, past the media's end: read with
        # a post-end past it and a level of 0, the action fixes the level and moves
        # the end past it too.
        open_hierarchies((A, a_hierarchy(10, 90, 0, post_end=150)))

        def edit():
            tls.get_timeline(FORM).set_component_data(A, "level", 1)
            tls.get_timeline(FORM).set_component_data(A, "end", 120)

        reason = the_core_s_reason(
            A,
            components_of("hierarchy", **{A: a_hierarchy(10, 120, 1, post_end=150)}),
            code=rules.PAST_MEDIA_END,
            about="start end",
        )
        with Refused(tilia, tilia_errors, reason):
            edit()
            record()

        # Allowed, as if the check let it through, the save refuses it.
        edit()
        as_if_allowed(tilia, A)
        assert not save()

    def test_a_start_and_an_end_past_the_end_are_one_problem(
        self, open_hierarchies, tls, tilia_errors
    ):
        # Read past the media's end by its end, with a level of 0: the action
        # fixes the level and moves its start past the end too.
        open_hierarchies((A, a_hierarchy(90, 110, 0)))
        timeline = tls.get_timeline(FORM)

        timeline.set_component_data(A, "level", 1)
        timeline.set_component_data(A, "start", 105)
        record()

        assert_not_refused(tilia_errors)
        assert save()


class TestAnActionThatChangesTwoAtOdds:
    def test_is_refused_though_each_is_fixed_in_part_as_its_save_is(
        self, open_hierarchies, tilia, tls, tluis, tilia_errors
    ):
        # Both read at a level of 0, A holding B at its own level: both levels go
        # up, and the two still cross, now as neither was read. The core keeps a
        # problem between two components only with the others as they were.
        open_hierarchies((A, a_hierarchy(0, 20, 0)), (B, a_hierarchy(5, 15, 0)))
        timeline_ui = tluis.get_timeline_ui(FORM)
        timeline_ui.deselect_all_elements()
        for component_id in (A, B):
            timeline_ui.select_element(timeline_ui.get_element(component_id))

        with Refused(tilia, tilia_errors, crossing()):
            commands.execute("timeline.hierarchy.increase_level")

        for component_id in (A, B):
            tls.get_timeline(FORM).set_component_data(component_id, "level", 1)
        as_if_allowed(tilia, A, B)
        assert not save()


class TestARow:
    def test_is_checked_as_a_component_is(self, tilia, range_tlui, tilia_errors):
        # TiLiA's own check of a row's color, which the dialog makes, is passed by.
        commands.execute("timeline.range.add_row")
        row = range_tlui.timeline.rows[-1]
        reason = rules.color("notacolor").reason

        with Refused(tilia, tilia_errors, reason):
            row.color = "notacolor"
            record()


class TestAComponentsColor:
    """A hierarchy read with a color that isn't one, as a file may hold it."""

    @pytest.fixture
    def miscolored(self, open_hierarchies):
        return open_hierarchies((A, a_hierarchy(0, 20, 1, color="notacolor")))

    def test_is_one_of_its_problems(self, miscolored, tilia, tluis, tilia_errors):
        with Refused(tilia, tilia_errors, rules.color("notacolor").reason):
            edit_label(tluis, FORM, A, "changed")

    def test_reset_is_allowed_and_saves(self, miscolored, tluis, tilia_errors):
        select(tluis, FORM, A)

        commands.execute("timeline.component.reset_color")

        assert_not_refused(tilia_errors)
        assert save()


class TestAPdfMarkersPage:
    """The inspector offers no page past the PDF's end: the page is posted as the
    inspector would post it, were it to."""

    def a_pdf_file(self, tmp_path, *, found: bool) -> Path:
        if found:
            shutil.copy(EXAMPLE_PDF, tmp_path / "edition.pdf")
        return a_file(
            tmp_path,
            tla.Timeline(
                id=EDITION,
                kind="pdf",
                ordinal=1,
                name="Edition",
                attrs={"height": 30, "path": "edition.pdf"},
                components={
                    A: tla.Component(
                        id=A, kind="pdf_marker", attrs={"time": 0.0, "page_number": 1}
                    )
                },
            ),
        )

    def turn_to(self, tluis, page_number: int) -> None:
        select(tluis, EDITION, A)
        post(Post.INSPECTOR_FIELD_EDITED, "Page number", page_number, A, 0)

    def test_past_the_pdf_s_end_is_refused(
        self, qtui, tilia, tls, tluis, tilia_errors, tmp_path
    ):
        open_file(self.a_pdf_file(tmp_path, found=True))
        pages = len(pypdf.PdfReader(EXAMPLE_PDF).pages)
        reason = rules.pdf_marker(
            LENGTH, [], {"time": 0.0, "page_number": pages + 1}, page_count=pages
        ).reason

        with Refused(tilia, tilia_errors, reason):
            self.turn_to(tluis, pages + 1)

    def test_any_is_allowed_when_the_pdf_isn_t_found(
        self, qtui, tilia, tls, tluis, tilia_errors, tmp_path
    ):
        open_file(self.a_pdf_file(tmp_path, found=False))
        pages = len(pypdf.PdfReader(EXAMPLE_PDF).pages)

        self.turn_to(tluis, pages + 1)

        assert_not_refused(tilia_errors)
        assert element(tluis, EDITION, A).get_data("page_number") == pages + 1


class TestWhatTheNextActionIsComparedWith:
    """In a file with two crossing hierarchies, A and B, an edit of C is C's: the
    problems the file came with aren't the action's."""

    @pytest.fixture
    def crossing(self, open_hierarchies):
        return open_hierarchies(
            (A, a_hierarchy(0, 20, 1)),
            (B, a_hierarchy(5, 15, 1)),
            (C, a_hierarchy(40, 60, 1)),
        )

    def test_after_a_command_that_fails_is_the_state_before_it(
        self, crossing, tluis, tilia_errors
    ):
        select(tluis, FORM, C)
        with patch.object(HierarchyTimeline, "alter_levels", side_effect=RuntimeError):
            commands.execute("timeline.hierarchy.increase_level")

        edit_label(tluis, FORM, C, "changed")

        assert_not_refused(tilia_errors)

    def test_after_a_file_that_fails_to_load_is_the_file_open_before(
        self, crossing, tluis, tilia_errors, tmp_path
    ):
        other = tmp_path / "other"
        other.mkdir()
        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            patch.object(tla_bridge, "state_of", side_effect=RuntimeError),
        ):
            assert not commands.execute(
                "file.open", a_file(other, hierarchies((D, a_hierarchy(0, 10, 1))))
            )

        edit_label(tluis, FORM, C, "changed")

        assert_not_refused(tilia_errors)


class TestASaveAfterAnAcceptedEdit:
    @pytest.mark.parametrize(
        "edit",
        ["label", "level", "delete", "add"],
    )
    def test_isn_t_refused(self, open_hierarchies, tluis, tilia_errors, edit):
        # A file with a problem it came with, which no edit here fixes.
        open_hierarchies(
            (A, a_hierarchy(0, 20, 1)),
            (B, a_hierarchy(5, 15, 1)),
            (C, a_hierarchy(40, 60, 1)),
        )
        if edit == "label":
            edit_label(tluis, FORM, C, "changed")
        elif edit == "level":
            select(tluis, FORM, C)
            commands.execute("timeline.hierarchy.increase_level")
        elif edit == "delete":
            select(tluis, FORM, C)
            commands.execute("timeline.component.delete")
        else:
            commands.execute("timeline.hierarchy.add", start=70, end=80, level=1)

        assert_not_refused(tilia_errors)
        assert save()


class TestWhatIsntChecked:
    def test_undo_and_redo_and_the_state_accepted_follows_them(
        self, open_hierarchies, tilia, tluis, tilia_errors
    ):
        open_hierarchies((A, a_hierarchy(0, 20, 1)), (B, a_hierarchy(5, 15, 1)))
        select(tluis, FORM, A)
        commands.execute("timeline.hierarchy.increase_level")

        commands.execute("edit.undo")

        assert_not_refused(tilia_errors)
        assert element(tluis, FORM, A).get_data("level") == 1
        # A crosses B again, as it was read: its label can't change.
        with Refused(tilia, tilia_errors, crossing()):
            edit_label(tluis, FORM, A, "changed")

        commands.execute("edit.redo")
        edit_label(tluis, FORM, A, "changed")

        assert len(refusals(tilia_errors)) == 1
        assert element(tluis, FORM, A).get_data("label") == "changed"

    def test_a_section_that_pauses_undo_is_checked_when_the_action_ends(
        self, tilia, hierarchy_tlui, tls, tilia_errors
    ):
        commands.execute("timeline.hierarchy.add", start=0, end=10, level=1)
        timeline = hierarchy_tlui.timeline

        with PauseUndoManager():
            timeline.create_component(ComponentKind.HIERARCHY, start=5, end=15, level=1)
            record()
        assert_not_refused(tilia_errors)

        record()
        assert len(refusals(tilia_errors)) == 1
        assert len(timeline) == 1


class TestTheCommandLine:
    def test_an_accepted_command_records_nothing_and_is_the_next_one_s_baseline(
        self, tilia, tls, cli, tilia_errors, tmp_path
    ):
        def import_hierarchies(name: str, *rows: str) -> None:
            # An import replaces what the timeline holds.
            csv = tmp_path / name
            csv.write_text("".join(f"{row}\n" for row in ("start,end,level", *rows)))
            cli.parse_and_run(
                "timelines import hierarchy by-time"
                f' --file "{csv.resolve()}" --target-ordinal 1'
            )

        cli.parse_and_run("timeline add hierarchy --name Form")
        undo = list(tilia.undo_manager.stack)

        import_hierarchies("first.csv", "0,10,1")

        assert_not_refused(tilia_errors)
        assert tilia.undo_manager.stack == undo
        document = tilia.file_manager.file.document
        assert [len(tl.components) for tl in document.timelines.values()] == [1]
        with Refused(tilia, tilia_errors, crossing()):
            import_hierarchies("second.csv", "0,10,1", "5,15,1")


class TestTheMediaLength:
    def test_is_the_document_s(self, qtui, tilia, tls, tluis, tilia_errors, tmp_path):
        # The player reports a length a little off the stored one: the document
        # keeps its own (FR-034), and so do the rules.
        open_file(a_file(tmp_path, hierarchies((A, a_hierarchy(10, 100, 1)))))
        tilia.set_file_media_duration(99.5, "keep")

        edit_label(tluis, FORM, A, "changed")

        assert_not_refused(tilia_errors)

    @pytest.mark.parametrize(
        "length",
        [pytest.param(None, id="unknown"), pytest.param(-5.0, id="not a length")],
    )
    def test_unknown_or_not_one_compares_no_time(
        self, qtui, tilia, tls, tluis, tilia_errors, tmp_path, length
    ):
        # As the core's writer compares none with it (WP16's `rules.md`, the media
        # length's row).
        open_file(
            a_file(tmp_path, hierarchies((A, a_hierarchy(10, 500, 1))), length=length)
        )

        edit_label(tluis, FORM, A, "changed")

        assert_not_refused(tilia_errors)
        assert element(tluis, FORM, A).get_data("label") == "changed"

    @pytest.mark.parametrize("scale", ["yes", "no"])
    def test_a_scale_or_a_crop_leaves_a_file_that_writes(
        self, qtui, tilia, tls, tilia_state, tilia_errors, tmp_path, scale
    ):
        # FR-034, TimeLineAnnotator/project-management#496 point 1: nothing is left past a shorter media's end.
        open_file(
            a_file(
                tmp_path,
                hierarchies(
                    (A, a_hierarchy(0, 40, 1)),
                    (B, a_hierarchy(40, 100, 1, post_end=100)),
                ),
            )
        )

        tilia_state.set_duration(50, scale_timelines=scale)
        record()

        assert_not_refused(tilia_errors)
        assert save()


class TestAScaleOrACropAnsweredAsAFileOpens:
    """The media reports another length once the file is open, and the person
    answers to scale or to crop: the components it moves keep the problems they
    came with, as ones they came with."""

    @pytest.mark.parametrize(
        "scale, length", [pytest.param("yes", 80, id="scaled"), ("no", 10)]
    )
    def test_keeps_a_component_s_own_problems_and_the_file_saves(
        self, open_hierarchies, tilia, tls, tilia_errors, scale, length
    ):
        # A has a level of 0. A crop to 10 s cuts it, and takes C out.
        open_hierarchies((A, a_hierarchy(0, 20, 0)), (C, a_hierarchy(40, 60, 1)))

        tilia.set_file_media_duration(length, scale)

        assert (
            tls.get_timeline(FORM).get_component(A).end == {"yes": 16, "no": 10}[scale]
        )
        assert_not_refused(tilia_errors)
        assert save()

    def test_an_edit_after_it_is_checked_against_it(
        self, open_hierarchies, tilia, tluis, tilia_errors
    ):
        # A has a level of 0, which the scale doesn't fix: an edit of C is C's.
        open_hierarchies((A, a_hierarchy(0, 20, 0)), (C, a_hierarchy(40, 60, 1)))
        tilia.set_file_media_duration(80, "yes")

        edit_label(tluis, FORM, C, "changed")

        assert_not_refused(tilia_errors)
        assert save()

    @pytest.mark.xfail(
        strict=True,
        reason="the core keeps a problem between two components only with the"
        " other as it was read, until TimeLineAnnotator/project-management#647",
    )
    def test_keeps_a_problem_between_two_it_moves_and_the_file_saves(
        self, open_hierarchies, tilia, tluis, tilia_errors
    ):
        open_hierarchies((A, a_hierarchy(0, 20, 1)), (B, a_hierarchy(5, 15, 1)))

        tilia.set_file_media_duration(80, "yes")

        assert_not_refused(tilia_errors)
        assert save()


class TestSpeed:
    def test_one_label_edit_of_3000_hierarchies_is_checked_well_under_a_second(
        self, tilia, tls
    ):
        # Without the UI: 2,000 units at level 1, in 1,000 at level 2.
        timeline = tls.create_timeline(HierarchyTimeline)
        timeline.clear()
        for index in range(1000):
            start = index * 3.0
            for child in range(2):
                timeline.create_component(
                    ComponentKind.HIERARCHY,
                    start=start + child * 1.5,
                    end=start + (child + 1) * 1.5,
                    level=1,
                    checked=False,
                )
            timeline.create_component(
                ComponentKind.HIERARCHY,
                start=start,
                end=start + 3.0,
                level=2,
                checked=False,
            )
        before = tilia.get_app_state()
        timeline.set_component_data(timeline[0].id, "label", "changed")
        after = tilia.get_app_state()

        def timed() -> float:
            # A new gate each time, which knows neither state yet.
            gate = EditGate()
            gate.accepted = before
            began = time.perf_counter()
            verdict = gate.check(after, media_length=3000.0, page_counts={})
            took = time.perf_counter() - began
            assert verdict.reason is None
            return took

        # The best of three, so that another program's load doesn't count.
        assert min(timed() for _ in range(3)) < 0.5
