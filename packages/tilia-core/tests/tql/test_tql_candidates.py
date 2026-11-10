"""A file's units are read only where a unit of the query may fit: a timeline
where no component has the label is never loaded (SC-004's floor). The hints of
an empty result, which read the lanes on their own, are left out here."""

import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import hints, relations

FIXTURE = {
    "length": 60,
    "timelines": [
        {
            "name": "Form (X)",
            "kind": "hierarchy",
            "units": [
                ["S", 3, 0, 16],
                ["pres", 2, 0, 8],
                ["x", 1, 0, 4],
                ["cad", 1, 4, 8],
                ["cont", 2, 8, 16],
                ["cad", 1, 8, 12],
                ["x", 1, 12, 16],
            ],
        },
        {"name": "Cadences", "kind": "marker", "units": [["PAC", 8], ["HC", 16]]},
        {
            "name": "Beats",
            "kind": "beats",
            "start": 0,
            "every": 0.25,
            "beats_per_bar": 4,
            "bars": 60,
        },
    ],
}


@pytest.fixture
def loaded(monkeypatch):
    """The names of the timelines the search loads units of."""
    monkeypatch.setattr(hints, "empty", lambda *args: [])
    names = []
    timeline = relations.Scope.timeline

    def spy(self, timeline_id):
        if timeline_id not in self._timelines:
            names.append(self.facts.timeline(timeline_id).get("name"))
        return timeline(self, timeline_id)

    monkeypatch.setattr(relations.Scope, "timeline", spy)
    return names


@pytest.mark.parametrize(
    "query",
    [
        "ST[CONSISTS OF pres THEN cont] IN form",
        "ST[CONTAINS cad] IN form",
        "ST THEN TR IN form",
        "ST[duration >= 4 bars]",
    ],
)
def test_a_label_no_unit_has_loads_no_unit(loaded, query):
    got = tql.run(fixture_index.build_index(FIXTURE), query)
    assert got.matches == []
    assert loaded == []


def test_a_unit_is_read_only_in_the_timelines_where_its_label_is(loaded):
    got = tql.run(fixture_index.build_index(FIXTURE), "PAC THEN HC")
    assert [[c.label for c in s] for m in got.matches for s in m.slots] == [
        ["PAC"],
        ["HC"],
    ]
    assert loaded == ["Cadences"]
