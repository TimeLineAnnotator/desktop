from tilia.ui.cli.timelines.utils import assert_error


class TestAddBeat:
    def test_bad_ordinal_raises_error(self, cli, tls):
        cli.parse_and_run("timeline add beat --beat-pattern 4")

        with assert_error():
            cli.parse_and_run("component beat --tl-ordinal 0 --time 0")

    def test_bad_name_raises_error(self, cli, tls):
        cli.parse_and_run("timeline add beat --beat-pattern 4 --name this")

        with assert_error():
            cli.parse_and_run("component beat --tl-name other --time 0")

    def test_add_single(self, cli, tls):
        cli.parse_and_run("timeline add beat --beat-pattern 4")
        cli.parse_and_run("component beat --tl-ordinal 1 --time 1")

        assert tls[0].components[0].time == 1

    def test_add_multiple(self, cli, tls):
        cli.parse_and_run("timeline add beat --beat-pattern 4")

        for i in range(10):
            cli.parse_and_run(f"component beat --tl-ordinal 1 --time {i}")

        assert len(tls[0].components) == 10
        for i in range(10):
            assert tls[0][i].get_data("time") == i
