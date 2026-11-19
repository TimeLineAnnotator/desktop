from pathlib import Path

import pytest

from tilia.ui.cli.script import split_commands


def run_script(cli, path):
    cli.parse_and_run(f'script "{str(path.resolve())}"')


def write_script(tmp_path, contents, encoding="utf-8"):
    path = tmp_path / "script.txt"
    path.write_text(contents, encoding=encoding)
    return path


def test_empty_script(cli, tmp_path, tilia_errors):
    path = write_script(tmp_path, "")
    run_script(cli, path)
    tilia_errors.assert_error()


def test_create_timelines(cli, tmp_path, tls):
    path = write_script(tmp_path, "timelines add hierarchy --name test")
    run_script(cli, path)

    assert len(tls) == 1
    assert tls[0].get_data("name") == "test"


def test_load_media(cli, tmp_path, tilia_state):
    media_path = Path(__file__).parent.parent.parent / "resources" / "example.mp3"
    path = write_script(tmp_path, f"load-media {str(media_path.resolve())}")
    run_script(cli, path)

    assert Path(tilia_state.media_path) == media_path


def test_comments(cli, tls, tmp_path, tilia_errors):
    script = "# this is a comment"
    script += "\ntimelines add hierarchy"
    script += "\n# this is another comment"
    path = write_script(tmp_path, script)

    run_script(cli, path)
    tilia_errors.assert_no_error()
    assert len(tls) == 1


def test_different_encoding(cli, tls, tmp_path, tilia_errors):
    path = write_script(
        tmp_path, "timelines add hierarchy --name Válido?", encoding="latin-1"
    )
    cli.parse_and_run(f'script "{str(path.resolve())}" --encoding latin-1')

    tilia_errors.assert_no_error()
    assert len(tls) == 1


def test_commands_separated_by_semicolons(cli, tls, tmp_path, tilia_errors):
    path = write_script(tmp_path, "timelines add hierarchy; timelines add hierarchy")
    run_script(cli, path)

    tilia_errors.assert_no_error()
    assert len(tls) == 2


@pytest.mark.parametrize(
    "text,commands",
    [
        ("a", ["a"]),
        ("a;b", ["a", "b"]),
        ("a\nb", ["a", "b"]),
        ("a\r\nb", ["a", "b"]),
        ("a ; b ;", ["a", "b"]),
        ("a;;b", ["a", "b"]),
        ('a "x;y" b;c', ['a "x;y" b', "c"]),
        ('a "x\ny"', ['a "x\ny"']),
        ("# comment\na", ["a"]),
        ("# comment;a", ["a"]),
        ("", []),
    ],
)
def test_split_commands(text, commands):
    assert split_commands(text) == commands
