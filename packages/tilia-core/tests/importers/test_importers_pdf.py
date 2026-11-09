import json
import os
import subprocess
import sys
import unicodedata

import pypdf
import pytest
from import_docs import component, document, timeline

from tilia_core import rules, tla
from tilia_core.importers import pdf as pdf_module
from tilia_core.importers._results import ImportFailed
from tilia_core.importers.pdf import import_by_time


def make_pdf(path, pages):
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    with open(path, "wb") as file:
        writer.write(file)
    return path


@pytest.fixture
def csv_file(tmp_path):
    def write(text, encoding="utf-8"):
        path = tmp_path / "pages.csv"
        path.write_text(text, encoding=encoding, newline="")
        return path

    return write


@pytest.fixture
def pdf_timeline(tmp_path):
    """A timeline whose PDF, made here, has `pages` pages."""

    def make(pages=2):
        path = make_pdf(tmp_path / "score.pdf", pages)
        return timeline("pdf", attrs={"path": str(path)})

    return make


def csv_of(*rows):
    return "\n".join(",".join(map(str, row)) for row in rows)


def markers_of(target):
    return list(target.components.values())


def messages(result):
    return [problem.message for problem in result.problems]


NO_SUCH_PAGE = "The PDF has no page with that number."


class TestByTime:
    # From TiLiA's tests/parsers/csv/test_pdf_from_csv.py, TestByTime.

    def test_pdf_marker_by_time(self, pdf_timeline, csv_file):
        target = pdf_timeline(1)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [5, 1]))
        )

        assert result.problems == []
        marker = markers_of(target)[0]
        assert len(target.components) == 1
        assert marker.kind == "pdf_marker"
        assert marker.attrs == {"time": 5, "page_number": 1}

    def test_pdf_marker_by_time_multiple(self, pdf_timeline, csv_file):
        target = pdf_timeline(12)
        doc = document(timelines=[target])
        rows = [["time", "page_number"], [0, 1], [1, 2], [10, 11], [11, 12], [20, 3]]

        result = import_by_time(doc, target.id, csv_file(csv_of(*rows)))

        assert result.problems == []
        for marker, (time, page_number) in zip(
            markers_of(target), rows[1:], strict=True
        ):
            assert marker.attrs["time"] == time
            assert marker.attrs["page_number"] == page_number

    def test_invalid_values_return_errors(self, pdf_timeline, csv_file):
        target = pdf_timeline(1)
        doc = document(timelines=[target])

        result = import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], ["invalid", 1], [1, "invalid"])),
        )

        assert messages(result) == [
            "invalid is not a valid time.",
            "invalid is not a valid page number.",
        ]
        assert [problem.column for problem in result.problems] == [
            "time",
            "page_number",
        ]
        assert [problem.line for problem in result.problems] == [2, 3]
        assert all(problem.skipped for problem in result.problems)
        assert markers_of(target) == []

    def test_time_out_of_bound_returns_error(self, pdf_timeline, csv_file):
        target = pdf_timeline(1)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, -1], [1, 2]))
        )

        assert messages(result) == [NO_SUCH_PAGE, NO_SUCH_PAGE]
        assert markers_of(target) == []

    def test_valid_markers_get_created_even_if_errors_happen(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(1)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, -1], [1, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        marker = markers_of(target)[0]
        assert len(target.components) == 1
        assert marker.attrs["time"] == 1
        assert marker.attrs["page_number"] == 1


class TestTwoPagePdf:
    @pytest.mark.parametrize("page", [1, 2])
    def test_a_page_it_has(self, pdf_timeline, csv_file, page):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, page]))
        )

        assert result.problems == []
        assert markers_of(target)[0].attrs["page_number"] == page

    @pytest.mark.parametrize("page", [0, -1, 3])
    def test_a_page_it_hasnt_is_a_skipped_row(self, pdf_timeline, csv_file, page):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, page]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.problems[0].line == 2
        assert result.problems[0].column == "page_number"
        assert result.problems[0].skipped
        assert result.notes == []
        assert markers_of(target) == []

    def test_a_page_number_that_isnt_an_integer(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1.5]))
        )

        assert messages(result) == ["1.5 is not a valid page number."]

    def test_a_page_number_is_stored_as_an_integer(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 2]))
        )

        assert type(markers_of(target)[0].attrs["page_number"]) is int
        assert type(markers_of(target)[0].attrs["time"]) is float


