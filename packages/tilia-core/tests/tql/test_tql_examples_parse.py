import examples
import pytest

from tilia_core import tql

EXAMPLES = examples.load()["examples"]


@pytest.mark.parametrize("example", EXAMPLES, ids=[f"{e.n}" for e in EXAMPLES])
def test_example_parses_and_is_explained(example):
    sentence = tql.explain(tql.parse(example.query))
    assert sentence and sentence.endswith("."), sentence
