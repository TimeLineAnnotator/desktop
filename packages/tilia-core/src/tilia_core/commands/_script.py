"""Reading a `tilia run` script, and checking it before any of it runs.

A script is UTF-8, one command per line. Each line is split as TiLiA splits it and
parsed with one spelling per command and option, and every line that can't run is
reported, naming the right spelling where there is one. The check is about the
script's text and about what this installation can run. What a command finds when
it runs, and a value that `build` or the importers refuse, is left for running.
"""

from __future__ import annotations

import argparse
import functools
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from tilia_core import importers, rules
from tilia_core.build import _KINDS as _KINDS_ADDED
from tilia_core.build import _NOT_A_MEDIA_LENGTH
from tilia_core.commands._report import Report

# contracts/run.md's refusals, and in their form those it doesn't give
# (TimeLineAnnotator/project-management#497 (what the check of a script says)).
_QUOTE_NOT_CLOSED = "a quote isn't closed"
_NOT_A_COMMAND = '"{}" isn\'t a command'
_NOT_AN_OPTION = '"{}" isn\'t an option of {}'
_NOT_AN_ARGUMENT = '"{}" isn\'t an argument of {}'
_NOT_A_KIND = '"{}" isn\'t a kind of {}'
_NOT_A_VALUE = '"{}" isn\'t a value of {}'
_USE = ": use {}"
_REQUIRED = "the argument {} is required"
_ONE_OF_REQUIRED = "the argument {} or {} is required"
_NOT_BOTH = "{} and {} can't both be given"
_NEEDS_A_VALUE = "{} needs a value"
_TAKES_NO_VALUE = "{} takes no value"
# importers' text for a harmony import without the extra, from the same rule.
_HARMONY_NEEDS = f"harmony import needs: {rules.INSTALL_HARMONY}"
_NOT_UTF8 = "this line isn't UTF-8: save the script as UTF-8"

_SCALE_TIMELINES = ("yes", "no", "prompt")

# TiLiA 0.7's other spellings of a command's words, by the words before them.
_ALIASES_OF_KINDS = {"hrc": "hierarchy", "mrk": "marker", "bea": "beat"}
_ALIASES = {
    "": {"timeline": "timelines", "tl": "timelines"},
    "timelines import": _ALIASES_OF_KINDS,
}

# A "--" after the first, which some versions of Python drop and others keep as a
# value, is passed to argparse as this, a word that can't be taken for either.
_DASHES = "--"
_LATER_DASHES = "\0--\0"

# As argparse tells a negative number, which it takes for a value, from an option.
_NEGATIVE_NUMBER = re.compile(r"-\d+|-\d*\.\d+")


@dataclass(frozen=True, kw_only=True)
class Command:
    """A parsed line: its name, such as "timelines import marker by-measure", and its
    arguments as argparse gives them.

    `args.kind` is the kind a `timelines add` or `timelines import` line asks for, and
    `args.by` an import's "time" or "measure", None for `timelines import beat`.
    `args.beat_pattern` is a list of the words given, or None.
    """

    name: str
    args: argparse.Namespace


@dataclass(kw_only=True)
class ScriptLine:
    number: int  # 1-based, in the file
    text: str  # as written, without its line ending
    args: list[str] | None  # None when a quote isn't closed
    command: Command | None = None  # set by the check; None when the line is refused


@dataclass(kw_only=True)
class Script:
    path: Path  # as given, from the working folder
    lines: list[ScriptLine] = field(default_factory=list)  # no blanks or comments
    not_utf8: ScriptLine | None = None  # the line where it stops being UTF-8

    @property
    def name(self) -> str:
        """What reports call the script: its file's name, as they call any file."""
        return self.path.name

    @property
    def folder(self) -> Path:
        """Where the script's relative paths start."""
        return self.path.parent


@dataclass(frozen=True, kw_only=True)
class CheckProblem:
    """A line refused before running. Any of them means nothing runs, status 2."""

    line: ScriptLine
    why: str

    def report(self) -> Report:
        return Report(line=self.line, kind="problem", message=self.why)


def split_line(text: str) -> list[str] | None:
    """A line's arguments, as TiLiA's `CLI.parse_command` splits it: spaces separate,
    double quotes group, and there is no way to write a quote inside them. None when
    a quote isn't closed. A backslash is no escape, so a Windows path stays whole."""
    text = text.strip()
    args = []
    quoted_string = ""
    in_quotes = False
    for arg in text.split(" "):
        if not in_quotes and len(arg) > 1 and arg.startswith('"') and arg.endswith('"'):
            args.append(arg[1:-1])
        elif not in_quotes and arg.startswith('"'):
            in_quotes = True
            quoted_string = arg[1:]
        elif in_quotes and not arg.endswith('"'):
            quoted_string += " " + arg
        elif in_quotes and arg.endswith('"'):
            in_quotes = False
            quoted_string += " " + arg[:-1]
            args.append(quoted_string)
        elif not in_quotes and arg.endswith('"'):
            return None
        else:
            args.append(arg)

    if in_quotes:
        return None
    return args