class TestAPdfThatCantBeRead:
    def test_a_missing_pdf_refuses_every_row_with_one_note(self, tmp_path, csv_file):
        missing = tmp_path / "missing.pdf"
        target = timeline("pdf", attrs={"path": str(missing)})
        doc = document(timelines=[target])

        result = import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], [0, 1], [1, 2], [2, 3])),
        )

        assert messages(result) == [NO_SUCH_PAGE] * 3
        assert all(problem.skipped for problem in result.problems)
        assert result.notes == [
            f"The PDF '{missing}' can't be read: every page number is refused"
        ]
        assert markers_of(target) == []

    def test_a_file_that_isnt_a_pdf(self, tmp_path, csv_file):
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"this isn't a PDF")
        target = timeline("pdf", attrs={"path": str(garbage)})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert len(result.notes) == 1

    def test_an_empty_file(self, tmp_path, csv_file):
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        target = timeline("pdf", attrs={"path": str(empty)})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert len(result.notes) == 1

    def test_an_encrypted_pdf(self, tmp_path, csv_file):
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.encrypt("secret", algorithm="RC4-128")
        locked = tmp_path / "locked.pdf"
        with open(locked, "wb") as file:
            writer.write(file)
        target = timeline("pdf", attrs={"path": str(locked)})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert len(result.notes) == 1

    def test_pypdfs_log_doesnt_reach_standard_error(self, tmp_path):
        # tilia run's standard error holds its reports only, and pypdf logs what it
        # finds in a broken file, to standard error when nothing has set up logging.
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"this isn't a PDF")
        probe = (
            "import sys; from pathlib import Path;"
            " from tilia_core.importers.pdf import _page_count;"
            " sys.exit(_page_count(Path(sys.argv[1])) is not None)"
        )

        ran = subprocess.run(
            [sys.executable, "-c", probe, str(garbage)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        assert ran.returncode == 0
        assert ran.stderr == ""

    def test_a_folder(self, tmp_path, csv_file):
        target = timeline("pdf", attrs={"path": str(tmp_path)})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert len(result.notes) == 1

    @pytest.mark.parametrize(
        "attrs", [{"path": ""}, {}], ids=["an empty path", "no path"]
    )
    def test_a_timeline_without_a_path_has_no_pdf(self, csv_file, attrs):
        target = timeline("pdf", attrs=attrs)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == ["This timeline has no PDF."]

    def test_the_note_comes_once_with_no_rows(self, tmp_path, csv_file):
        target = timeline("pdf", attrs={"path": str(tmp_path / "missing.pdf")})
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, csv_file("time,page_number\n"))

        assert result.problems == []
        assert len(result.notes) == 1

    def test_a_pdf_with_no_pages_can_be_read(self, tmp_path, csv_file):
        target = timeline("pdf", attrs={"path": str(make_pdf(tmp_path / "e.pdf", 0))})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == []


class TestThePdfsPath:
    def test_a_relative_path_is_read_from_the_documents_folder(
        self, tmp_path, csv_file
    ):
        (tmp_path / "piece" / "scores").mkdir(parents=True)
        make_pdf(tmp_path / "piece" / "scores" / "score.pdf", 2)
        target = timeline("pdf", attrs={"path": "scores/score.pdf"})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece" / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 2]))
        )

        assert result.problems == []
        assert result.notes == []

    def test_an_absolute_path_is_read_as_it_is(self, tmp_path, csv_file):
        target = timeline(
            "pdf", attrs={"path": str(make_pdf(tmp_path / "score.pdf", 2))}
        )
        doc = document(timelines=[target])
        doc.origin = tmp_path / "elsewhere" / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 2]))
        )

        assert result.problems == []

    def test_the_note_names_the_file_it_looked_for(self, tmp_path, csv_file):
        target = timeline("pdf", attrs={"path": "scores/missing.pdf"})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(doc, target.id, csv_file("time,page_number\n"))

        looked_for = tmp_path / "scores" / "missing.pdf"
        assert result.notes == [
            f"The PDF '{looked_for}' can't be read: every page number is refused"
        ]

    def test_a_name_stored_composed_is_found_decomposed(self, tmp_path, csv_file):
        # Files are named in decomposed form (NFD) on macOS's older file
        # system and copied elsewhere; `tla.media` finds them, and so must this.
        stored = unicodedata.normalize("NFC", "scores/Études.pdf")
        named = unicodedata.normalize("NFD", "scores/Études.pdf")
        assert stored != named
        (tmp_path / "scores").mkdir()
        make_pdf(tmp_path / named, 2)
        target = timeline("pdf", attrs={"path": stored})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 2]))
        )

        assert result.problems == []
        assert result.notes == []

    @pytest.mark.skipif(os.name == "nt", reason="a path of Windows form is Windows's")
    def test_a_path_of_the_other_systems_form_isnt_looked_up(self, tmp_path, csv_file):
        # Joined to the folder, `C:/scores/score.pdf` would name a file below it.
        (tmp_path / "C:" / "scores").mkdir(parents=True)
        make_pdf(tmp_path / "C:" / "scores" / "score.pdf", 2)
        target = timeline("pdf", attrs={"path": "C:/scores/score.pdf"})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == [
            "The PDF 'C:/scores/score.pdf' can't be read: every page number is refused"
        ]

    def test_pdf_file_asks_tlas_local_file(self, tmp_path, csv_file, monkeypatch):
        asked = []

        def local_file(stored, folder):
            asked.append((stored, folder))
            return None

        monkeypatch.setattr(pdf_module, "local_file", local_file)
        target = timeline("pdf", attrs={"path": "scores/score.pdf"})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        import_by_time(doc, target.id, csv_file("time,page_number\n"))

        assert asked == [("scores/score.pdf", str(tmp_path))]

    def test_a_stored_url_isnt_looked_up(self, tmp_path, csv_file, monkeypatch):
        # Joined to the folder, `https://example.com/score.pdf` would name a
        # file below a folder called `https:` on macOS and Linux.
        asked = []
        monkeypatch.setattr(
            pdf_module, "local_file", lambda *args: asked.append(args) or None
        )
        stored = "https://example.com/score.pdf"
        target = timeline("pdf", attrs={"path": stored})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert asked == []
        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == [
            f"The PDF '{stored}' can't be read: every page number is refused"
        ]

    @pytest.mark.skipif(os.name != "nt", reason="the mirror of the POSIX test")
    def test_a_posix_form_path_isnt_looked_up_on_windows(
        self, tmp_path, csv_file, monkeypatch
    ):
        # `/...` with no drive is the other system's form here, yet Windows
        # reads it through the current drive and would find the file.
        monkeypatch.chdir(tmp_path)
        (tmp_path / "scores").mkdir()
        make_pdf(tmp_path / "scores" / "score.pdf", 2)
        stored = (tmp_path / "scores" / "score.pdf").as_posix()[2:]
        assert os.path.isfile(stored)
        target = timeline("pdf", attrs={"path": stored})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == [
            f"The PDF '{stored}' can't be read: every page number is refused"
        ]

    def test_the_note_names_the_file_found_when_it_cant_be_read(
        self, tmp_path, csv_file
    ):
        # Found as its decomposed (NFD) name, which differs from the stored
        # and the joined path: the note names the file, not what was stored.
        named = unicodedata.normalize("NFD", "Études.pdf")
        (tmp_path / named).write_bytes(b"this isn't a PDF")
        stored = unicodedata.normalize("NFC", "Études.pdf")
        target = timeline("pdf", attrs={"path": stored})
        doc = document(timelines=[target])
        doc.origin = tmp_path / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        # The note names the file that was found. macOS's file system doesn't
        # tell NFC from NFD apart, so there the stored name finds it first and
        # is the one shown: compare the files, and the exact name elsewhere.
        (note,) = result.notes
        start, end = "The PDF '", "' can't be read: every page number is refused"
        assert note.startswith(start) and note.endswith(end)
        shown = note[len(start) : -len(end)]
        assert os.path.samefile(shown, tmp_path / named)
        if sys.platform != "darwin":
            assert shown == str(tmp_path / named)

    @pytest.mark.parametrize(
        "stored, folder",
        [("scores/bad\udcff.pdf", ""), ("score.pdf", "bad\udcff")],
        ids=["in the stored path", "in the documents folder"],
    )
    def test_the_note_can_be_printed_whatever_the_name(
        self, tmp_path, csv_file, stored, folder
    ):
        target = timeline("pdf", attrs={"path": stored})
        doc = document(timelines=[target])
        doc.origin = tmp_path / folder / "piece.tla"

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        (note,) = result.notes
        assert note.encode("utf-8")
        assert "bad\\udcff" in note

    def test_a_relative_path_with_no_document_folder_isnt_looked_up(
        self, tmp_path, csv_file, monkeypatch
    ):
        # A document built in memory has no folder, so a relative path names no
        # file; it isn't read from wherever the process happens to run.
        make_pdf(tmp_path / "score.pdf", 2)
        monkeypatch.chdir(tmp_path)
        target = timeline("pdf", attrs={"path": "score.pdf"})
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert messages(result) == [NO_SUCH_PAGE]
        assert result.notes == [
            "The PDF 'score.pdf' can't be read: every page number is refused"
        ]


