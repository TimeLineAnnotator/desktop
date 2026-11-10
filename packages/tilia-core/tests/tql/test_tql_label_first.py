"""SQL tests a unit's label before the rest of its brackets: a measure in bars
or beats is taken only of the components with the label."""

import fixture_index
from fake_timemap import FakeTimeMap

from tilia_core import tql

FIXTURE = {
    "length": 120,
    "timelines": [
        {
            "name": "Form (X)",
            "kind": "hierarchy",
            "units": [["ant", 1, 0, 16]]
            + [["b", 1, 16 + 4 * i, 20 + 4 * i] for i in range(20)],
        },
        {"name": "Notes", "kind": "marker", "units": [["n", i] for i in range(100)]},
        {
            "name": "Beats",
            "kind": "beats",
            "start": 0,
            "every": 1,
            "beats_per_bar": 4,
            "bars": 30,
        },
    ],
}


def test_a_length_in_bars_is_measured_only_of_the_units_with_the_label(monkeypatch):
    calls = []
    length = FakeTimeMap.length

    def counting(self, start, end, unit="bar"):
        calls.append((start, end))
        return length(self, start, end, unit)

    index = fixture_index.build_index(FIXTURE)
    monkeypatch.setattr(FakeTimeMap, "length", counting)
    got = tql.run(index, "ant[duration = 4 bars] IN form")
    assert [(c.label, c.start) for m in got.matches for s in m.slots for c in s] == [
        ("ant", 0)
    ]
    assert calls == [(0, 16)]
    assert "CASE WHEN" in got.sql


def test_a_unit_without_the_label_or_the_length_fits_nothing():
    index = fixture_index.build_index(FIXTURE)
    assert tql.run(index, "ant[duration = 3 bars] IN form").matches == []
    assert tql.run(index, "zzz[duration = 4 bars] IN form").matches == []
    got = tql.run(index, "b[duration = 1 bars] IN form")
    assert len(got.matches) == 20
