"""Queries on a corpus opened from files: WP13's printed examples of the fixtures
``exposition`` and ``pop``, written as stand-in files (User Story 1)."""

import unicodedata
from collections import Counter
from pathlib import Path

import corpus_docs
import examples
import fake_timemap
import pytest
from grammars import GRAMMARS
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus.settings import NoSettings

DATA = examples.load()
FIXTURES = ("exposition", "pop")
PENDING_FILE = Path(examples.__file__).with_name("examples_pending.txt")


def _pending() -> dict[int, str]:
    out = {}
    for line in PENDING_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            n, _, reason = line.partition(":")
            out[int(n)] = reason.strip()
    return out


PENDING = _pending()


class Settings(NoSettings):
    """The label grammar a fixture names."""

    def __init__(self, grammar):
        self._grammar = grammar

    def grammar(self, timeline, document):
        return self._grammar or super().grammar(timeline, document)


@pytest.fixture(scope="module")
def corpora(tmp_path_factory):
    out = {}
    for name in FIXTURES:
        fixture = DATA["fixtures"][name]
        folder = tmp_path_factory.mktemp(name)
        corpus_docs.write_doc(
            folder / f"{name}.tla", corpus_docs.document_from_fixture(fixture)
        )
        grammar = GRAMMARS[fixture["grammar"]] if "grammar" in fixture else None
        out[name] = open_corpus(
            folder,
            reader=JsonDocumentReader(),
            settings=Settings(grammar),
            time_map_of=fake_timemap.time_map_of,
            rescan_before_reads=False,
        )
    yield out
    for corpus in out.values():
        corpus.close()


# The rows as WP13's tests/tql/test_tql_examples.py prints them.
def _unit(component, marked):
    text = f"{component.label}@{component.start:g}"
    return f"[{text}]" if marked else text


def _row(match, has_target):
    steps = []
    for n, slot in enumerate(match.slots):
        units = [
            _unit(c, has_target and match.is_target(n + 1, k))
            for k, c in enumerate(slot)
        ]
        if units:
            steps.append(", ".join(units))
    return " | ".join(steps)


def _rows(result, has_target):
    if result.grain == "timeline":
        return [r["timeline"] for r in result.rows]
    return [_row(m, has_target) for m in result.matches]


def _params():
    out = []
    for e in DATA["examples"]:
        if e.fixture not in FIXTURES:
            continue
        marks = []
        if e.n in PENDING:
            marks.append(pytest.mark.xfail(strict=True, reason=PENDING[e.n]))
        out.append(pytest.param(e, id=str(e.n), marks=marks))
    return out


def test_one_of_pops_examples_needs_bars():
    assert any(e.fixture == "pop" and "bar" in e.query for e in DATA["examples"])


@pytest.mark.parametrize("example", _params())
def test_example(corpora, example):
    result = tql.run(corpora[example.fixture], example.query)
    has_target = tql.parse(example.query).has_target
    assert Counter(_rows(result, has_target)) == Counter(example.rows)


def test_a_label_written_in_nfd_is_found_by_the_word_in_nfc(tmp_path):
    nfd = unicodedata.normalize("NFD", "Café")
    assert nfd != "Café"
    doc = corpus_docs.document(
        corpus_docs.hierarchy([[nfd, 1, 0, 10]], fields={"role": "form"}),
        document_id="nfd",
    )
    corpus_docs.write_doc(tmp_path / "a.tla", doc)
    with open_corpus(tmp_path, reader=JsonDocumentReader()) as corpus:
        result = tql.run(corpus, '"Café" IN form')
        assert [m.slots[0][0].label for m in result.matches] == ["Café"]
