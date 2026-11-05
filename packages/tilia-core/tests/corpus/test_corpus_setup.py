"""The corpus package and its test folder are in place."""

# Imported at the top, as tests here import WP13's helpers: pytest collects
# tests/corpus before tests/tql, so this import needs pyproject.toml's
# pythonpath, and fails at collection without it.
import examples

import tilia_core.corpus


def test_the_corpus_package_imports():
    assert tilia_core.corpus.__doc__.startswith("Corpora: a folder of TiLiA files")


def test_wp13s_helpers_import_by_their_bare_names():
    assert "exposition" in examples.load()["fixtures"]
