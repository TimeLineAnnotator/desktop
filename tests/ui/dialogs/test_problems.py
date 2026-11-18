"""The warnings a file opens with, in one dialog (FR-061; contracts/messages.md,
row 4): the file's name and how many there are, then one line each, in TiLiA's
terms, with a button that copies them. A file with none shows no dialog.

The files that break a rule are WP3's valid file with one thing changed, made with
WP3's own `make_broken.py`, as its tests make them.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from tests.mock import Serve
from tests.utils import get_blank_file_data
from tilia.requests import Get, serve, server, stop_serving
from tilia.ui import commands
from tilia.ui.dialogs.problems import ProblemsDialog

FILES = Path(__file__).parents[3] / "packages" / "tilia-core" / "tests" / "tla"
MESSAGE = (
    "'{name}' has {n} problems. TiLiA keeps them as they are, and saves them"
    " unchanged until you fix them."
)


def _load_make_broken():
    spec = importlib.util.spec_from_file_location(
        "make_broken", FILES / "broken" / "make_broken.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_broken = _load_make_broken()
IDS = make_broken.IDS
FORM, CADENCES, BEATS = IDS["form"], IDS["cadences"], IDS["beats"]
FIRST, SECOND = make_broken.make_id(100), make_broken.make_id(101)
LYRICS = make_broken.make_id(102)


def a_file(tmp_path: Path, change=None, name: str = "piece.tla") -> Path:
    """WP3's valid file, with `change` made to its content."""
    content = copy.deepcopy(make_broken.base())
    if change is not None:
        change(content)
    path = tmp_path / name
    path.write_text(make_broken.text_of(content), encoding="utf-8")
    return path


def hierarchies(*components):
    def change(content):
        content["timelines"][FORM]["components"] = {
            id: {"kind": "HIERARCHY", **attrs} for id, attrs in components
        }

    return change


def at_level_0(content):
    """Row 4's example: a hierarchy at level 0, from 12 s to 45.5 s, in 'Form'."""
    hierarchies((FIRST, {"start": 12.0, "end": 45.5, "level": 0}))(content)


def an_old_file(tmp_path: Path, formal_type: str = "sonata") -> Path:
    """A file as TiLiA 0.7 saved it, with a formal type and a formal function."""
    file_data = get_blank_file_data()
    file_data["version"] = "0.7.0"
    file_data["media_metadata"]["media length"] = 100.0
    file_data["timelines"]["1"] = {
        "name": "Form",
        "kind": "HIERARCHY_TIMELINE",
        "height": 120,
        "is_visible": True,
        "ordinal": 2,
        "components": {
            "2": {
                "start": 0.0,
                "pre_start": 0.0,
                "end": 100.0,
                "post_end": 100.0,
                "level": 1,
                "label": "kept",
                "color": "",
                "formal_type": formal_type,
                "formal_function": "opening",
                "comments": "",
                "kind": "HIERARCHY",
                "hash": "irrelevant",
            }
        },
    }
    path = tmp_path / "old.tla"
    path.write_text(json.dumps(file_data), encoding="utf-8")
    return path


class ShownProblems(Serve):
    """Serves the dialog, keeping each file's name and lines it is shown with."""

    def __init__(self):
        super().__init__(Get.FROM_USER_SHOW_PROBLEMS, None)
        self.shown: list[tuple[str, list[str]]] = []

    def _callback(self, name, lines):
        self.shown.append((name, lines))


def open_file(path: Path, discard=False) -> list[tuple[str, list[str]]]:
    """Opens `path`, as the File menu does; what the dialog was shown with. Timelines
    of kinds TiLiA doesn't know are kept, or discarded if `discard`."""
    with (
        Serve(Get.FROM_USER_RETRY_MEDIA_PATH, False),
        Serve(Get.FROM_USER_RETRY_PDF_PATH, False),
        Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, discard)),
        ShownProblems() as problems,
    ):
        assert commands.execute("file.open", path)
    return problems.shown


def lines_shown(path: Path) -> list[str]:
    shown = open_file(path)
    assert len(shown) == 1  # one dialog
    return shown[0][1]


@pytest.fixture
def opening(qtui, tilia, tls):
    yield


