from tests.ui.cli.common import cli_run


class TestCLISetMediaLength:
    def test_set(self, tilia_state):
        cli_run('metadata set-media-length 123.45')

        assert tilia_state.duration == 123.45

    def test_set_to_string_fails(self, tilia_state, tilia_errors):
        prev_duration = tilia_state.duration
        cli_run('metadata set-media-length invalid')

        assert tilia_state.duration == prev_duration
        # no error is raised since argparse pre-validates the value

    def test_set_to_negative_fails(self, tilia_state, tilia_errors):
        prev_duration = tilia_state.duration
        cli_run('metadata set-media-length -23')

        assert tilia_state.duration == prev_duration
        tilia_errors.assert_error()

    def test_set_to_zero_fails(self, tilia_state, tilia_errors):
        prev_duration = tilia_state.duration
        cli_run('metadata set-media-length 0')

        assert tilia_state.duration == prev_duration
        tilia_errors.assert_error()

