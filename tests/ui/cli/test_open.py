import json
import shutil
from unittest.mock import patch

from colorama import Fore

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.utils import get_blank_file_data
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


def _write_old_file_with_a_formal_type(tmp_path):
    """A file as TiLiA 0.7 saved it, whose formal type the core drops."""
    file_data = get_blank_file_data()
    file_data["version"] = "0.7.0"
    file_data["media_metadata"]["media length"] = 100.0
    file_data["timelines"]["1"] = {
        "name": "Form",
        "kind": "HIERARCHY_TIMELINE",
        "height": 120,
        "is_visible": True,
        "ordinal": 2,
        "components": {
            "2": {
                "start": 0.0,
                "end": 10.0,
                "level": 1,
                "formal_type": "sonata",
                "kind": "HIERARCHY",
                "hash": "irrelevant",
            }
        },
    }
    path = tmp_path / "old.tla"
    path.write_text(json.dumps(file_data), encoding="utf-8")
    return path


class TestProblems:
    def test_prints_the_message_then_one_line_each(self, cli, tls, tmp_path, capsys):
        path = _write_old_file_with_a_formal_type(tmp_path)

        cli.parse_and_run(f'open "{path.resolve()}"')

        printed = capsys.readouterr().out.replace(Fore.RESET, "")
        assert printed.splitlines() == [
            "'old.tla' has 1 problem. TiLiA keeps it as it is, and saves it unchanged"
            " until you fix it.",
            'Form, 00:00.0–00:10.0: formal_type "sonata" dropped',
        ]

    def test_prints_nothing_for_a_file_with_none(self, cli, tls, tmp_path, capsys):
        path = _save_file_with_hierarchy_timeline(cli, tmp_path)
        capsys.readouterr()

        cli.parse_and_run(f'open "{path.resolve()}"')

        assert capsys.readouterr().out == ""