class TestTheLines:
    def test_a_segment_is_its_timeline_its_span_and_the_reason(self, opening, tmp_path):
        # Row 4's example, word for word.
        assert lines_shown(a_file(tmp_path, at_level_0)) == [
            "Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'"
        ]

    def test_a_point_is_its_timeline_its_time_and_the_reason(self, opening, tmp_path):
        def past_the_end(content):
            content["media"]["length"] = 10.0
            content["timelines"][CADENCES]["components"] = {
                FIRST: {"kind": "MARKER", "time": 12.0}
            }

        assert lines_shown(a_file(tmp_path, past_the_end)) == [
            "Cadences, 00:12.0: Time '00:12.0' is bigger than media time '00:10.0'"
        ]

    def test_a_warning_without_ids_is_its_message_alone(self, opening, tmp_path):
        def media_length_0(content):
            content["media"]["length"] = 0

        assert lines_shown(a_file(tmp_path, media_length_0)) == [
            "0 is not a valid media length."
        ]

    def test_one_line_each_in_the_reader_s_order(self, opening, tmp_path):
        def two(content):
            at_level_0(content)
            content["media"]["length"] = 0

        assert lines_shown(a_file(tmp_path, two)) == [
            "0 is not a valid media length.",
            "Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'",
        ]

    def test_a_warning_about_a_timeline_alone_is_its_name_and_the_reason(
        self, opening, tmp_path
    ):
        # TimeLineAnnotator/project-management#597, point 2.
        def vocabulary(content):
            content["timelines"][FORM]["metadata"] = {"vocabulary": "not one"}

        assert lines_shown(a_file(tmp_path, vocabulary)) == [
            'Form: the vocabulary "not one" of the timeline "Form" isn\'t a valid'
            " reference"
        ]

    def test_a_component_tilia_doesn_t_show_is_its_timeline_s_name_and_the_reason(
        self, opening, tmp_path
    ):
        # A beat without a time is in no measure, so TiLiA shows it nowhere.
        # TimeLineAnnotator/project-management#597, point 2.
        def without_a_time(content):
            del content["timelines"][BEATS]["components"][IDS["beat_2"]]["time"]

        assert lines_shown(a_file(tmp_path, without_a_time)) == [
            'Beats: a beat of the timeline "Beats" has no time'
        ]

    def test_a_timeline_without_a_name_is_left_out(self, opening, tmp_path):
        # TimeLineAnnotator/project-management#597, point 3.
        def unnamed(content):
            at_level_0(content)
            content["timelines"][FORM]["name"] = ""

        assert lines_shown(a_file(tmp_path, unnamed)) == [
            "00:12.0–00:45.5: Level can't be below 1. Got '0'"
        ]

    def test_a_line_break_in_a_timeline_s_name_is_a_space(self, opening, tmp_path):
        def two_lines(content):
            at_level_0(content)
            content["timelines"][FORM]["name"] = "Form\nin two\r\nlines"

        assert lines_shown(a_file(tmp_path, two_lines)) == [
            "Form in two lines, 00:12.0–00:45.5: Level can't be below 1. Got '0'"
        ]

    def test_the_dialog_names_the_file(self, opening, tmp_path):
        shown = open_file(a_file(tmp_path, at_level_0, name="Sonata.tla"))

        assert [name for name, _ in shown] == ["Sonata.tla"]


def with_words(content):
    """A timeline of a kind TiLiA doesn't know, "Words", with a vocabulary that isn't
    a reference."""
    content["timelines"][LYRICS] = {
        "kind": "Lyrics",
        "name": "Words",
        "ordinal": 6,
        "metadata": {"vocabulary": "not one"},
        "components": {},
    }


class TestATimelineOfAKindTiLiADoesntKnow:
    """TimeLineAnnotator/project-management#597, point 8."""

    WORDS = (
        """the vocabulary "not one" of the timeline "Words" isn't a valid reference"""
    )

    def test_kept_its_warnings_are_listed_as_their_reason(self, opening, tmp_path):
        assert lines_shown(a_file(tmp_path, with_words)) == [self.WORDS]

    def test_discarded_its_warnings_aren_t_listed(self, opening, tmp_path):
        assert open_file(a_file(tmp_path, with_words), discard=True) == []

    def test_discarded_the_others_are_listed_and_counted(self, opening, tmp_path):
        def and_at_level_0(content):
            with_words(content)
            at_level_0(content)

        shown = open_file(a_file(tmp_path, and_at_level_0), discard=True)

        assert shown == [
            ("piece.tla", ["Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'"])
        ]


