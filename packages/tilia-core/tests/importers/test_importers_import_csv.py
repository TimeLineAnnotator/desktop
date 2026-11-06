"""`import_csv`: which importer a target gets, and what fails an import as a whole,
changing nothing (FR-024). What each importer reads is in its own tests.

The refusals' texts are those TimeLineAnnotator/project-management#484 (what such a
refusal says) answered."""

import copy
import importlib.util
import inspect
import sys

import pypdf
import pytest
from import_docs import component, document, timeline

from tilia_core import importers, tla
from tilia_core.importers import ImportFailed, ImportResult, harmony_available

# The columns of every kind by time, so that one CSV can go into any of them.
ANY_KIND = "time,page_number,start,end,level,row\n1,1,0,10,1,Strings\n"
NOT_ONE_OF_THEM = "is not a marker, hierarchy, range, harmony or pdf timeline"
BY_MEASURE = "Reference beat timeline is required for importing by measure"
BY = "'by' must be either 'time' or 'measure'"
HARMONY_EXTRA = 'harmony import needs: pip install "tilia-core[harmony]"'
REQUIRED = {
    "marker": ("time",),
    "hierarchy": ("start", "end", "level"),
    "range": ("start", "end", "row"),
    "pdf": ("time", "page_number"),
}


@pytest.fixture
def csv_file(tmp_path):
    def write(text=ANY_KIND):
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8", newline="")
        return path

    return write


@pytest.fixture
def pdf_file(tmp_path):
    path = tmp_path / "score.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(path)
    return path


def music21_found(monkeypatch, spec):
    """Makes `find_spec` give `spec` for music21, whether it is installed or not."""
    find_spec = importlib.util.find_spec

    def patched(name, *args, **kwargs):
        if name == "music21":
            return spec
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", patched)


@pytest.fixture
def with_the_extra(monkeypatch):
    music21_found(monkeypatch, object())


@pytest.fixture
def without_the_extra(monkeypatch):
    music21_found(monkeypatch, None)


def holding_a_component(kind, **kwargs):
    return timeline(kind, components=[component("marker", time=5.0)], **kwargs)


def refused(doc, target, path, **kwargs):
    """The failure of an import that must change nothing."""
    before = copy.deepcopy(doc)

    with pytest.raises(ImportFailed) as failed:
        importers.import_csv(doc, target, path, **kwargs)

    assert doc == before
    return failed.value


class TestDispatch:
    @pytest.mark.parametrize(
        "kind, made",
        [
            ("marker", "marker"),
            ("hierarchy", "hierarchy"),
            ("range", "range"),
            ("pdf", "pdf_marker"),
        ],
    )
    def test_the_targets_kind_picks_the_importer(self, csv_file, pdf_file, kind, made):
        attrs = {"path": str(pdf_file)} if kind == "pdf" else {}
        target = timeline(kind, attrs=attrs)
        doc = document(timelines=[target])

        result = importers.import_csv(doc, target.id, csv_file(), by="time")

        assert isinstance(result, ImportResult)
        assert result.problems == []
        assert result.rows == 1
        assert result.created == list(target.components)
        assert [one.kind for one in target.components.values()] == [made]

    def test_it_changes_only_the_target(self, csv_file):
        target = timeline("marker")
        other = holding_a_component("marker", ordinal=2)
        doc = document(timelines=[target, other])
        before = copy.deepcopy(other)

        importers.import_csv(doc, target.id, csv_file(), by="time")

        assert other == before

    def test_the_path_can_be_text(self, csv_file):
        target = timeline("marker")
        doc = document(timelines=[target])

        result = importers.import_csv(doc, target.id, str(csv_file()), by="time")

        assert len(result.created) == 1

    def test_a_reference_by_time_isnt_read(self, csv_file):
        # As TiLiA's command line, which looks for one only by measure.
        target = timeline("marker")
        doc = document(timelines=[target])

        result = importers.import_csv(
            doc, target.id, csv_file(), by="time", reference="no such timeline"
        )

        assert len(result.created) == 1


