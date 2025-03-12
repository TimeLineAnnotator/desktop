import json
from unittest.mock import patch

from tilia.timelines.marker.components import Marker


def test_export(tilia_state, cli, marker_tl, tmp_path):
    marker_tl.set_data("name", "test")
    for i in range(3):
        marker_tl.create_marker(i)

    tmp_file = tmp_path / "test.txt"

    cli.parse_and_run(f"export {tmp_file.resolve()}")

    with open(tmp_file, "r") as f:
        data = json.load(f)

    tl_data = data["timelines"][0]

    assert tl_data["name"] == "test"
    assert len(tl_data["components"]) == 3


def test_export_file_exists_do_not_overwrite(tilia_state, cli, marker_tl, tmp_path):
    marker_tl.set_data("name", "test")
    for i in range(3):
        marker_tl.create_marker(i)

    tmp_file = tmp_path / "test.txt"
    tmp_file.write_text("do not overwrite this")

    with patch("builtins.input", return_value="no"):
        cli.parse_and_run(f"export {tmp_file.resolve()}")

    with open(tmp_file, "r") as f:
        contents = f.read()

    assert contents == "do not overwrite this"


def test_export_file_exists_overwrite(tilia_state, cli, marker_tl, tmp_path):
    marker_tl.set_data("name", "test")
    for i in range(3):
        marker_tl.create_marker(i)

    tmp_file = tmp_path / "test.txt"
    tmp_file.write_text("overwrite this")

    with patch("builtins.input", return_value="yes"):
        cli.parse_and_run(f"export {tmp_file.resolve()}")

    with open(tmp_file, "r") as f:
        data = json.load(f)

    tl_data = data["timelines"][0]
    assert tl_data["name"] == "test"
    assert len(tl_data["components"]) == 3


def test_export_file_exists_overwrite_with_flag(tilia_state, cli, marker_tl, tmp_path):
    marker_tl.set_data("name", "test")

    tmp_file = tmp_path / "test.txt"
    tmp_file.write_text("overwrite this")

    cli.parse_and_run(f"export {tmp_file.resolve()} --overwrite")

    with open(tmp_file, "r") as f:
        data = json.load(f)

    tl_data = data["timelines"][0]
    assert tl_data["name"] == "test"