class TestTheRules:
    @pytest.mark.parametrize(
        "time, message",
        [
            (-1, "Time can't be negative. Got '-00:01.0'"),
            (61, "Time '01:01.0' is bigger than media time '01:00.0'"),
            ("nan", "nan is not a valid time."),
            ("inf", "inf is not a valid time."),
        ],
    )
    def test_a_time_the_rules_refuse(self, pdf_timeline, csv_file, time, message):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [time, 1], [0, 1]))
        )

        assert messages(result) == [message]
        assert result.problems[0].line == 2
        assert result.problems[0].column == "time"
        assert result.problems[0].skipped
        assert len(target.components) == 1

    def test_two_markers_at_one_time_keep_the_first(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], [1, 1], [1, 2])),
        )

        assert messages(result) == [
            "There is already a PDF page marker component at the selected position."
        ]
        assert result.problems[0].line == 3
        assert markers_of(target)[0].attrs["page_number"] == 1
        assert len(target.components) == 1

    def test_one_check_per_import(self, pdf_timeline, csv_file, monkeypatch):
        target = pdf_timeline(2)
        doc = document(timelines=[target])
        calls = []
        check_timeline = rules.check_timeline

        def counted(media_length, components, **kwargs):
            calls.append(kwargs)
            return check_timeline(media_length, components, **kwargs)

        monkeypatch.setattr(rules, "check_timeline", counted)

        import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], [0, 1], [1, 2], [2, 9])),
        )

        assert calls == [{"page_count": 2, "skip_broken": True}]

    def test_the_kinds_function_isnt_called_row_by_row(
        self, pdf_timeline, csv_file, monkeypatch
    ):
        def refuse(*_args, **_kwargs):
            raise AssertionError("checked row by row")

        monkeypatch.setattr(rules, "pdf_marker", refuse)
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )


