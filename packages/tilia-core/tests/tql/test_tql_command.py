"""`tilia query` (User Story 7, FR-045–FR-047), through the `tilia` command's own
entry point, with PySide6 and the app blocked.

Until WP3's reader is the index's default (TimeLineAnnotator/project-management#185),
`open_corpus` reads no `.tla` file without a reader, so these tests run the
command with the corpus tests' stand-in reader, which reads documents written as
JSON (`tests/corpus/json_reader.py`). Each run is a fresh interpreter: it blocks
PySide6, shiboken6 and `tilia` before anything is imported, gives `open_corpus`
the stand-in reader, and calls `tilia_core.commands.main`, which finds `query`
among the installed entry points."""

import csv
import io
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import corpus_docs
import examples
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql

TESTS = Path(__file__).resolve().parent.parent
HELPERS = [str(TESTS / "corpus"), str(TESTS / "tql")]
FIXTURES = examples.load()["fixtures"]
MATCH_COLUMNS = [
    "path",
    "title",
    "timeline",
    "lane",
    "label",
    "start",
    "end",
    "bar",
    "beat",
]

RUNNER = """
import importlib.abc
import sys

BLOCKED = ("PySide6", "shiboken6", "tilia")


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in BLOCKED:
            raise ImportError(f"{fullname} is blocked")
        return None


sys.meta_path.insert(0, Blocker())
mode, *arguments = sys.argv[1:]

from functools import partial

from tilia_core import corpus, tql

if mode != "no-reader":
    from json_reader import JsonDocumentReader

    corpus.open_corpus = partial(corpus.open_corpus, reader=JsonDocumentReader())
if mode == "interrupted":
    # A Ctrl+C as the run starts: the command's handler sets `cancel`.
    import signal

    run = tql.run

    def interrupted(*args, **kwargs):
        signal.raise_signal(signal.SIGINT)
        return run(*args, **kwargs)

    tql.run = interrupted

from tilia_core.commands import main

sys.argv = ["tilia", *arguments]
sys.exit(main())
"""