class TestTargetOfTheWrongKind:
    @pytest.mark.parametrize("kind", ["beat", "slider", "score", "audiowave"])
    def test_a_kind_it_doesnt_import(self, csv_file, kind):
        target = holding_a_component(kind, name="Other")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="time")

        assert failed.message == (
            f"{kind.capitalize()} timeline 'Other' (ordinal 1) {NOT_ONE_OF_THEM}"
        )

    @pytest.mark.parametrize(
        "kind, shown",
        [
            (tla.UnknownKind("Lyrics"), "Lyrics"),
            # Spelled as the API names a kind, or as a file spells one, it still
            # isn't that kind.
            (tla.UnknownKind("marker"), "Marker"),
            (tla.UnknownKind("Marker"), "Marker"),
            (tla.UnknownKind("lyrics"), "Lyrics"),
            (tla.UnknownKind("TimeLine"), "TimeLine"),
            ("lyrics", "Lyrics"),
        ],
    )
    def test_a_kind_the_core_doesnt_know(self, csv_file, kind, shown):
        target = holding_a_component(kind, name="Other")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="time")

        assert failed.message == (
            f"{shown} timeline 'Other' (ordinal 1) {NOT_ONE_OF_THEM}"
        )

    def test_a_kind_the_core_doesnt_know_from_a_file_can_still_be_written(
        self, csv_file
    ):
        # Imported into, it took markers that the next write refused.
        raw = {"kind": "Lyrics", "ordinal": 1, "components": {"a": {"time": 1.0}}}
        unknown = tla.Timeline(
            id=tla.new_id(), kind=tla.UnknownKind("Lyrics"), ordinal=1, raw=raw
        )
        written = tla.canonical_bytes(document(timelines=[unknown]))
        doc = tla.loads(written)

        refused(doc, next(iter(doc.timelines)), csv_file(), by="time")

        assert tla.canonical_bytes(doc) == written

    def test_a_timeline_with_no_name_is_given_by_its_kind_and_ordinal(self, csv_file):
        target = timeline("beat", ordinal=3)
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="time")

        assert failed.message == f"Beat timeline (ordinal 3) {NOT_ONE_OF_THEM}"

    def test_a_lone_surrogate_in_a_name_is_written_out(self, csv_file):
        target = timeline("beat", name="\ud83d", ordinal=2)
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="time")

        assert (
            failed.message == f"Beat timeline '\\ud83d' (ordinal 2) {NOT_ONE_OF_THEM}"
        )
        str(failed).encode("utf-8")

    def test_a_lone_surrogate_in_an_id_is_written_out(self, csv_file):
        failed = refused(document(), "\ud83d", csv_file(), by="time")

        assert failed.message == "No timeline found with id=\\ud83d"
        str(failed).encode("utf-8")

    def test_the_failure_names_the_csv(self, csv_file):
        target = timeline("beat", name="Measures")
        doc = document(timelines=[target])
        path = csv_file()

        failed = refused(doc, target.id, path, by="time")

        assert failed.path == path
        assert str(failed) == (
            f"data.csv: Beat timeline 'Measures' (ordinal 1) {NOT_ONE_OF_THEM}"
        )

    def test_an_id_the_document_doesnt_have(self, csv_file):
        doc = document(timelines=[timeline("marker")])

        path = csv_file()

        failed = refused(doc, "no such timeline", path, by="time")

        assert failed.message == "No timeline found with id=no such timeline"
        assert failed.path == path


class TestBy:
    @pytest.mark.parametrize("by", ["bar", "by-time", "TIME", "", None])
    def test_anything_else_than_time_or_measure(self, csv_file, by):
        target = holding_a_component("marker")
        doc = document(timelines=[target])

        path = csv_file()

        failed = refused(doc, target.id, path, by=by)

        assert failed.message == BY
        assert failed.path == path

    def test_it_must_be_given(self, csv_file):
        target = timeline("marker")
        doc = document(timelines=[target])

        with pytest.raises(TypeError):
            importers.import_csv(doc, target.id, csv_file())