class TestABadTimeAndABadPage:
    @pytest.mark.parametrize(
        "row, message, column",
        [
            (["abc", "xyz"], "abc is not a valid time.", "time"),
            (["abc", 9], "abc is not a valid time.", "time"),
            ([61, 9], "Time '01:01.0' is bigger than media time '01:00.0'", "time"),
            ([-1, 9], "Time can't be negative. Got '-00:01.0'", "time"),
            # A cell that can't be read comes before any rule.
            ([61, "xyz"], "xyz is not a valid page number.", "page_number"),
        ],
        ids=[
            "neither can be read",
            "no time, a page it hasn't",
            "beyond the media, a page it hasn't",
            "negative, a page it hasn't",
            "beyond the media, no page",
        ],
    )
    def test_one_problem_for_the_row(
        self, pdf_timeline, csv_file, row, message, column
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], row))
        )

        assert messages(result) == [message]
        assert result.problems[0].column == column
        assert result.problems[0].skipped
        assert markers_of(target) == []


class TestShortRows:
    # A column the row is too short for reads as an empty cell.

    @pytest.mark.parametrize(
        "header, row, column, message",
        [
            (
                "time,page_number",
                "0",
                "page_number",
                "an empty value is not a valid page number.",
            ),
            ("page_number,time", "1", "time", "an empty value is not a valid time."),
        ],
    )
    def test_a_missing_cell_skips_the_row(
        self, pdf_timeline, csv_file, header, row, column, message
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, csv_file(f"{header}\n{row}\n"))

        assert messages(result) == [message]
        assert result.problems[0].column == column
        assert result.problems[0].skipped
        assert markers_of(target) == []

    def test_an_empty_cell_reads_the_same(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, csv_file("time,page_number\n0,\n"))

        assert messages(result) == ["an empty value is not a valid page number."]

    @pytest.mark.parametrize(
        "row, column, message",
        [
            ('"  ",1', "time", "an empty value is not a valid time."),
            ('0,"  "', "page_number", "an empty value is not a valid page number."),
        ],
        ids=["time", "page number"],
    )
    def test_a_cell_of_only_spaces_reads_the_same(
        self, pdf_timeline, csv_file, row, column, message
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, csv_file(f"time,page_number\n{row}\n"))

        assert messages(result) == [message]
        assert result.problems[0].column == column
        assert result.problems[0].skipped


