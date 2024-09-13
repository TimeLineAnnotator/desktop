def test_set_metadata(cli, tilia_state):
    cli.parse_and_run('metadata set title "my title"')

    assert tilia_state.metadata['title'] == 'my title'


def test_set(cli, tilia_state):
    cli.parse_and_run('metadata set title "my title"')

    assert tilia_state.metadata['title'] == 'my title'


def test_set_to_empty_string(cli, tilia_state):
    cli.parse_and_run('metadata set title ""')

    assert tilia_state.metadata['title'] == ''


def test_cant_set_media_length(cli, tilia_state):
    prev_duration = tilia_state.duration
    cli.parse_and_run('metadata set "media length" 123.45')

    assert tilia_state.duration == prev_duration


def test_set_field_with_spaces(cli, tilia_state):
    cli.parse_and_run('metadata set "composition year" 1999')

    assert tilia_state.metadata['composition year'] == '1999'


def test_set_inexistent_field(cli, tilia_state, tilia_errors):
    cli.parse_and_run('metadata set inexistent value')

    tilia_errors.assert_error()
