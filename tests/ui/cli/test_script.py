from pathlib import Path


def run_script(cli, path):
    cli.parse_and_run(f'script "{str(path.resolve())}"')


def write_script(tmp_path, contents):
    path = tmp_path / "script.txt"
    path.write_text(contents)
    return path


def test_empty_script(cli, tmp_path, tilia_errors):
    path = write_script(tmp_path, "")
    run_script(cli, path)
    tilia_errors.assert_error()


def test_create_timelines(cli, tmp_path, tls):
    path = write_script(tmp_path, "timelines add hierarchy --name test")
    run_script(cli, path)

    assert len(tls) == 1
    assert tls[0].get_data('name') == "test"


def test_load_media(cli, tmp_path, tilia_state):
    media_path = Path(__file__).parent.parent.parent / 'resources' / 'example.mp3'
    path = write_script(tmp_path, f"load-media {str(media_path.resolve())}")
    run_script(cli, path)

    assert Path(tilia_state.media_path) == media_path