def tilia(*arguments, cwd, mode="reader", encoding="utf-8"):
    """Run `tilia` with `arguments`, as a user would, but with the stand-in
    reader (`mode` "reader"), without one ("no-reader"), or with a Ctrl+C as
    the query starts ("interrupted"). Its output is bytes with `encoding`
    None, as for CSV."""
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": os.pathsep.join(HELPERS),
    }
    return subprocess.run(
        [sys.executable, "-c", RUNNER, mode, *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding=encoding,
        timeout=120,
    )


def write_fixture(folder, name):
    document = corpus_docs.document_from_fixture(FIXTURES[name])
    corpus_docs.write_doc(folder / f"{name}.tla", document)
    return folder


@pytest.fixture
def exposition(tmp_path):
    return write_fixture(tmp_path / "exposition", "exposition")


@pytest.fixture
def harmony(tmp_path):
    return write_fixture(tmp_path / "harmony", "harmony")


def expected(folder, query, **limits):
    """What `tql.run` gives for `query` on `folder`, read as the command reads it."""
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        return tql.run(corpus, query, **limits)


def expected_stats(folder, query, name, **options):
    """The statistics table `name` of `query`'s matches on `folder`."""
    with open_corpus(folder, reader=JsonDocumentReader()) as corpus:
        return tql.run(corpus, query).stats(name, **options)


def table(text):
    """The cells of an aligned table, column by column as its header places
    them: a list of dicts, one per row."""
    header, *lines = text.splitlines()
    names = header.split()
    starts = [header.index(name) for name in names]
    ends = [*starts[1:], None]
    return [
        {
            name: line[start:end].strip()
            for name, start, end in zip(names, starts, ends, strict=True)
        }
        for line in lines
    ]


def header(text):
    return text.splitlines()[0].split()


def cell(column, value):
    """A value as the table prints it: times with three decimals, None empty."""
    if value is None:
        return ""
    if column in ("start", "end"):
        return f"{value:.3f}"
    return str(value)


# -- the command and its help ------------------------------------------------- #
def test_tilia_help_lists_query(tmp_path):
    result = tilia("--help", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "  query" in result.stdout.splitlines()


def test_the_installed_tilia_lists_query():
    script = shutil.which("tilia", path=sysconfig.get_path("scripts"))
    assert script is not None

    result = subprocess.run(
        [script, "--help"], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert "  query" in result.stdout.splitlines()


def test_query_help_exits_0_and_lists_the_options(tmp_path):
    result = tilia("query", "--help", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: tilia query")
    for option in (
        "--file",
        "--csv",
        "--stats",
        "--by",
        "--fold-subtypes",
        "--sql",
        "--explain",
        "--max-matches",
        "--time-limit",
        "--labels",
        "--help",
    ):
        assert option in result.stdout
    assert result.stderr == ""


# -- wrong use: status 2 ------------------------------------------------------ #
@pytest.mark.parametrize(
    "folder,message",
    [
        ("nowhere", "no such folder: nowhere"),
        ("exposition.tla", "not a folder: exposition.tla"),
    ],
)
def test_a_folder_that_isnt_one_exits_2_and_names_it(exposition, folder, message):
    result = tilia("query", folder, "* IN form", cwd=exposition)

    assert result.returncode == 2
    assert message in result.stderr
    assert result.stdout == ""


def test_an_unknown_option_exits_2_and_names_it(exposition):
    result = tilia("query", ".", "* IN form", "--colour", cwd=exposition)

    assert result.returncode == 2
    assert "--colour" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("arguments", [(), (".",)])
def test_a_missing_argument_exits_2(exposition, arguments):
    result = tilia("query", *arguments, cwd=exposition)

    assert result.returncode == 2
    assert "usage: tilia query" in result.stderr


def test_too_many_arguments_exit_2(exposition):
    result = tilia("query", ".", "* IN form", "more", cwd=exposition)

    assert result.returncode == 2
    assert "more" in result.stderr


def test_a_malformed_query_prints_format_errors_text_and_exits_2(exposition):
    text = "verse THEN"
    with pytest.raises(tql.TQLError) as error:
        tql.parse(text)

    result = tilia("query", ".", text, cwd=exposition)

    assert result.returncode == 2
    assert result.stderr == tql.format_error(text, error.value) + "\n"
    assert result.stdout == ""


def test_a_lane_the_corpus_lacks_prints_format_errors_text_and_exits_2(exposition):
    text = "verse IN nowhere"
    with open_corpus(exposition, reader=JsonDocumentReader()) as corpus:
        with pytest.raises(tql.TQLError) as error:
            tql.run(corpus, text)

    result = tilia("query", ".", text, cwd=exposition)

    assert result.returncode == 2
    assert result.stderr == tql.format_error(text, error.value) + "\n"


def test_a_malformed_query_in_a_file_names_the_file_and_the_line(exposition):
    text = "-- a reserved word as a label\nthen THEN coda IN form\n"
    (exposition.parent / "q.tql").write_text(text, encoding="utf-8")
    with pytest.raises(tql.TQLError) as error:
        tql.parse(text)

    result = tilia("query", ".", "--file", "../q.tql", cwd=exposition)

    assert result.returncode == 2
    assert result.stderr == (
        "../q.tql, line 2: " + tql.format_error(text, error.value) + "\n"
    )


def test_a_query_file_that_doesnt_exist_exits_2_and_names_it(exposition):
    result = tilia("query", ".", "--file", "missing.tql", cwd=exposition)

    assert result.returncode == 2
    assert "missing.tql" in result.stderr


def test_a_query_and_a_query_file_together_exit_2(exposition):
    (exposition / "q.tql").write_text("PAC IN cadences", encoding="utf-8")

    result = tilia("query", ".", "PAC IN cadences", "--file", "q.tql", cwd=exposition)

    assert result.returncode == 2


@pytest.mark.parametrize(
    "option,value",
    [("--max-matches", "0"), ("--max-matches", "x"), ("--time-limit", "-1")],
)
def test_a_limit_that_isnt_one_exits_2(exposition, option, value):
    result = tilia("query", ".", "* IN form", option, value, cwd=exposition)

    assert result.returncode == 2
    assert option in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        ("--by", "label"),
        ("--fold-subtypes",),
        ("--sql", "--stats", "counts"),
        ("--sql", "--csv"),
    ],
)
def test_options_that_dont_go_together_exit_2(exposition, arguments):
    result = tilia("query", ".", "* IN form", *arguments, cwd=exposition)

    assert result.returncode == 2
    assert result.stdout == ""


def test_an_unknown_statistics_key_exits_2(exposition):
    result = tilia(
        "query", ".", "* IN form", "--stats", "counts", "--by", "colour", cwd=exposition
    )

    assert result.returncode == 2
    assert "colour" in result.stderr


# -- rows ---------------------------------------------------------------------- #
def test_the_rows_printed_are_tql_runs(exposition):
    query = "* THEN @TR THEN * IN form"
    rows = expected(exposition, query).rows
    assert len(rows) == 2

    result = tilia("query", ".", query, cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    printed = table(result.stdout)
    columns = header(result.stdout)
    assert columns == MATCH_COLUMNS
    assert printed == [{c: cell(c, row[c]) for c in columns} for row in rows]


def test_a_table_as_printed(exposition):
    result = tilia("query", ".", "PAC IN cadences", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "path            title  timeline  lane  label  start   end     bar  beat\n"
        "exposition.tla         Cadences        PAC    21.500  21.500\n"
    )


def test_a_query_without_matches_prints_the_header(exposition):
    result = tilia("query", ".", "coda IN form", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert header(result.stdout) == MATCH_COLUMNS
    assert len(result.stdout.splitlines()) == 1


def test_a_query_of_timelines_prints_their_columns(exposition):
    query = "WHERE tl.role = form"
    rows = expected(exposition, query).rows

    result = tilia("query", ".", query, cwd=exposition)

    assert result.returncode == 0, result.stderr
    columns = header(result.stdout)
    assert columns == ["path", "title", "timeline", "kind", "role", "author"]
    assert table(result.stdout) == [
        {c: cell(c, row[c]) for c in columns} for row in rows
    ]


def test_csv_on_standard_output_is_to_csvs_bytes(exposition, tmp_path):
    query = "* THEN @TR THEN * IN form"
    expected(exposition, query).to_csv(tmp_path / "expected.csv")

    result = tilia("query", ".", query, "--csv", cwd=exposition, encoding=None)

    assert result.returncode == 0, result.stderr
    assert result.stdout == (tmp_path / "expected.csv").read_bytes()


def test_csv_to_a_file_is_to_csvs_bytes(exposition, tmp_path):
    query = "* IN form"
    expected(exposition, query).to_csv(tmp_path / "expected.csv")

    result = tilia("query", ".", query, "--csv", "../out.csv", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (tmp_path / "out.csv").read_bytes() == (
        tmp_path / "expected.csv"
    ).read_bytes()


def test_a_query_from_a_file(exposition):
    (exposition.parent / "q.tql").write_text(
        "-- the cadences\nPAC IN cadences\n", encoding="utf-8"
    )

    by_file = tilia("query", ".", "--file", "../q.tql", cwd=exposition)
    by_argument = tilia("query", ".", "PAC IN cadences", cwd=exposition)

    assert by_file.returncode == 0, by_file.stderr
    assert by_file.stdout == by_argument.stdout


def test_a_query_file_names_the_folder_after_the_option(exposition):
    (exposition / "q.tql").write_text("PAC IN cadences", encoding="utf-8")

    result = tilia("query", "--file", "q.tql", ".", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert "PAC" in result.stdout


# -- chord labels ----------------------------------------------------------- #
def test_chords_print_their_symbols_by_default(harmony):
    query = "V7 THEN I IN harmony"
    rows = expected(harmony, query).rows

    result = tilia("query", ".", query, cwd=harmony)

    assert result.returncode == 0, result.stderr
    assert [r["label"] for r in table(result.stdout)] == [r["symbol"] for r in rows]
    assert tilia("query", ".", query, "--labels", "letter", cwd=harmony).stdout == (
        result.stdout
    )


def test_labels_roman_prints_roman_numerals(harmony):
    query = "V7 THEN I IN harmony"
    rows = expected(harmony, query).rows

    result = tilia("query", ".", query, "--labels", "roman", cwd=harmony)

    assert result.returncode == 0, result.stderr
    assert [r["label"] for r in table(result.stdout)] == [r["roman"] for r in rows]
    assert "V7 → I" in result.stdout


def test_labels_roman_in_csv(harmony):
    query = "V7 THEN I IN harmony"
    rows = expected(harmony, query).rows

    result = tilia("query", ".", query, "--labels", "roman", "--csv", cwd=harmony)

    assert result.returncode == 0, result.stderr
    read = list(csv.DictReader(io.StringIO(result.stdout)))
    assert [r["label"] for r in read] == [r["roman"] for r in rows]
    assert [r["symbol"] for r in read] == [r["symbol"] for r in rows]


def test_labels_other_than_letter_or_roman_exit_2(harmony):
    result = tilia("query", ".", "* IN harmony", "--labels", "symbol", cwd=harmony)

    assert result.returncode == 2
    assert "--labels" in result.stderr


# -- statistics, SQL and explain ---------------------------------------------- #
def test_stats_prints_the_statistics_table(harmony):
    query = "V7 THEN I IN harmony"
    stats = expected_stats(harmony, query, "counts")

    result = tilia("query", ".", query, "--stats", "counts", cwd=harmony)

    assert result.returncode == 0, result.stderr
    assert header(result.stdout) == stats.columns
    assert table(result.stdout) == [
        {c: str(v) for c, v in zip(stats.columns, row, strict=True)}
        for row in stats.rows
    ]


def test_stats_by_two_keys(harmony):
    query = "V7 THEN I IN harmony"
    stats = expected_stats(harmony, query, "counts", by=["label", "file"])

    result = tilia(
        "query", ".", query, "--stats", "counts", "--by", "label,file", cwd=harmony
    )

    assert result.returncode == 0, result.stderr
    assert header(result.stdout) == stats.columns
    assert len(table(result.stdout)) == len(stats.rows)


def test_stats_in_csv_is_the_tables_to_csv(exposition, tmp_path):
    query = "* IN form"
    stats = expected_stats(
        exposition, query, "counts", by="category", fold_subtypes=True
    )
    stats.to_csv(tmp_path / "expected.csv")

    result = tilia(
        "query",
        ".",
        query,
        "--stats",
        "counts",
        "--by",
        "category",
        "--fold-subtypes",
        "--csv",
        cwd=exposition,
        encoding=None,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (tmp_path / "expected.csv").read_bytes()


def test_sql_prints_the_results_sql(exposition):
    query = "MT THEN TR IN form"
    sql = expected(exposition, query).sql

    result = tilia("query", ".", query, "--sql", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert result.stdout == sql + "\n"


@pytest.mark.parametrize(
    "folder", [(), ("nowhere",)], ids=["needs-none", "reads-none-given"]
)
def test_explain_needs_no_folder(tmp_path, folder):
    query = "verse THEN chorus IN form"

    result = tilia("query", "--explain", *folder, query, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == tql.explain(tql.parse(query)) + "\n"


def test_explain_of_a_malformed_query_exits_2(tmp_path):
    result = tilia("query", "--explain", "verse THEN", cwd=tmp_path)

    assert result.returncode == 2
    assert "^" in result.stderr


# -- what the run couldn't do --------------------------------------------------- #
def test_an_unreadable_file_is_named_with_its_line_and_exits_1(exposition):
    (exposition / "broken.tla").write_text("{\n  nope\n", encoding="utf-8")
    rows = expected(exposition, "PAC IN cadences").rows

    result = tilia("query", ".", "PAC IN cadences", cwd=exposition)

    assert result.returncode == 1
    err = result.stderr.splitlines()
    assert err[0].startswith("broken.tla: can't read (line 2): not valid JSON")
    assert err[1:] == ["warning: 1 file was left out: 1 unreadable"]
    assert [r["path"] for r in table(result.stdout)] == [r["path"] for r in rows]


def test_an_unreadable_file_in_a_subfolder_is_named_by_its_path(exposition):
    (exposition / "sub").mkdir()
    (exposition / "sub" / "broken.tla").write_text("{", encoding="utf-8")

    result = tilia("query", ".", "PAC IN cadences", cwd=exposition)

    assert result.returncode == 1
    assert result.stderr.startswith("sub/broken.tla: can't read")


def test_files_that_cant_answer_a_condition_warn_and_exit_0(exposition):
    query = "* IN form WHERE bar = 1"
    warnings = expected(exposition, query).warnings
    assert warnings

    result = tilia("query", ".", query, cwd=exposition)

    assert result.returncode == 0
    assert result.stderr.splitlines() == [f"warning: {w}" for w in warnings]


def test_a_run_stopped_by_max_matches_says_some_and_exits_1(exposition):
    query = "* IN form"
    rows = expected(exposition, query, max_matches=2).rows
    assert len(rows) == 2

    result = tilia("query", ".", query, "--max-matches", "2", cwd=exposition)

    assert result.returncode == 1
    assert result.stderr == "stopped: some 2 matches (--max-matches)\n"
    assert len(table(result.stdout)) == 2


def test_a_time_limit_that_isnt_reached_changes_nothing(exposition):
    plain = tilia("query", ".", "* IN form", cwd=exposition)

    result = tilia("query", ".", "* IN form", "--time-limit", "60", cwd=exposition)

    assert result.returncode == 0, result.stderr
    assert result.stdout == plain.stdout


def test_ctrl_c_cancels_the_run_prints_what_was_found_and_exits_1(exposition):
    result = tilia("query", ".", "* IN form", cwd=exposition, mode="interrupted")

    assert result.returncode == 1
    assert result.stderr == "stopped: some 0 matches (cancelled)\n"
    assert header(result.stdout)[0] == "path"


def test_without_a_tla_reader_it_says_so_and_exits_1(exposition):
    # Until TimeLineAnnotator/project-management#185 makes WP3's reader the
    # index's default, open_corpus reads no .tla file without one.
    result = tilia("query", ".", "* IN form", cwd=exposition, mode="no-reader")

    assert result.returncode == 1
    assert result.stderr.startswith("tilia query: no .tla reader yet")
    assert result.stdout == ""
