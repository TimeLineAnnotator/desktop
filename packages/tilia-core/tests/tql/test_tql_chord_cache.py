"""A chord or key literal is matched once per distinct set of chord or key
columns, however many units have them."""

import examples
import fixture_index

from tilia_core import harmony, tql
from tilia_core.tql import sqlfuncs

FIXTURES = examples.load()["fixtures"]


def test_a_chord_literal_is_matched_once_per_distinct_chord(monkeypatch):
    calls = []
    chord_matches = harmony.chord_matches

    def counting(spec, chord, key):
        calls.append((spec, tuple(chord.values()), tuple(key.values())))
        return chord_matches(spec, chord, key)

    monkeypatch.setattr(harmony, "chord_matches", counting)
    getattr(sqlfuncs.tql_chord, "cache_clear", lambda: None)()
    index = fixture_index.build_index(*([FIXTURES["harmony"]] * 4))
    one = tql.run(index, "V THEN I IN harmony")
    assert len(calls) == len(set(calls))  # four files, the chords of one
    assert one.matches and len(one.matches) % 4 == 0
    again = tql.run(index, "V THEN I IN harmony")
    assert [m.slots for m in again.matches] == [m.slots for m in one.matches]
    assert len(calls) == len(set(calls))
