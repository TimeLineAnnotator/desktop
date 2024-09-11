from tests.ui.cli.common import cli_run


def test_set(tilia_state):
    cli_run('metadata set title "my title"')

    assert tilia_state.metadata['title'] == 'my title'


def test_set_to_empty_string(tilia_state):
    cli_run('metadata set title ""')

    assert tilia_state.metadata['title'] == ''


def test_cant_set_media_length(tilia_state):
    prev_duration = tilia_state.duration
    cli_run('metadata set "media length" 123.45')

    assert tilia_state.duration == prev_duration


def test_set_field_with_spaces(tilia_state):
    cli_run('metadata set "composition year" 1999')

    assert tilia_state.metadata['composition year'] == '1999'


def test_set_inexistent_field(tilia_state, tilia_errors):
    cli_run('metadata set inexistent value')

    tilia_errors.assert_error()