class TestAnOldFile:
    """Saving an old file drops its formal types and functions (#446): the dialog
    says so when it opens, before it can be saved without them."""

    def test_its_dropped_formal_type_is_shown_when_it_opens(self, opening, tmp_path):
        assert lines_shown(an_old_file(tmp_path)) == [
            'Form, 00:00.0–01:40.0: formal_type "sonata" dropped',
            'Form, 00:00.0–01:40.0: formal_function "opening" dropped',
        ]

    @pytest.mark.parametrize(
        "line_break",
        [chr(0x2028), chr(0x2029), chr(0x85)],
        ids=["line separator", "paragraph separator", "next line"],
    )
    def test_a_line_break_in_the_reason_is_a_space(self, opening, tmp_path, line_break):
        # The migration's reason quotes the value as JSON, which keeps these.
        path = an_old_file(tmp_path, formal_type=f"sonata{line_break}form")

        assert lines_shown(path) == [
            'Form, 00:00.0–01:40.0: formal_type "sonata form" dropped',
            'Form, 00:00.0–01:40.0: formal_function "opening" dropped',
        ]

    def test_a_save_after_it_writes_the_file_without_them(self, opening, tmp_path):
        assert lines_shown(an_old_file(tmp_path))

        saved = tmp_path / "saved.tla"
        assert commands.execute("file.save_as", str(saved))

        text = saved.read_text(encoding="utf-8")
        assert "formal_type" not in text
        assert "formal_function" not in text
        assert '"kept"' in text


class TestNoDialog:
    def test_for_a_file_with_no_warnings(self, opening, tmp_path):
        assert open_file(a_file(tmp_path)) == []

    def test_for_a_file_that_isn_t_opened(self, opening, tmp_path, tilia_errors):
        # The file open before has warnings of its own, which aren't shown again.
        assert lines_shown(a_file(tmp_path, at_level_0, name="before.tla"))
        path = a_file(tmp_path, at_level_0)
        path.write_text(path.read_text(encoding="utf-8")[:-10], encoding="utf-8")

        with ShownProblems() as problems:
            assert not commands.execute("file.open", path)

        assert problems.shown == []
        tilia_errors.assert_error()


@contextmanager
def not_served(request: Get):
    """No interface serves `request`."""
    replier, callback = server(request)
    stop_serving(replier, request)
    try:
        yield
    finally:
        serve(replier, request, callback)


class TestWithoutAnInterface:
    def test_the_file_opens_all_the_same(self, opening, tilia, tmp_path):
        path = a_file(tmp_path, at_level_0)

        with not_served(Get.FROM_USER_SHOW_PROBLEMS):
            assert commands.execute("file.open", path)

        assert tilia.file_manager.file.file_path == str(path.resolve())


def a_dialog(lines=("Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'",)):
    return ProblemsDialog("piece.tla", list(lines), None)


def button_texts(dialog) -> list[str]:
    return sorted(button.text().replace("&", "") for button in dialog.buttons.buttons())


class TestTheDialog:
    def test_row_4_s_words(self, qtui):
        lines = [
            "Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'",
            "0 is not a valid media length.",
        ]
        dialog = a_dialog(lines)

        assert dialog.windowTitle() == "Problems in this file"
        assert dialog.message.text() == MESSAGE.format(name="piece.tla", n=2)
        assert dialog.lines_view.toPlainText() == "\n".join(lines)
        assert button_texts(dialog) == ["Copy", "OK"]

    def test_one_problem_changes_only_the_noun(self, qtui):
        # TimeLineAnnotator/project-management#597, point 1.
        assert a_dialog().message.text() == (
            "'piece.tla' has 1 problem. TiLiA keeps them as they are, and saves them"
            " unchanged until you fix them."
        )

    def test_a_name_is_shown_as_it_is(self, qtui):
        dialog = ProblemsDialog("<b>piece</b>.tla", ["a line"], None)

        assert dialog.message.textFormat() == Qt.TextFormat.PlainText
        assert dialog.message.text().startswith("'<b>piece</b>.tla' has 1 problem.")

    def test_copy_puts_the_lines_on_the_clipboard_and_leaves_it_open(self, qtui):
        lines = ["one, 00:01.0: first", "two: second", "third"]
        dialog = a_dialog(lines)
        dialog.show()
        QGuiApplication.clipboard().setText("before")

        dialog.copy_button.click()

        assert (
            QGuiApplication.clipboard().text()
            == "one, 00:01.0: first\ntwo: second\nthird"
        )
        assert dialog.isVisible()
        dialog.close()

    def test_ok_closes_it(self, qtui):
        dialog = a_dialog()
        dialog.show()

        [ok] = [b for b in dialog.buttons.buttons() if b is not dialog.copy_button]
        ok.click()

        assert not dialog.isVisible()
        assert dialog.result() == QDialog.DialogCode.Accepted