class TestResult:
    def test_created_is_the_new_ids_in_the_order_of_the_rows(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], [5, 1], [3, 9], [1, 2])),
        )

        assert result.created == list(target.components)
        assert [target.components[i].attrs["time"] for i in result.created] == [5, 1]

    def test_rows_counts_those_read_and_leaves_empty_ones_out(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc, target.id, csv_file("time,page_number\n0,1\n\nabc,1\n\n1,9")
        )

        assert result.rows == 3

    def test_problems_are_in_row_order_whichever_step_found_them(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(
            doc,
            target.id,
            csv_file(csv_of(["time", "page_number"], [0, 9], ["abc", 1], [1, 9])),
        )

        assert [problem.line for problem in result.problems] == [2, 3, 4]

    def test_a_problems_path_is_the_csv(self, pdf_timeline, csv_file, tmp_path):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        result = import_by_time(doc, target.id, csv_file("time,page_number\nabc,1"))

        assert result.problems[0].path == tmp_path / "pages.csv"


class TestTheDocument:
    def test_it_replaces_the_markers(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        old = component("pdf_marker", time=9.0, page_number=2)
        target.components[old.id] = old
        doc = document(timelines=[target])

        import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        assert old.id not in target.components
        assert len(target.components) == 1

    def test_a_component_of_a_kind_the_core_doesnt_know_stays(
        self, pdf_timeline, csv_file
    ):
        # FR-032, and WP3's FR-015.
        target = pdf_timeline(2)
        target.attrs["height"] = 30  # a written timeline has one
        old = component("pdf_marker", time=9.0, page_number=2)
        unknown = tla.Component(
            id=tla.new_id(), kind=tla.UnknownKind("LYRIC"), extra={"time": 9.0}
        )
        target.components = {old.id: old, unknown.id: unknown}
        written = tla.canonical_bytes(document(timelines=[target]))
        read = tla.loads(written)

        result = import_by_time(
            read, target.id, csv_file(csv_of(["time", "page_number"], [0, 1]))
        )

        kept = read.timelines[target.id].components
        assert set(kept) == {unknown.id, *result.created}
        assert kept[unknown.id] == unknown
        assert (
            json.loads(tla.canonical_bytes(read))["timelines"][target.id]["components"][
                unknown.id
            ]
            == json.loads(written)["timelines"][target.id]["components"][unknown.id]
        )

    def test_the_path_can_be_text(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])
        path = csv_file("time,page_number\nabc,1")

        result = import_by_time(doc, target.id, str(path))

        assert result.problems[0].path == path

    def test_the_required_columns_are_named_in_tilias_order(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(2)
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed) as failed:
            import_by_time(doc, target.id, csv_file("label\nx"))

        assert failed.value.message == (
            "Column 'page_number' not found on first row of .csv file."
        )

    def test_importing_twice_gives_the_same_new_ids_aside(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target])
        path = csv_file(csv_of(["time", "page_number"], [0, 1], [1, 2]))

        import_by_time(doc, target.id, path)
        first = [marker.attrs for marker in markers_of(target)]
        import_by_time(doc, target.id, path)

        assert [marker.attrs for marker in markers_of(target)] == first

    def test_a_quarters_document_reads_times_as_they_are(self, pdf_timeline, csv_file):
        target = pdf_timeline(2)
        doc = document(timelines=[target], time_unit="quarters", media_length=240.0)

        result = import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [120, 1]))
        )

        assert result.problems == []
        assert markers_of(target)[0].attrs["time"] == 120

    @pytest.mark.parametrize(
        "text, encoding, message",
        [
            (
                "time\n0",
                "utf-8",
                "Column 'page_number' not found on first row of .csv file.",
            ),
            (
                "page_number\n1",
                "utf-8",
                "Column 'time' not found on first row of .csv file.",
            ),
            ("", "utf-8", "Can't import: file is empty."),
            ("time,page_number,café\n0,1,x", "cp1252", None),
        ],
        ids=["no page number", "no time", "an empty file", "a file that isn't UTF-8"],
    )
    def test_a_failed_import_changes_nothing(
        self, pdf_timeline, csv_file, text, encoding, message
    ):
        target = pdf_timeline(2)
        old = component("pdf_marker", time=9.0, page_number=2)
        target.components[old.id] = old
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed) as failed:
            import_by_time(doc, target.id, csv_file(text, encoding))

        if message is not None:
            assert failed.value.message == message
        assert list(target.components) == [old.id]

    def test_a_document_with_no_media_length_changes_nothing(
        self, pdf_timeline, csv_file
    ):
        # TimeLineAnnotator/project-management#418: a file can bring a timeline and
        # no media length.
        target = pdf_timeline(2)
        old = component("pdf_marker", time=9.0, page_number=2)
        target.components[old.id] = old
        doc = document(timelines=[target], media_length=None)

        with pytest.raises(ImportFailed) as failed:
            import_by_time(doc, target.id, csv_file("time,page_number\n0,1"))

        assert failed.value.message.startswith("No media loaded and no duration set.")
        assert list(target.components) == [old.id]

    def test_a_file_that_doesnt_exist_changes_nothing(self, pdf_timeline, tmp_path):
        target = pdf_timeline(2)
        old = component("pdf_marker", time=9.0, page_number=2)
        target.components[old.id] = old
        doc = document(timelines=[target])

        with pytest.raises(OSError):
            import_by_time(doc, target.id, tmp_path / "missing.csv")

        assert list(target.components) == [old.id]

    def test_an_imported_document_can_be_written_and_read_back(
        self, pdf_timeline, csv_file
    ):
        target = pdf_timeline(2)
        target.attrs["height"] = 30  # a written timeline has one
        doc = document(timelines=[target])
        import_by_time(
            doc, target.id, csv_file(csv_of(["time", "page_number"], [0, 1], [1, 2]))
        )

        read = tla.loads(tla.canonical_bytes(doc))

        assert [c.attrs for c in read.timelines[target.id].components.values()] == [
            c.attrs for c in target.components.values()
        ]