class TestByMeasure:
    @pytest.mark.parametrize("kind", ["marker", "hierarchy", "range", "harmony", "pdf"])
    def test_a_missing_reference(self, csv_file, with_the_extra, kind):
        target = holding_a_component(kind)
        doc = document(timelines=[target])

        path = csv_file()

        failed = refused(doc, target.id, path, by="measure")

        assert failed.message == BY_MEASURE
        assert failed.path == path

    @pytest.mark.parametrize(
        "kind", ["marker", "harmony", "slider", tla.UnknownKind("Beat")]
    )
    def test_a_reference_that_isnt_a_beat_timeline(self, csv_file, kind):
        target = holding_a_component("marker")
        reference = timeline(kind, name="Other", ordinal=2)
        doc = document(timelines=[target, reference])
        path = csv_file()

        failed = refused(doc, target.id, path, by="measure", reference=reference.id)

        shown = kind.spelling if isinstance(kind, tla.UnknownKind) else kind
        assert failed.message == (
            f"{shown.capitalize()} timeline 'Other' (ordinal 2) is not a beat timeline"
        )
        assert failed.path == path

    def test_a_reference_with_no_name_is_given_by_its_kind_and_ordinal(self, csv_file):
        target = holding_a_component("marker")
        reference = timeline("marker", ordinal=4)
        doc = document(timelines=[target, reference])

        failed = refused(
            doc, target.id, csv_file(), by="measure", reference=reference.id
        )

        assert failed.message == "Marker timeline (ordinal 4) is not a beat timeline"

    def test_a_reference_the_document_doesnt_have(self, csv_file):
        target = holding_a_component("marker")
        doc = document(timelines=[target])

        path = csv_file()

        failed = refused(doc, target.id, path, by="measure", reference="none")

        assert failed.message == "No timeline found with id=none"
        assert failed.path == path

    @pytest.mark.parametrize("kind", ["marker", "hierarchy", "range", "pdf"])
    def test_isnt_implemented_yet(self, csv_file, kind):
        # Until TimeLineAnnotator/project-management#272 (markers and PDF markers by
        # measure) and TimeLineAnnotator/project-management#273 (hierarchies and
        # ranges by measure).
        target = holding_a_component(kind)
        reference = timeline("beat", ordinal=2)
        doc = document(timelines=[target, reference])
        before = copy.deepcopy(doc)

        with pytest.raises(NotImplementedError):
            importers.import_csv(
                doc, target.id, csv_file(), by="measure", reference=reference.id
            )

        assert doc == before


class TestHarmony:
    @pytest.mark.parametrize("by", ["time", "measure"])
    def test_without_the_extra_it_names_the_command(
        self, csv_file, without_the_extra, by
    ):
        target = holding_a_component("harmony")
        reference = timeline("beat", ordinal=2)
        doc = document(timelines=[target, reference])

        failed = refused(doc, target.id, csv_file(), by=by, reference=reference.id)

        assert failed.message == HARMONY_EXTRA
        assert str(failed) == f"data.csv: {HARMONY_EXTRA}"

    def test_another_kind_doesnt_need_the_extra(self, csv_file, without_the_extra):
        target = timeline("marker")
        doc = document(timelines=[target])

        result = importers.import_csv(doc, target.id, csv_file(), by="time")

        assert len(result.created) == 1

    def test_with_the_extra_it_imports_by_time(self, csv_file):
        pytest.importorskip("music21", reason="needs the harmony extra")
        target = timeline("harmony")
        doc = document(timelines=[target])
        path = csv_file("time,harmony_or_key,symbol\n1,harmony,C\n")

        result = importers.import_csv(doc, target.id, path, by="time")

        assert result.problems == []
        assert result.created == list(target.components)
        assert [one.kind for one in target.components.values()] == ["harmony"]

    def test_with_the_extra_by_measure_isnt_implemented_yet(
        self, csv_file, with_the_extra
    ):
        # Until TimeLineAnnotator/project-management#274 (harmonies by measure).
        target = holding_a_component("harmony")
        reference = timeline("beat", ordinal=2)
        doc = document(timelines=[target, reference])
        before = copy.deepcopy(doc)

        with pytest.raises(NotImplementedError):
            importers.import_csv(
                doc, target.id, csv_file(), by="measure", reference=reference.id
            )

        assert doc == before