@contextmanager
def dialogs_shown(when_shown=lambda dialog: None):
    """Each dialog TiLiA's window shows, instead of waiting for the user."""
    shown = []

    def exec_(dialog):
        shown.append(dialog)
        when_shown(dialog)

    with patch.object(ProblemsDialog, "exec", exec_):
        yield shown


@pytest.fixture
def main_window(qtui):
    """TiLiA's window, shown, as it is once TiLiA has started."""
    qtui.main_window.show()
    QTest.qWaitForWindowExposed(qtui.main_window)
    yield qtui.main_window
    qtui.main_window.hide()


def run_the_event_loop_until(condition, timeout_ms=2000):
    for _ in range(timeout_ms // 10):
        if condition():
            return True
        QTest.qWait(10)
    return condition()


class TestOpening:
    """TiLiA's window shows the dialog itself, over it."""

    def test_a_file_with_warnings_shows_the_dialog(
        self, opening, qtui, main_window, tmp_path
    ):
        with dialogs_shown() as shown:
            commands.execute("file.open", a_file(tmp_path, at_level_0))

        [dialog] = shown
        assert dialog.windowTitle() == "Problems in this file"
        assert dialog.message.text() == (
            "'piece.tla' has 1 problem. TiLiA keeps them as they are, and saves them"
            " unchanged until you fix them."
        )
        assert dialog.lines_view.toPlainText() == (
            "Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'"
        )
        assert dialog.parent() is qtui.main_window

    def test_a_file_with_none_shows_none(self, opening, main_window, tmp_path):
        with dialogs_shown() as shown:
            commands.execute("file.open", a_file(tmp_path))

        assert shown == []

    def test_once_the_file_is_open(self, opening, tilia, main_window, tmp_path):
        path = a_file(tmp_path, at_level_0)
        seen = []

        def when_shown(_):
            file = tilia.file_manager.file
            seen.append((file.file_path, tilia.is_file_modified()))

        with dialogs_shown(when_shown):
            commands.execute("file.open", path)

        assert seen == [(str(path.resolve()), False)]


class TestOnStartUp:
    """A file named when TiLiA starts opens before TiLiA's window shows: its
    dialog waits for the window, and then shows over it."""

    def test_waits_for_the_window(self, opening, qtui, tmp_path):
        window = qtui.main_window
        assert not window.isVisible()
        shown_returned = []
        seen = []

        def when_shown(dialog):
            seen.append(
                (dialog.parent() is window, window.isVisible(), bool(shown_returned))
            )

        with dialogs_shown(when_shown) as shown:
            assert commands.execute("file.open", a_file(tmp_path, at_level_0))
            QCoreApplication.processEvents()
            assert shown == []

            window.show()
            shown_returned.append(True)
            try:
                assert run_the_event_loop_until(lambda: shown)
            finally:
                window.hide()

        # Over the window, once it shows, and from the event loop: not from within
        # `show()`, as TiLiA's start calls it before its event loop runs.
        assert seen == [(True, True, True)]
        assert shown[0].lines_view.toPlainText() == (
            "Form, 00:12.0–00:45.5: Level can't be below 1. Got '0'"
        )

    def test_shows_once(self, opening, qtui, tmp_path):
        window = qtui.main_window
        with dialogs_shown() as shown:
            commands.execute("file.open", a_file(tmp_path, at_level_0))
            window.show()
            try:
                assert run_the_event_loop_until(lambda: shown)
                window.hide()
                window.show()
                QTest.qWait(50)
            finally:
                window.hide()

        assert len(shown) == 1
