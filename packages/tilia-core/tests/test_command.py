import shutil
import subprocess
import sys
import sysconfig
from importlib.metadata import version

import pytest

from tilia_core import command


class FakeEntryPoint:
    def __init__(self, name, function):
        self.name = name
        self.function = function

    def load(self):
        return self.function


def install(monkeypatch, **functions):
    commands = {name: FakeEntryPoint(name, f) for name, f in functions.items()}
    monkeypatch.setattr(command, "_installed_commands", lambda: commands)


def test_no_arguments_lists_commands(monkeypatch, capsys):
    install(monkeypatch, gui=lambda: 0, other=lambda: 0)

    assert command.main([]) == 0

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines.index("  gui") < lines.index("  other")
    assert "To open a file in TiLiA: tilia gui piece.tla" in out


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags(monkeypatch, capsys, flag):
    install(monkeypatch, gui=lambda: 0)

    assert command.main([flag]) == 0
    assert "gui" in capsys.readouterr().out


def test_no_commands_installed_says_so(monkeypatch, capsys):
    install(monkeypatch)

    assert command.main([]) == 0

    out = capsys.readouterr().out
    assert "No commands are installed." in out
    assert "tilia gui" not in out


def test_file_name_suggests_gui(monkeypatch, capsys):
    install(monkeypatch, gui=lambda: 0)

    assert command.main(["piece.tla"]) == 2

    err = capsys.readouterr().err
    assert "tilia: 'piece.tla' is not a tilia command." in err
    assert 'Did you mean "tilia gui piece.tla"?' in err


def test_old_cli_flag_suggests_gui(monkeypatch, capsys):
    install(monkeypatch, gui=lambda: 0)

    assert command.main(["-i", "cli"]) == 2
    assert 'Did you mean "tilia gui -i cli"?' in capsys.readouterr().err


def test_suggestion_quotes_arguments(monkeypatch, capsys):
    install(monkeypatch, gui=lambda: 0)

    assert command.main(["my piece.tla"]) == 2
    assert "tilia gui 'my piece.tla'" in capsys.readouterr().err


def test_unknown_command_without_gui(monkeypatch, capsys):
    install(monkeypatch)

    assert command.main(["piece.tla"]) == 2

    err = capsys.readouterr().err
    assert "tilia gui" not in err
    assert "tilia --help" in err


def test_command_receives_arguments_in_sys_argv(monkeypatch):
    seen = []

    def gui():
        seen.append(list(sys.argv))
        return 7

    install(monkeypatch, gui=gui)
    monkeypatch.setattr(sys, "argv", ["/path/to/tilia", "gui", "a", "b c"])

    assert command.main(["gui", "a", "b c"]) == 7
    assert seen == [["/path/to/tilia", "a", "b c"]]


def test_command_returning_none_exits_zero(monkeypatch):
    install(monkeypatch, gui=lambda: None)
    monkeypatch.setattr(sys, "argv", ["tilia", "gui"])

    assert command.main(["gui"]) == 0


def test_argv_defaults_to_sys_argv(monkeypatch):
    install(monkeypatch, gui=lambda: 3)
    monkeypatch.setattr(sys, "argv", ["tilia", "gui"])

    assert command.main() == 3


def test_version(capsys):
    assert command.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"tilia-core {version('tilia-core')}"


def test_installed_script():
    script = shutil.which("tilia", path=sysconfig.get_path("scripts"))
    assert script is not None

    result = subprocess.run(
        [script, "--version"], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"tilia-core {version('tilia-core')}"