class TestTheFileFails:
    @pytest.mark.parametrize(
        "kind, column",
        [(kind, column) for kind, columns in REQUIRED.items() for column in columns],
    )
    def test_a_missing_required_column(self, csv_file, pdf_file, kind, column):
        attrs = {"path": str(pdf_file)} if kind == "pdf" else {}
        if kind == "range":
            attrs["rows"] = [{"id": "Ab12Cd", "name": "Old"}]
        target = holding_a_component(kind, attrs=attrs)
        doc = document(timelines=[target])
        header = ",".join(name for name in REQUIRED[kind] if name != column)

        failed = refused(
            doc, target.id, csv_file(f"{header},label\n1,1,1,a\n"), by="time"
        )

        assert (
            failed.message == f"Column '{column}' not found on first row of .csv file."
        )
        assert str(failed) == f"data.csv: {failed.message}"

    @pytest.mark.parametrize("kind", REQUIRED)
    def test_an_empty_file(self, csv_file, kind):
        target = holding_a_component(kind)
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(""), by="time")

        assert failed.message == "Can't import: file is empty."

    @pytest.mark.parametrize("kind", REQUIRED)
    def test_a_file_that_isnt_utf_8(self, tmp_path, kind):
        path = tmp_path / "data.csv"
        path.write_bytes("time\n1\ncaf\xe9\n".encode("latin-1"))
        target = holding_a_component(kind)
        doc = document(timelines=[target])

        failed = refused(doc, target.id, path, by="time")

        assert failed.message == f"'{path}' is not a valid UTF-8 encoded CSV file."

    @pytest.mark.parametrize("kind", REQUIRED)
    def test_a_document_with_no_media_length(self, csv_file, kind):
        target = holding_a_component(kind)
        doc = document(timelines=[target], media_length=None)

        failed = refused(doc, target.id, csv_file(), by="time")

        assert failed.message.startswith("No media loaded and no duration set.")

    @pytest.mark.parametrize("kind", REQUIRED)
    def test_a_file_that_cant_be_opened_is_left_to_the_caller(self, tmp_path, kind):
        # An OSError, as the importers raise it, for the caller to report.
        target = holding_a_component(kind)
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(OSError):
            importers.import_csv(doc, target.id, tmp_path / "none.csv", by="time")

        assert doc == before


class TestTheOrderOfTheChecks:
    """Of several faults, the first in the order target, `by`, reference, extra is
    reported (TimeLineAnnotator/project-management#484, 4A)."""

    def test_the_target_before_by(self, csv_file):
        target = timeline("beat", name="Measures")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="bar")

        assert failed.message.endswith(NOT_ONE_OF_THEM)

    def test_the_target_before_a_missing_reference(self, csv_file):
        target = timeline("beat", name="Measures")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="measure")

        assert failed.message.endswith(NOT_ONE_OF_THEM)

    def test_the_target_before_a_wrong_reference(self, csv_file):
        target = timeline("beat", name="Measures")
        reference = timeline("marker", name="Sections", ordinal=2)
        doc = document(timelines=[target, reference])

        failed = refused(
            doc, target.id, csv_file(), by="measure", reference=reference.id
        )

        assert failed.message.endswith(NOT_ONE_OF_THEM)

    def test_the_target_before_a_reference_the_document_doesnt_have(self, csv_file):
        target = timeline("beat", name="Measures")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="measure", reference="none")

        assert failed.message.endswith(NOT_ONE_OF_THEM)

    def test_a_target_the_document_doesnt_have_before_by(self, csv_file):
        doc = document(timelines=[timeline("marker")])

        failed = refused(doc, "none", csv_file(), by="bar")

        assert failed.message == "No timeline found with id=none"

    def test_by_before_a_missing_reference(self, csv_file):
        target = timeline("marker")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="bar")

        assert failed.message == BY

    def test_by_before_a_wrong_reference(self, csv_file):
        target = timeline("marker")
        reference = timeline("marker", ordinal=2)
        doc = document(timelines=[target, reference])

        failed = refused(doc, target.id, csv_file(), by="bar", reference=reference.id)

        assert failed.message == BY

    def test_by_before_the_extra(self, csv_file, without_the_extra):
        target = timeline("harmony")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="bar")

        assert failed.message == BY

    def test_a_missing_reference_before_the_extra(self, csv_file, without_the_extra):
        target = timeline("harmony")
        doc = document(timelines=[target])

        failed = refused(doc, target.id, csv_file(), by="measure")

        assert failed.message == BY_MEASURE

    def test_a_wrong_reference_before_the_extra(self, csv_file, without_the_extra):
        target = timeline("harmony")
        reference = timeline("marker", ordinal=2)
        doc = document(timelines=[target, reference])

        failed = refused(
            doc, target.id, csv_file(), by="measure", reference=reference.id
        )

        assert failed.message.endswith("is not a beat timeline")


