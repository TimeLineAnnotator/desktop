"""The shared examples: beat timelines with the meters and quarter stamps that
desktop#621's code gives them, for the core's tests and the app's. The beat
values, flags and quarter stamps are computed by running #621's code, never
written by hand. #621 has no text form of a time signature: `time_signature`
is its values written by format_time_signature, which this file can't check
against itself; test_timemap_table.py checks it against texts written by hand.

A case that passes on one side only means the two copies of the rules differ:
fix one side, never the expected values alone.
"""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from docs import beat_timeline, document
from tilia_core.timemap import time_map_for
from tilia_core.timemap.table import build_rows

EXAMPLES = json.loads(
    Path(__file__).with_name("shared_examples.json").read_text(encoding="utf-8")
)
METERS = [pytest.param(case, id=case["name"]) for case in EXAMPLES["meters"]]

# The cases the spec asks for, by the names the file gives them.
REQUIRED = [
    "the default unit",
    "a pickup",
    "6/8 tapped in two, before its unit is set",
    "6/8 tapped in two, after a 3/8 pickup",
    "6/8 tapped in six",
    "2+3 over two taps",
    "1/2: eighths tapped in 2/4",
    "a unit changing in mid-piece",
    "a unit set on a later beat of its measure",
    "two units in one measure",
    "an ambiguous fit: three taps under 2+3",
    "a pickup holding the end of a pattern",
    "a numerator that isn't whole: 1/3 over four taps",
    "no unit in the first measures, and one in a later measure",
    "no unit at all",
]


def test_the_file_holds_every_case_the_spec_asks_for():
    names = [case["name"] for case in EXAMPLES["meters"]]

    assert [name for name in REQUIRED if name not in names] == []
    assert len(set(names)) == len(names)


@pytest.mark.parametrize("case", METERS)
def test_each_case_is_laid_out_as_the_contract_says(case):
    beats = case["beats"]
    times = [beat["time"] for beat in beats]

    assert beats[0].get("measure") is not None
    assert times == sorted(set(times))
    assert len(case["expected"]["meters"]) == sum(
        beat.get("measure") is not None for beat in beats
    )
    assert len(case["expected"]["qstamps"]) == len(beats)


@pytest.mark.parametrize("case", METERS)
def test_meters(case):
    timeline = beat_timeline(case["beats"])
    rows = build_rows(document(timeline), timeline)

    assert [_meter(row) for row in rows] == [
        {**meter, "beat_values": [Fraction(value) for value in meter["beat_values"]]}
        for meter in case["expected"]["meters"]
    ]


def _meter(row):
    return {
        "time_signature": row.time_signature,
        "beat_values": list(row.meter.beat_values),
        "assumed": row.assumed,
        "ambiguous": row.ambiguous,
        "conflicting": row.conflicting,
    }


@pytest.mark.parametrize("case", METERS)
def test_qstamps(case):
    # At a beat, the time map's qstamp is the exact stamp as a float, as #621's
    # get_quarter_stamp_by_time gives it; the rows hold the downbeats' exactly.
    timeline = beat_timeline(case["beats"])
    time_map = time_map_for(document(timeline), timeline.id)
    expected = [Fraction(qstamp) for qstamp in case["expected"]["qstamps"]]

    assert [time_map.qstamp(beat["time"]) for beat in case["beats"]] == [
        float(qstamp) for qstamp in expected
    ]
    downbeats = [
        k for k, beat in enumerate(case["beats"]) if beat.get("measure") is not None
    ]
    assert [row.qstamp for row in time_map.measure_rows()] == [
        expected[k] for k in downbeats
    ]
    # The last bar lasts as many quarter notes in the map as in its row:
    # TimeLineAnnotator/project-management#325 (a last beat's length).
    last = time_map.measure_rows()[-1]
    assert time_map.quarters(last.start, last.end) == pytest.approx(
        float(last.quarters)
    )
