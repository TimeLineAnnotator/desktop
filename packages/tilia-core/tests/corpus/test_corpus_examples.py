"""TQL's printed examples on their fixtures written as real ``.tla`` files
(SC-003; TimeLineAnnotator/project-management#154).

Each fixture of ``examples.toml`` is built as ``corpus_docs`` builds it, written
with ``tla.write``, and opened with ``open_corpus`` and its default reader,
WP3's. The examples that need bars get WP13's fake time map of the fixture's
beat timeline, found in the file read by its name; every example then gives the
rows the list gives, as ``tests/tql/test_tql_examples.py`` runs them on the
fixture index."""

from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import corpus_docs
import examples
import pytest
from fake_timemap import FakeTimeMap
from grammars import GRAMMARS
from tla_files import as_tla

from tilia_core import labels, open_corpus, tla, tql
from tilia_core.corpus.documents import Document
from tilia_core.corpus.settings import NoSettings

DATA = examples.load()
PENDING_FILE = Path(examples.__file__).with_name("examples_pending.txt")


def _pending() -> dict[int, str]:
    out: dict[int, str] = {}
    for line in PENDING_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            n, _, reason = line.partition(":")
            out[int(n)] = reason.strip()
    return out


PENDING = _pending()


def time_maps(fixture: dict):
    """A ``time_map_of`` for the file of ``fixture``: the fake time map of its
    beat timeline whose role is ``time_map``, else of its first, by the
    timeline's name in the fixture."""
    grids = {tl["name"]: tl for tl in fixture["timelines"] if tl["kind"] == "beats"}

    def time_map_of(document: Document, roles: Mapping[str, str | None]):
        beats = [tl for tl in document.timelines if tl.kind == "beat"]
        chosen = [tl for tl in beats if roles.get(tl.id) == "time_map"]
        if not (chosen or beats):
            return None
        tl = (chosen or beats)[0]
        fake = FakeTimeMap.from_fixture(grids[tl.name])
        fake.timeline_id, fake.guessed = tl.id, not chosen
        return fake

    return time_map_of


class Grammar(NoSettings):
    """The fixture's label grammar, as the corpus manifest will give it (WP15)."""

    def __init__(self, fixture: dict) -> None:
        name = fixture.get("grammar")
        self._grammar = GRAMMARS[name] if name else labels.WholeLabel()

    def grammar(self, timeline, document):
        return self._grammar


_corpora: dict[str, object] = {}


@pytest.fixture(scope="module")
def corpus_of(tmp_path_factory):
    def corpus(name: str):
        if name not in _corpora:
            fixture = DATA["fixtures"][name]
            if any(tl["kind"] == "harmony" for tl in fixture["timelines"]):
                # the writer checks keys and chords with music21
                pytest.importorskip("music21", reason="needs the harmony extra")
            folder = tmp_path_factory.mktemp(f"examples-{name}")
            document = corpus_docs.document_from_fixture(fixture)
            tla.write(folder / f"{name}.tla", as_tla(document))
            _corpora[name] = open_corpus(
                folder,
                rescan_before_reads=False,
                settings=Grammar(fixture),
                time_map_of=time_maps(fixture),
            )
        return _corpora[name]

    yield corpus
    for opened in _corpora.values():
        opened.close()
    _corpora.clear()


def _label(corpus, component) -> str:
    """A chord by its Roman numeral, as the examples print it (see
    ``test_tql_examples._label``)."""
    if component.kind != "chord":
        return component.label
    with corpus.reading() as r:
        (roman,) = r.connection.execute(
            "SELECT roman FROM chords WHERE component_id = ?", (component.id,)
        ).fetchone()
    return roman


def _row(corpus, match: tql.Match, has_target: bool) -> str:
    steps = []
    for n, slot in enumerate(match.slots):
        units = []
        for k, c in enumerate(slot):
            text = f"{_label(corpus, c)}@{c.start:g}"
            units.append(
                f"[{text}]" if has_target and match.is_target(n + 1, k) else text
            )
        if units:
            steps.append(", ".join(units))
    return " | ".join(steps)


def _rows(corpus, result: tql.Result, has_target: bool) -> list[str]:
    if result.grain == "timeline":
        return [r["timeline"] for r in result.rows]
    return [_row(corpus, m, has_target) for m in result.matches]


def _params():
    out = []
    for e in DATA["examples"]:
        marks = []
        if e.n in PENDING:
            marks.append(pytest.mark.xfail(strict=True, reason=PENDING[e.n]))
        out.append(pytest.param(e, id=str(e.n), marks=marks))
    return out


@pytest.mark.parametrize("name", sorted({e.fixture for e in DATA["examples"]}))
def test_every_fixture_is_one_readable_file(corpus_of, name):
    (row,) = corpus_of(name).files()
    assert row.state == "readable", row.reason


@pytest.mark.parametrize("example", _params())
def test_example(corpus_of, example):
    corpus = corpus_of(example.fixture)
    result = tql.run(corpus, example.query)
    has_target = tql.parse(example.query).has_target
    assert Counter(_rows(corpus, result, has_target)) == Counter(example.rows)
