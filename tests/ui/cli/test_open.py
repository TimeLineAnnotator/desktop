import json
from unittest.mock import patch

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.utils import get_blank_file_data, get_dummy_timeline_data
from tilia.requests import Get, get


def _write_tla(tmp_path, file_data):
    path = tmp_path / "test.tla"
    path.write_text(json.dumps(file_data), encoding="utf-8")
    return path


def test_open(cli, tls, tmp_path):
    file_data = get_blank_file_data()
    tl_data = get_dummy_timeline_data()
    file_data["timelines"] = tl_data
    tmp_file_path = _write_tla(tmp_path, file_data)

    cli.parse_and_run(f'open "{tmp_file_path.resolve()}"')

    assert len(tls) == 2


def test_open_file_does_not_exist(cli, tilia_errors):
    cli.parse_and_run('open "whatever"')
    tilia_errors.assert_error()


def test_open_missing_extension(cli, tls, tmp_path):
    file_data = get_blank_file_data()
    tl_data = get_dummy_timeline_data()
    file_data["timelines"] = tl_data
    tmp_file_path = _write_tla(tmp_path, file_data)

    cli.parse_and_run(f'open "{str(tmp_file_path.resolve()).replace(".tla", "")}"')

    assert len(tls) == 2


class TestWithMissingMedia:
    @staticmethod
    def get_file_with_missing_media(tmp_path):
        file_data = get_blank_file_data()

        file_data["media_path"] = "whatever"
        return str(_write_tla(tmp_path, file_data).resolve())

    def test_dont_load_new_media(self, tilia, cli, tls, tmp_path, tilia_errors):
        with patch("builtins.input", return_value="no"):
            cli.parse_and_run(f'open "{self.get_file_with_missing_media(tmp_path)}"')

        assert not get(Get.MEDIA_PATH)

    def test_load_new_media(self, tilia, cli, tls, tmp_path, tilia_errors):
        with patch("builtins.input", side_effect=["yes", EXAMPLE_MEDIA_PATH]):
            cli.parse_and_run(f'open "{self.get_file_with_missing_media(tmp_path)}"')

        assert get(Get.MEDIA_PATH) == EXAMPLE_MEDIA_PATH