class TestTheCsvIsNamed:
    def test_a_refusal_with_a_path_given_as_text_names_the_file(self, csv_file):
        target = timeline("beat", name="Measures")
        doc = document(timelines=[target])
        path = csv_file()

        failed = refused(doc, target.id, str(path), by="time")

        assert failed.path == path
        assert str(failed) == (
            f"data.csv: Beat timeline 'Measures' (ordinal 1) {NOT_ONE_OF_THEM}"
        )

    def test_a_refusal_of_by_with_a_path_given_as_text_names_the_file(self, csv_file):
        target = timeline("marker")
        doc = document(timelines=[target])
        path = csv_file()

        failed = refused(doc, target.id, str(path), by="bar")

        assert failed.path == path
        assert str(failed) == f"data.csv: {BY}"


class TestSurface:
    # Every name of the importers' contract that exists so far:
    # TimeLineAnnotator/project-management's specs/wp16-importers-command/
    # contracts/python-api.md and plan.md. `import_beats` joins them with its
    # own task.
    CONTRACT = [
        "IMPORTED_KINDS",
        "ImportFailed",
        "ImportResult",
        "RowProblem",
        "harmony_available",
        "import_csv",
        "import_metadata",
    ]

    def test_the_kinds_are_those_it_imports_into(self):
        assert importers.IMPORTED_KINDS == (
            "marker",
            "hierarchy",
            "range",
            "harmony",
            "pdf",
        )

    def test_all_holds_the_names_of_the_contract(self):
        assert sorted(importers.__all__) == sorted(self.CONTRACT)

    @pytest.mark.parametrize("name", CONTRACT)
    def test_each_name_can_be_imported_from_the_package(self, name):
        namespace = {}

        exec(f"from tilia_core.importers import {name}", namespace)

        assert namespace[name] is getattr(importers, name)

    def test_import_csv_takes_by_and_the_reference_as_keywords(self):
        parameters = inspect.signature(importers.import_csv).parameters

        assert list(parameters) == ["document", "target", "path", "by", "reference"]
        assert parameters["by"].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters["by"].default is inspect.Parameter.empty
        assert parameters["reference"].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters["reference"].default is None

    def test_the_functions_are_documented(self):
        assert importers.import_csv.__doc__
        assert importers.harmony_available.__doc__


class TestHarmonyAvailable:
    def test_with_music21(self, with_the_extra):
        assert harmony_available() is True

    def test_without_music21(self, without_the_extra):
        assert harmony_available() is False

    def test_it_imports_nothing(self, tmp_path, monkeypatch):
        (tmp_path / "music21.py").write_text("raise RuntimeError('imported')\n")
        monkeypatch.syspath_prepend(tmp_path)
        monkeypatch.delitem(sys.modules, "music21", raising=False)

        assert harmony_available() is True
        assert "music21" not in sys.modules
