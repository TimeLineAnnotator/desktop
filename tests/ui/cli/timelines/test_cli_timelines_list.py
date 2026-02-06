from unittest.mock import patch


def test_list_timelines_no_timelines(cli):
    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline list")

        printed = mock_print.call_args[0][0]

        assert "name" in printed
        assert "ord" in printed
        assert "kind" in printed
        assert "1" not in printed


def test_list_timelines_single_timeline(cli, hierarchy_tl):
    hierarchy_tl.set_data("name", "test1")

    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline list")

        printed = mock_print.call_args[0][0]

        assert "test1" in printed
        assert "Hierarchy" in printed
        assert str(hierarchy_tl.ordinal) in printed


def test_list_timelines_multiple_timelines(cli, tls):
    for name in ["test1", "test2", "test3"]:
        cli.parse_and_run("timeline add hrc --name " + name)

    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timelines list")

        printed = mock_print.call_args[0][0]

        assert "test1" in printed
        assert "test2" in printed
        assert "test3" in printed
