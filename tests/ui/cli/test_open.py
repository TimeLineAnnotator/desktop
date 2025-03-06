import json
from unittest.mock import patch

from tests.utils import get_blank_file_data, get_dummy_timeline_data


def test_open(cli, tls, tmp_path):
    file_data = get_blank_file_data()
    tl_data = get_dummy_timeline_data()
    file_data["timelines"] = tl_data
    tmp_file_path = tmp_path / "test.tla"
    tmp_file_path.write_text(json.dumps(file_data))

    with patch("builtins.input", return_value=str(tmp_file_path.resolve())):
        cli.parse_and_run(f'open "{tmp_file_path.resolve()}"')

    assert len(tls) == 2


def test_open_file_does_not_exist(cli, tmp_path, tilia_errors):
    with patch("builtins.input", return_value=str(tmp_path)):
        cli.parse_and_run('open "whatever"')

    tilia_errors.assert_error()


def test_open_missing_extension(cli, tls, tmp_path):
    file_data = get_blank_file_data()
    tl_data = get_dummy_timeline_data()
    file_data["timelines"] = tl_data
    tmp_file_path = tmp_path / "test.tla"
    tmp_file_path.write_text(json.dumps(file_data))

    with patch("builtins.input", return_value=str(tmp_file_path.resolve())):
        cli.parse_and_run(f'open "{str(tmp_file_path.resolve()).replace(".tla", "")}"')

    assert len(tls) == 2