def read_script(path: str | os.PathLike[str]) -> Script:
    """The script at `path`, each line split, up to the first line that isn't UTF-8.
    Lines end at LF, CRLF or CR, where an editor ends them.

    Raises `OSError` for a script that can't be read.
    """
    script = Script(path=Path(path))
    for number, raw in enumerate(script.path.read_bytes().splitlines(), start=1):
        try:
            text = raw.decode("utf-8-sig" if number == 1 else "utf-8")
        except UnicodeDecodeError:
            shown = raw.decode("utf-8", "backslashreplace")
            script.not_utf8 = ScriptLine(number=number, text=shown, args=None)
            break
        if text.strip() and not text.startswith("#"):
            script.lines.append(
                ScriptLine(number=number, text=text, args=split_line(text))
            )
    return script


def check(script: Script) -> list[CheckProblem]:
    """What's wrong with each line, in order, a line having as many problems as it
    has faults, and each line that can run given its `command`."""
    problems = []
    for line in script.lines:
        line.command, whys = _parsed_line(line)
        problems += [CheckProblem(line=line, why=why) for why in whys]
    if script.not_utf8 is not None:
        problems.append(CheckProblem(line=script.not_utf8, why=_NOT_UTF8))
    return problems


class _BadValue(Exception):
    """A value of the wrong type: `type` functions raise it, and argparse lets it
    through, with their text."""


class _ParserError(Exception):
    """What argparse says when it stops, in its own words."""


class _Parser(argparse.ArgumentParser):
    """A command's parser, which raises where argparse would print and exit: on some
    errors even with `exit_on_error=False`, depending on the version of Python."""

    def __init__(self, prog: str) -> None:
        super().__init__(
            prog=prog, add_help=False, allow_abbrev=False, exit_on_error=False
        )
        self.bad_values: list[str] = []

    def error(self, message: str) -> NoReturn:
        raise _ParserError(message)


def _integer(attribute: str) -> Callable[[str], int]:
    def read(text: str) -> int:
        try:
            return int(text)
        except ValueError:
            raise _BadValue(rules.not_valid(attribute, text)) from None

    return read


