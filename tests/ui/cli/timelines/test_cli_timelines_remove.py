from unittest.mock import patch

from tilia.timelines.hierarchy.timeline import HierarchyTimeline


def test_remove_type_not_provided(cli, hierarchy_tl, tls):
    cli.parse_and_run("timeline remove")

    assert not tls.is_empty


def test_remove_by_name_one_timeline(cli, tls):
    cli.parse_and_run("timeline add hierarchy --name test")
    cli.parse_and_run("timeline remove name test")

    assert tls.is_empty


def test_remove_by_name_multiple_timelines(cli, tls):
    for name in ["test1", "test2", "test3"]:
        cli.parse_and_run("timeline add mrk --name " + name)

    cli.parse_and_run("timeline remove name test1")

    assert len(tls) == 2

    cli.parse_and_run("timeline remove name test2")

    assert len(tls) == 1


def test_remove_by_name_not_found(cli, tls):
    cli.parse_and_run("timeline add hierarchy --name test")

    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline remove name othername")

        printed = mock_print.call_args[0][0]
        assert "No timeline found" in printed
        assert "othername" in printed


def test_remove_by_name_when_no_timelines(cli):
    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline remove name test")

        printed = mock_print.call_args[0][0]
        assert "No timeline found" in printed
        assert "test" in printed


def test_remove_by_name_name_not_provide(cli, tls, hierarchy_tl):
    cli.parse_and_run("timeline remove name")

    assert not tls.is_empty


def test_remove_by_ordinal_one_timeline(cli, tls, hierarchy_tl):
    cli.parse_and_run("timeline remove ordinal 1")

    assert len(tls) == 0


def test_remove_by_ordinal_multiple_timelines(cli, tls):
    for _ in range(3):
        cli.parse_and_run('timeline add hrc --name ""')

    cli.parse_and_run("timeline remove ordinal 1")

    assert len(tls) == 2

    cli.parse_and_run("timeline remove ordinal 2")

    assert len(tls) == 1


def test_remove_by_ordinal_not_found(cli, tls):
    tls.create_timeline(HierarchyTimeline)

    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline remove ordinal 3")

        printed = mock_print.call_args[0][0]
        assert "No timeline found" in printed
        assert "3" in printed


def test_remove_by_ordinal_when_no_timelines(cli, tls):
    with patch("builtins.print") as mock_print:
        cli.parse_and_run("timeline remove ordinal 1")

        printed = mock_print.call_args[0][0]
        assert "No timeline found" in printed
        assert "1" in printed


def test_remove_by_ordinal_ordinal_not_provided(cli, tls, hierarchy_tl):
    cli.parse_and_run("timeline remove ordinal")

    assert not tls.is_empty
