import json
from pathlib import Path


def get_blank_file_data():
    return {
        "file_path": "",
        "media_path": "",
        "media_metadata": {
            "title": "Untitled",
            "notes": "",
            "composer": "",
            "tonality": "",
            "time signature": "",
            "performer": "",
            "performance year": "",
            "arranger": "",
            "composition year": "",
            "recording year": "",
            "form": "",
            "instrumentation": "",
            "genre": "",
            "lyrics": ""
        },
        "timelines": {
            "0": {
                "is_visible": True,
                "ordinal": 1,
                "height": 40,
                "kind": "SLIDER_TIMELINE",
                "components": {}
            }
        },
        "app_name": "TiLiA",
        "version": "0.1.1"
    }


def get_dummy_timeline_data(id: int = 1) -> dict[str, dict]:
    return {
        str(id): {
            "height": 220,
            "is_visible": True,
            "ordinal": 1,
            "name": "test",
            "kind": "HIERARCHY_TIMELINE",
            "components_hash": "",
            "components": {},
        }
    }


def get_tmp_file_with_dummy_timeline(tmp_path: Path) -> Path:
    file_data = get_blank_file_data()
    file_data["timelines"] = get_dummy_timeline_data()
    tmp_file = tmp_path / "test.tla"
    tmp_file.write_text(json.dumps(file_data), encoding="utf-8")

    return tmp_file
