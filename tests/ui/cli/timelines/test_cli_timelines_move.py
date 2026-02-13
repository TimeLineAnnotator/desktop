from tilia.ui.cli.timelines.utils import patch_warn, assert_warn


def _setup_two_timelines(cli):
    cli.parse_and_run("timeline add marker --name first")
    cli.parse_and_run("timeline add marker --name second")


def _setup_three_timelines(cli):
    _setup_two_timelines(cli)
    cli.parse_and_run("timeline add marker --name third")


class TestMoveByName:
    def test_from_second_to_first_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move name second 1")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "first"

    def test_from_first_to_second_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move name first 2")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "first"

    def test_to_same_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move name first 1")

        assert tls[0].get_data("name") == "first"
        assert tls[1].get_data("name") == "second"

    def test_two_positions_up(self, cli, tls):
        _setup_three_timelines(cli)

        cli.parse_and_run("timeline move name third 1")

        assert tls[0].get_data("name") == "third"
        assert tls[1].get_data("name") == "first"
        assert tls[2].get_data("name") == "second"

    def test_two_positions_down(self, cli, tls):
        _setup_three_timelines(cli)

        cli.parse_and_run("timeline move name first 3")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "third"
        assert tls[2].get_data("name") == "first"

    def test_duplicate_names_exist(self, cli, tls):
        cli.parse_and_run("timeline add marker --name duplicate")
        cli.parse_and_run("timeline add marker --name duplicate")
        cli.parse_and_run("timeline add marker --name other")

        with patch_warn() as mock_warn:
            cli.parse_and_run("timeline move name duplicate 3")

        mock_warn.assert_called()

        assert tls[0].get_data("name") == "duplicate"
        assert tls[1].get_data("name") == "other"
        assert tls[2].get_data("name") == "duplicate"


class TestMoveByOrdinal:
    def test_from_second_to_first_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move ordinal 2 1")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "first"

    def test_from_first_to_second_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move ordinal 1 2")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "first"

    def test_to_same_position(self, cli, tls):
        _setup_two_timelines(cli)

        cli.parse_and_run("timeline move ordinal 1 1")

        assert tls[0].get_data("name") == "first"
        assert tls[1].get_data("name") == "second"

    def test_two_positions_up(self, cli, tls):
        _setup_three_timelines(cli)

        cli.parse_and_run("timeline move ordinal 3 1")

        assert tls[0].get_data("name") == "third"
        assert tls[1].get_data("name") == "first"
        assert tls[2].get_data("name") == "second"

    def test_two_positions_down(self, cli, tls):
        _setup_three_timelines(cli)

        cli.parse_and_run("timeline move ordinal 1 3")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "third"
        assert tls[2].get_data("name") == "first"

    def test_move_beyond_last_ordinal(self, cli, tls):
        _setup_three_timelines(cli)

        with patch_warn() as mock_warn:
            cli.parse_and_run("timeline move ordinal 1 4")

        mock_warn.assert_called()

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "third"
        assert tls[2].get_data("name") == "first"

    def test_move_beyond_last_ordinal_only_one_timeline_exists(self, cli, tls):
        cli.parse_and_run("timeline add marker --name only")

        with patch_warn() as mock_warn:
            cli.parse_and_run("timeline move ordinal 1 0")

        mock_warn.assert_called()

        assert tls[0].get_data("name") == "only"

    def test_move_to_zero(self, cli, tls):
        _setup_three_timelines(cli)

        with patch_warn() as mock_warn:
            cli.parse_and_run("timeline move ordinal 3 0")

        mock_warn.assert_called()

        assert tls[0].get_data("name") == "third"
        assert tls[1].get_data("name") == "first"
        assert tls[2].get_data("name") == "second"

    def test_move_to_zero_only_one_timeline_exists(self, cli, tls):
        cli.parse_and_run("timeline add marker --name only")

        # should warn that ordinal parameter is < 1
        with assert_warn():
            cli.parse_and_run("timeline move ordinal 1 0")

        assert tls[0].get_data("name") == "only"

    def test_move_to_negative_ordinal(self, cli, tls):
        _setup_two_timelines(cli)

        # should warn that ordinal parameter is < 1
        with patch_warn():
            cli.parse_and_run("timeline move ordinal 2 -1")

        assert tls[0].get_data("name") == "second"
        assert tls[1].get_data("name") == "first"
