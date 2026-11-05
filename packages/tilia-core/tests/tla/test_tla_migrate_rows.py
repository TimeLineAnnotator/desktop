"""The migration strips a row's defaults only on a timeline that has rows."""

import json

from tilia_core import tla

ROW = {"id": "Dw5p2E", "name": "Row 0", "color": None, "height": None}


def old_file(kind, component, **timeline_attrs):
    return {
        "file_path": "",
        "media_path": "",
        "media_metadata": {"title": "Piece"},
        "timelines": {
            "1": {
                "kind": kind,
                "name": "Analysis",
                "ordinal": 1,
                "height": 30,
                "is_visible": True,
                **timeline_attrs,
                "components": {"2": component},
            }
        },
        "app_name": "TiLiA",
        "version": "0.6.0",
    }


def migrated_timeline(content):
    doc = tla.loads(json.dumps(content).encode())
    stored = json.loads(tla.canonical_bytes(doc))
    (timeline,) = stored["timelines"].values()
    return timeline


def marker(**attrs):
    component = {"kind": "MARKER", "time": 5, "label": "PAC", "hash": "0e1f"}
    return old_file("Marker", component, **attrs)


def test_an_unknown_rows_key_on_a_marker_timeline_stays_as_it_is():
    timeline = migrated_timeline(marker(rows=[dict(ROW)]))

    assert timeline["rows"] == [ROW]


def test_a_range_timeline_loses_the_defaults_in_its_rows():
    component = {
        "kind": "RANGE",
        "start": 0,
        "end": 1,
        "row_id": "Dw5p2E",
        "hash": "0e1f",
    }
    timeline = migrated_timeline(old_file("Range", component, rows=[dict(ROW)]))

    assert timeline["rows"] == [{"id": "Dw5p2E", "name": "Row 0"}]
