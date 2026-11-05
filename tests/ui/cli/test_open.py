import shutil
from unittest.mock import patch

from tests.constants import EXAMPLE_MEDIA_PATH
from tilia.requests import Get, get


def _save_and_clear(cli, tmp_path):
    path = tmp_path / "test.tla"
    cli.parse_and_run(f'save "{path.resolve()}"')
    cli.parse_and_run("clear --force")
    return path


def _save_file_with_hierarchy_timeline(cli, tmp_path):
    cli.parse_and_run("timelines add hierarchy --name test")
    return _save_and_clear(cli, tmp_path)


def test_open(cli, tls, tmp_path):
    tmp_file_path = _save_file_with_hierarchy_timeline(cli, tmp_path)

    cli.parse_and_run(f'open "{tmp_file_path.resolve()}"')

    assert len(tls) == 2


def test_open_file_does_not_exist(cli, tilia_errors):
    cli.parse_and_run('open "whatever"')
    tilia_errors.assert_error()


def test_open_missing_extension(cli, tls, tmp_path):
    tmp_file_path = _save_file_with_hierarchy_timeline(cli, tmp_path)

    cli.parse_and_run(f'open "{str(tmp_file_path.resolve()).replace(".tla", "")}"')

    assert len(tls) == 2


class TestWithMissingMedia:
    @staticmethod
    def get_file_with_missing_media(cli, tmp_path):
        # Save a file whose media was moved away afterwards.
        media_path = tmp_path / "moved.mp3"
        shutil.copy(EXAMPLE_MEDIA_PATH, media_path)
        cli.parse_and_run(f'load-media "{media_path.resolve()}"')
        file_path = _save_and_clear(cli, tmp_path)
        media_path.unlink()
        return str(file_path.resolve())

    def test_dont_load_new_media(self, tilia, cli, tls, tmp_path, tilia_errors):
        file_path = self.get_file_with_missing_media(cli, tmp_path)
        with patch("builtins.input", return_value="no"):
            cli.parse_and_run(f'open "{file_path}"')

        assert not get(Get.MEDIA_PATH)

    def test_load_new_media(self, tilia, cli, tls, tmp_path, tilia_errors):
        file_path = self.get_file_with_missing_media(cli, tmp_path)
        with patch("builtins.input", side_effect=["yes", EXAMPLE_MEDIA_PATH]):
            cli.parse_and_run(f'open "{file_path}"')

        assert get(Get.MEDIA_PATH) == EXAMPLE_MEDIA_PATH