def _seconds(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise _BadValue(_NOT_A_MEDIA_LENGTH.format(text)) from None


def _scale_timelines(text: str) -> str:
    if text not in _SCALE_TIMELINES:
        why = _NOT_A_VALUE.format(text, "--scale-timelines")
        raise _BadValue(why + _use(_SCALE_TIMELINES))
    return text


def _kind_added(text: str) -> str:
    if text in _ALIASES_OF_KINDS:
        raise _BadValue(_NOT_A_COMMAND.format(text) + _use([_ALIASES_OF_KINDS[text]]))
    if text not in _KINDS_ADDED:
        raise _BadValue(_NOT_A_KIND.format(text, "timelines add") + _use(_KINDS_ADDED))
    return text


@dataclass(frozen=True, kw_only=True)
class _Option:
    spelling: str
    short: str | None = None  # TiLiA 0.7's other spelling
    type: Callable[[str], Any] = str
    is_flag: bool = False
    is_list: bool = False
    default: Any = None


@dataclass(frozen=True)
class _Positional:
    name: str
    type: Callable[[str], Any] = str


@dataclass(frozen=True, kw_only=True)
class _Syntax:
    """A command's arguments and long options, exactly as contracts/run.md's table
    lists them."""

    positionals: tuple[_Positional, ...] = ()
    options: tuple[_Option, ...] = ()
    required: tuple[str, ...] = ()
    one_of: tuple[tuple[str, str], ...] = ()
    kind: str | None = None  # of an import, which its words name
    by: str | None = None

    def option(self, spelling: str) -> _Option | None:
        for option in self.options:
            if option.spelling == spelling:
                return option
        return None


_PATH = _Positional("PATH")
_SCALE = _Option(
    spelling="--scale-timelines", short="-s", type=_scale_timelines, default="prompt"
)
_FILE_AND_TARGET = (
    _Option(spelling="--file", short="-f"),
    _Option(spelling="--target-name", short="-n"),
    _Option(spelling="--target-ordinal", short="-o", type=_integer("target ordinal")),
)
_TARGET = ("--target-name", "--target-ordinal")
_REFERENCE = ("--reference-tl-name", "--reference-tl-ordinal")


def _import_syntax(kind: str, by: str | None) -> _Syntax:
    options = _FILE_AND_TARGET
    one_of = (_TARGET,)
    if by == "measure":
        options += (
            _Option(spelling="--reference-tl-name"),
            _Option(
                spelling="--reference-tl-ordinal",
                type=_integer("reference tl ordinal"),
            ),
        )
        one_of += (_REFERENCE,)
    return _Syntax(
        options=options,
        required=("--file",),
        one_of=one_of,
        kind=kind,
        by=by,
    )


_COMMANDS: dict[str, _Syntax] = {
    "metadata set": _Syntax(positionals=(_Positional("FIELD"), _Positional("VALUE"))),
    "metadata set-media-length": _Syntax(
        positionals=(_Positional("SECONDS", _seconds),), options=(_SCALE,)
    ),
    "metadata import": _Syntax(positionals=(_PATH,)),
    "load-media": _Syntax(
        positionals=(_PATH,),
        options=(_Option(spelling="--duration-if-error", type=_seconds), _SCALE),
    ),
    "timelines add": _Syntax(
        positionals=(_Positional("KIND", _kind_added),),
        options=(
            _Option(spelling="--name", short="-n", default=""),
            _Option(spelling="--height", short="-e", type=_integer("height")),
            _Option(spelling="--beat-pattern", short="-b", is_list=True),
        ),
    ),
    "timelines import beat": _import_syntax("beat", None),
    **{
        f"timelines import {kind} by-{by}": _import_syntax(kind, by)
        for kind in importers.IMPORTED_KINDS
        for by in ("time", "measure")
    },
    "open": _Syntax(positionals=(_PATH,)),
    "save": _Syntax(
        positionals=(_PATH,), options=(_Option(spelling="--overwrite", is_flag=True),)
    ),
    "clear": _Syntax(options=(_Option(spelling="--force", is_flag=True),)),
}


def _next_words() -> dict[str, list[str]]:
    """For each start of a command, the words that can follow it, in the table's order."""
    following: dict[str, list[str]] = {}
    for name in _COMMANDS:
        words = name.split(" ")
        for position, word in enumerate(words):
            after = following.setdefault(" ".join(words[:position]), [])
            if word not in after:
                after.append(word)
    return following


_NEXT_WORDS = _next_words()


def _use(spellings: Sequence[str]) -> str:
    """`: use "a"`, `: use "a" or "b"`, `: use "a", "b" or "c"`."""
    quoted = [f'"{spelling}"' for spelling in spellings]
    if len(quoted) == 1:
        return _USE.format(quoted[0])
    return _USE.format(f"{', '.join(quoted[:-1])} or {quoted[-1]}")


def _noting(parser: _Parser, read: Callable[[str], Any]) -> Callable[[str], Any]:
    """`read`, which notes a bad value in the parser and goes on, so that argparse
    reads the rest of the line and every bad value is reported. A "--" after the
    first stands for itself, as argparse would otherwise take it for the end."""

    def noting(text: str) -> Any:
        try:
            return read(_DASHES if text == _LATER_DASHES else text)
        except _BadValue as bad:
            parser.bad_values.append(str(bad))
            return None

    return noting


@functools.cache
def _parser(name: str) -> _Parser:
    syntax = _COMMANDS[name]
    parser = _Parser(name)
    for positional in syntax.positionals:
        parser.add_argument(
            positional.name.lower(),
            metavar=positional.name,
            type=_noting(parser, positional.type),
        )
    for option in syntax.options:
        if option.is_flag:
            parser.add_argument(option.spelling, action="store_true")
        else:
            parser.add_argument(
                option.spelling,
                type=_noting(parser, option.type),
                default=option.default,
                nargs="+" if option.is_list else None,
            )
    if syntax.kind is not None:
        parser.set_defaults(kind=syntax.kind, by=syntax.by)
    return parser


def _parsed_line(line: ScriptLine) -> tuple[Command | None, list[str]]:
    """The line's command, when it has one and nothing is wrong with it, and what's
    wrong with it."""
    if line.args is None:
        return None, [_QUOTE_NOT_CLOSED]
    name, rest, whys = _command_words(line.args)
    if name is None:
        return None, whys
    syntax = _COMMANDS[name]
    if syntax.kind == "harmony" and not importers.harmony_available():
        whys.append(_HARMONY_NEEDS)
    tokens, wrong_spellings = _spelled(name, syntax, rest)
    whys += wrong_spellings
    if tokens is None:
        return None, whys
    whys += _missing_options(syntax, tokens)
    args, wrong_arguments = _arguments(name, syntax, tokens)
    whys += wrong_arguments
    if whys or args is None:
        return None, whys
    return Command(name=name, args=args), whys


def _command_words(args: list[str]) -> tuple[str | None, list[str], list[str]]:
    """The command the line's first words name, the rest of the line, and what's wrong
    with those words. A word TiLiA spells otherwise is read as it should be, so that
    the rest of the line can be checked too."""
    name = ""
    whys = []
    for position, word in enumerate(args):
        right = _ALIASES.get(name, {}).get(word)
        if right is not None:
            whys.append(_NOT_A_COMMAND.format(word) + _use([right]))
            word = right
        said = f"{name} {word}" if name else word
        if word not in _NEXT_WORDS[name]:
            whys.append(_stops_at(said, name))
            return None, [], whys
        name = said
        if name in _COMMANDS:
            return name, args[position + 1 :], whys
    whys.append(_stops_at(name, name))
    return None, [], whys


def _stops_at(said: str, name: str) -> str:
    """Why the words `said` make no command, `name` being those of them that start one."""
    why = _NOT_A_COMMAND.format(said)
    if name:
        why += _use([f"{name} {word}" for word in _NEXT_WORDS[name]])
    return why


def _spelled(
    name: str, syntax: _Syntax, tokens: list[str]
) -> tuple[list[str] | None, list[str]]:
    """The tokens after a command's words, each option spelled as it should be, and
    what's wrong with the options. None for the tokens when one has no one right
    spelling, as what follows it can't then be read."""
    right = []
    whys = []
    can_read_on = True
    for position, token in enumerate(tokens):
        if token == "--":
            right += tokens[position:]
            break
        spelling, equals, value = token.partition("=")
        option = syntax.option(spelling)
        if option is not None:
            if option.is_flag and equals:
                whys.append(_TAKES_NO_VALUE.format(spelling))
                token = spelling
            right.append(token)
        elif _looks_like_an_option(token):
            spellings = _right_spellings(syntax, spelling)
            why = _NOT_AN_OPTION.format(spelling, name)
            whys.append(why + _use(spellings) if spellings else why)
            if len(spellings) == 1:
                right.append(spellings[0] + equals + value)
            else:
                can_read_on = False
        else:
            right.append(token)
    return right if can_read_on else None, whys


def _looks_like_an_option(token: str) -> bool:
    """As argparse tells an option from a value, given no option here spelled as a
    negative number."""
    return (
        token.startswith("-")
        and token != "-"
        and " " not in token
        and _NEGATIVE_NUMBER.fullmatch(token) is None
    )


def _right_spellings(syntax: _Syntax, wrong: str) -> list[str]:
    """The long options `wrong` stands for: as TiLiA's short option, or as a prefix."""
    for option in syntax.options:
        if option.short == wrong:
            return [option.spelling]
    if wrong.startswith("--") and len(wrong) > 2:
        return [o.spelling for o in syntax.options if o.spelling.startswith(wrong)]
    return []


def _missing_options(syntax: _Syntax, tokens: list[str]) -> list[str]:
    given = set()
    for token in tokens:
        if token == "--":
            break
        given.add(token.partition("=")[0])
    whys = [_REQUIRED.format(o) for o in syntax.required if o not in given]
    for first, second in syntax.one_of:
        if first in given and second in given:
            whys.append(_NOT_BOTH.format(first, second))
        elif first not in given and second not in given:
            whys.append(_ONE_OF_REQUIRED.format(first, second))
    return whys


def _arguments(
    name: str, syntax: _Syntax, tokens: list[str]
) -> tuple[argparse.Namespace | None, list[str]]:
    """The line's arguments as argparse gives them, with every text our own, since
    argparse's words change with the version of Python. Options unknown here and
    those a command requires have been seen to by now."""
    parser = _parser(name)
    parser.bad_values = []
    try:
        args, extras = parser.parse_known_args(_dashes_kept(tokens))
    except argparse.ArgumentError as error:
        if error.argument_name is not None:
            return None, parser.bad_values + [
                _NEEDS_A_VALUE.format(error.argument_name)
            ]
        return None, parser.bad_values + _missing_positionals(syntax, str(error))
    except _ParserError as error:
        return None, parser.bad_values + _missing_positionals(syntax, str(error))
    if parser.bad_values:
        return None, parser.bad_values
    extras = [_DASHES if token == _LATER_DASHES else token for token in extras]
    too_many = [token for token in extras if token != "--"]
    return args, [_NOT_AN_ARGUMENT.format(token, name) for token in too_many]


def _dashes_kept(tokens: list[str]) -> list[str]:
    """The tokens, with each "--" after the first one that ends the options
    replaced, since a "--" is a value there and Python's versions differ on whether
    argparse keeps it."""
    if "--" not in tokens:
        return tokens
    end = tokens.index("--") + 1
    return tokens[:end] + [_LATER_DASHES if t == "--" else t for t in tokens[end:]]


def _missing_positionals(syntax: _Syntax, message: str) -> list[str]:
    """The arguments argparse's `message` says are missing: all it can say by now."""
    names = [p.name for p in syntax.positionals if p.name in message]
    return [_REQUIRED.format(name) for name in names] or [message]
