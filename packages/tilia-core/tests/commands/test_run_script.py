"""Reading and checking a `tilia run` script before any of it runs (FR-010-FR-013,
research R10): which lines are read, how each is split, which spellings it takes,
and what each refused line says."""

import codecs
import math
from pathlib import Path

import pytest

from tilia_core import importers
from tilia_core.commands._script import (
    _Parser,
    _parser,
    _ParserError,
    check,
    read_script,
    split_line,
)

SCRIPT = "import-script.txt"
NOT_UTF8 = "this line isn't UTF-8: save the script as UTF-8"
HARMONY_EXTRA = 'harmony import needs: pip install "tilia-core[harmony]"'
NOT_A_LENGTH = (
    "Cannot set media metadata to {}. Media length must be a positive number."
)
NOT_A_SCALE = '"{}" isn\'t a value of --scale-timelines: use "yes", "no" or "prompt"'
TARGET = "--target-name Chords"
BEAT = "timelines import beat"
EXTRA = '"{}" isn\'t an argument of timelines import beat'
BY_TIME = "timelines import marker by-time"
BY_MEASURE = "timelines import marker by-measure"
KINDS = ("marker", "hierarchy", "range", "harmony", "pdf")
METADATA = '"metadata set", "metadata set-media-length" or "metadata import"'
TIMELINES = '"timelines add" or "timelines import"'
BY = '"timelines import marker by-time" or "timelines import marker by-measure"'


@pytest.fixture(autouse=True)
def harmony_installed(monkeypatch):
    """The check's answers don't depend on what this environment has installed."""
    monkeypatch.setattr(importers, "harmony_available", lambda: True)


def script_of(tmp_path, text):
    path = tmp_path / SCRIPT
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return read_script(path)


def refusals(tmp_path, text):
    return [(p.line.number, p.why) for p in check(script_of(tmp_path, text))]


def whys(tmp_path, text):
    return [why for _, why in refusals(tmp_path, text)]


def command_of(tmp_path, text):
    script = script_of(tmp_path, text)
    assert check(script) == []
    return script.lines[0].command


class TestLines:
    def test_blank_lines_and_comments_are_skipped_and_lines_keep_their_numbers(
        self, tmp_path
    ):
        script = script_of(tmp_path, "# a comment\n\n   \nclear\n\t\n#clear\nclear\n")

        assert [line.number for line in script.lines] == [4, 7]
        assert [line.text for line in script.lines] == ["clear", "clear"]

    def test_only_a_line_that_starts_with_a_hash_is_a_comment(self, tmp_path):
        # As TiLiA's `script`, which asks line.startswith("#").
        assert refusals(tmp_path, "  # not a comment\n") == [
            (1, '"#" isn\'t a command')
        ]

    def test_a_line_keeps_its_text_as_written_and_is_split_without_its_spaces(
        self, tmp_path
    ):
        line = script_of(tmp_path, "  save a.tla  \n").lines[0]

        assert line.text == "  save a.tla  "
        assert line.args == ["save", "a.tla"]

    def test_a_script_with_no_commands_has_no_lines_and_no_refusals(self, tmp_path):
        script = script_of(tmp_path, "# only this\n\n")

        assert script.lines == []
        assert check(script) == []

    @pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
    def test_any_line_ending(self, tmp_path, ending):
        script = script_of(tmp_path, ending.join(["clear", "", "save a.tla"]))

        assert [(line.number, line.text) for line in script.lines] == [
            (1, "clear"),
            (3, "save a.tla"),
        ]

    @pytest.mark.parametrize("char", ["\x0b", "\x0c", "\x1c", "\x85", "\u2028"])
    def test_only_a_line_ending_ends_a_line(self, tmp_path, char):
        # str.splitlines would also break here, which would shift every line's
        # number from what an editor shows.
        script = script_of(tmp_path, f'metadata set title "a{char}b"\nclear\n')

        assert [line.number for line in script.lines] == [1, 2]
        assert script.lines[0].args == ["metadata", "set", "title", f"a{char}b"]

    @pytest.mark.parametrize(
        "text", ["clear\n", "# a comment\nclear\n", "\nclear\n", "clear"]
    )
    def test_a_byte_order_mark_is_not_part_of_the_script(self, tmp_path, text):
        script = script_of(tmp_path, codecs.BOM_UTF8 + text.encode())

        assert [line.text for line in script.lines] == ["clear"]
        assert check(script) == []

    def test_a_byte_order_mark_is_only_read_at_the_start(self, tmp_path):
        assert refusals(tmp_path, "clear\n\ufeffclear\n") == [
            (2, '"\ufeffclear" isn\'t a command')
        ]

    def test_the_folder_is_the_scripts(self, tmp_path):
        assert script_of(tmp_path, "clear\n").folder == tmp_path

    def test_reports_call_it_by_its_files_name(self, tmp_path):
        assert script_of(tmp_path, "clear\n").name == SCRIPT

    def test_the_path_is_kept_as_given(self, tmp_path, monkeypatch):
        (tmp_path / SCRIPT).write_text("clear\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        script = read_script(SCRIPT)

        assert script.path == Path(SCRIPT)
        assert script.folder == Path(".")

    def test_a_script_that_cant_be_read_raises_oserror(self, tmp_path):
        with pytest.raises(OSError):
            read_script(tmp_path / "no such script.txt")


class TestNotUtf8:
    @pytest.mark.parametrize(
        "bytes_",
        [
            b"\xf8",  # Latin-1's o with a stroke
            b"\xc3",  # a sequence that stops at the end of the line
            b"\xed\xa0\x80",  # a surrogate
            b"\xc0\xaf",  # an overlong form
        ],
    )
    def test_refused_at_its_first_bad_line(self, tmp_path, bytes_):
        text = b"clear\n# a comment\nmetadata set composer Dvo" + bytes_ + b"\nclear\n"

        assert refusals(tmp_path, text) == [(3, NOT_UTF8)]

    def test_another_encoding_altogether(self, tmp_path):
        text = "clear\n".encode("utf-16")

        assert refusals(tmp_path, text) == [(1, NOT_UTF8)]

    def test_in_a_comment_too(self, tmp_path):
        assert refusals(tmp_path, b"clear\n# Dvo\xf8\xe1k\nclear\n") == [(2, NOT_UTF8)]

    def test_only_the_first_bad_line_is_named(self, tmp_path):
        text = b"clear\nsave \xf8.tla\nclear\nsave \xf8.tla\n"

        assert refusals(tmp_path, text) == [(2, NOT_UTF8)]

    def test_the_lines_before_it_are_checked_and_those_after_it_are_not(self, tmp_path):
        text = b"nonsense\nclear\nsave \xf8.tla\nnonsense\n"

        assert refusals(tmp_path, text) == [
            (1, '"nonsense" isn\'t a command'),
            (3, NOT_UTF8),
        ]

    def test_its_report(self, tmp_path, capsys):
        script = script_of(tmp_path, b"clear\nsave \xf8.tla\n")

        for problem in check(script):
            problem.report().print(SCRIPT)

        captured = capsys.readouterr()
        assert captured.err == f"import-script.txt, line 2: {NOT_UTF8}\n"
        assert captured.out == ""


class TestSplitting:
    @pytest.mark.parametrize(
        "text,args",
        [
            # TiLiA's own cases, tests/ui/cli/test_cli_ui.py's PARSE_COMMAND_CASES.
            ("spaced args", ["spaced", "args"]),
            ('"spaced args"', ["spaced args"]),
            ('"spaced args" and more', ["spaced args", "and", "more"]),
            ('"three spaced args"', ["three spaced args"]),
            ('"three spaced args" and more', ["three spaced args", "and", "more"]),
            (
                'surrounded "quoted args" surrounded',
                ["surrounded", "quoted args", "surrounded"],
            ),
            ('"unfinished', None),
            ('"unfinished and more', None),
            ('not started"', None),
            ('notstarted"', None),
            ('notstarted" and more', None),
            ('this has notstarted"', None),
            ('"onestring"', ["onestring"]),
            ("trailing space ", ["trailing", "space"]),
            ("trailing spaces     ", ["trailing", "spaces"]),
            # What moving it as it is keeps.
            ("two  spaces", ["two", "", "spaces"]),
            ('""', [""]),
            ('a "" b', ["a", "", "b"]),
            ('"', None),
            ('a " b', None),
            ('a"b', ['a"b']),
            ('"a"b', None),
            ("tab\tseparated", ["tab\tseparated"]),
            ("'single quotes'", ["'single", "quotes'"]),
            # Windows paths, whole: a backslash is no escape.
            (r"C:\Users\me\piece.tla", [r"C:\Users\me\piece.tla"]),
            (r'"C:\Program Files\piece.tla"', [r"C:\Program Files\piece.tla"]),
            (r'"C:\My Scripts\"', ["C:\\My Scripts\\"]),
            (r"\\server\share\piece.tla", [r"\\server\share\piece.tla"]),
        ],
    )
    def test_as_tilia_splits_a_line(self, text, args):
        assert split_line(text) == args

    def test_a_line_holds_what_it_splits_into(self, tmp_path):
        script = script_of(
            tmp_path, 'metadata set composer "W. A. Mozart"\n"unclosed\n'
        )

        assert [line.args for line in script.lines] == [
            ["metadata", "set", "composer", "W. A. Mozart"],
            None,
        ]


def by_time(kind):
    return (
        f"timelines import {kind} by-time --file c.csv --target-name Chords",
        f"timelines import {kind} by-time",
        {
            "kind": kind,
            "by": "time",
            "file": "c.csv",
            "target_name": "Chords",
            "target_ordinal": None,
        },
    )


def by_measure(kind):
    return (
        f"timelines import {kind} by-measure --file c.csv --target-ordinal 3"
        " --reference-tl-name Measures",
        f"timelines import {kind} by-measure",
        {
            "kind": kind,
            "by": "measure",
            "file": "c.csv",
            "target_name": None,
            "target_ordinal": 3,
            "reference_tl_name": "Measures",
            "reference_tl_ordinal": None,
        },
    )


# Every command of contracts/run.md's table, each with all its long options.
ACCEPTED = [
    (
        'metadata set composer "W. A. Mozart"',
        "metadata set",
        {"field": "composer", "value": "W. A. Mozart"},
    ),
    (
        "metadata set-media-length 1043",
        "metadata set-media-length",
        {"seconds": 1043.0},
    ),
    *(
        (
            f"metadata set-media-length 312.5 --scale-timelines {answer}",
            "metadata set-media-length",
            {"seconds": 312.5, "scale_timelines": answer},
        )
        for answer in ("yes", "no", "prompt")
    ),
    ("metadata import fields.json", "metadata import", {"path": "fields.json"}),
    ("load-media a.wav", "load-media", {"path": "a.wav", "duration_if_error": None}),
    (
        "load-media a.mp3 --duration-if-error 312.5 --scale-timelines no",
        "load-media",
        {"path": "a.mp3", "duration_if_error": 312.5, "scale_timelines": "no"},
    ),
    (
        "timelines add beat --name Measures --height 40 --beat-pattern 3",
        "timelines add",
        {"kind": "beat", "name": "Measures", "height": 40, "beat_pattern": ["3"]},
    ),
    (
        "timelines add beat --beat-pattern 10[4] 3 15[4]",
        "timelines add",
        {"kind": "beat", "beat_pattern": ["10[4]", "3", "15[4]"]},
    ),
    (
        'timelines add beat --beat-pattern "10[4] 3"',
        "timelines add",
        {"kind": "beat", "beat_pattern": ["10[4] 3"]},
    ),
    (
        "timelines add hierarchy",
        "timelines add",
        {"kind": "hierarchy", "name": "", "height": None, "beat_pattern": None},
    ),
    (
        "timelines add marker --height 30",
        "timelines add",
        {"kind": "marker", "height": 30},
    ),
    (
        "timelines add harmony --name Chords",
        "timelines add",
        {"kind": "harmony", "name": "Chords"},
    ),
    (
        "timelines add --name Chords harmony",
        "timelines add",
        {"kind": "harmony", "name": "Chords"},
    ),
    (
        "timelines import beat --file beats.csv --target-name Measures",
        "timelines import beat",
        {
            "kind": "beat",
            "by": None,
            "file": "beats.csv",
            "target_name": "Measures",
            "target_ordinal": None,
        },
    ),
    (
        "timelines import beat --target-ordinal 2 --file beats.csv",
        "timelines import beat",
        {"file": "beats.csv", "target_name": None, "target_ordinal": 2},
    ),
    *(by_time(kind) for kind in KINDS),
    *(by_measure(kind) for kind in KINDS),
    (
        f"{BY_MEASURE} --file c.csv --target-name Chords --reference-tl-ordinal 1",
        BY_MEASURE,
        {"reference_tl_name": None, "reference_tl_ordinal": 1},
    ),
    ("open piece.tla", "open", {"path": "piece.tla"}),
    ("save piece.tla", "save", {"path": "piece.tla", "overwrite": False}),
    ("save piece.tla --overwrite", "save", {"path": "piece.tla", "overwrite": True}),
    ("save --overwrite piece.tla", "save", {"path": "piece.tla", "overwrite": True}),
    ("clear", "clear", {"force": False}),
    ("clear --force", "clear", {"force": True}),
]


class TestAccepted:
    @pytest.mark.parametrize("text,name,args", ACCEPTED)
    def test_every_command_with_its_long_options(self, tmp_path, text, name, args):
        command = command_of(tmp_path, text)

        assert command.name == name
        for key, value in args.items():
            assert getattr(command.args, key) == value, key

    def test_the_example_of_contracts_run(self, tmp_path):
        script = script_of(
            tmp_path,
            'metadata set composer "W. A. Mozart"\n'
            "metadata set-media-length 1043\n"
            "# timelines\n"
            "timelines add beat --name Measures --beat-pattern 3\n"
            "timelines add harmony --name Chords\n"
            "timelines add hierarchy --name Phrases\n"
            "\n"
            "timelines import beat --target-name Measures --file beats.csv\n"
            "timelines import harmony by-measure --target-name Chords"
            " --reference-tl-name Measures --file chords.csv\n"
            "timelines import hierarchy by-measure --target-name Phrases"
            " --reference-tl-name Measures --file phrases.csv\n"
            "\n"
            "save K279-1.tla --overwrite\n",
        )

        assert check(script) == []
        assert [line.number for line in script.lines] == [1, 2, 4, 5, 6, 8, 9, 10, 12]
        assert all(line.command is not None for line in script.lines)

    def test_an_option_may_give_its_value_after_an_equals_sign(self, tmp_path):
        # As argparse, and so TiLiA, takes it: the same spelling of the option.
        line = "timelines import beat --file=a=b.csv --target-name=-Chords"

        command = command_of(tmp_path, line)

        assert command.args.file == "a=b.csv"
        assert command.args.target_name == "-Chords"

    def test_a_quoted_option_may_hold_spaces_after_its_equals_sign(self, tmp_path):
        command = command_of(tmp_path, 'save "--overwrite" "a b.tla"')
        assert command.args.overwrite is True
        assert command.args.path == "a b.tla"

        line = 'timelines import beat "--file=a b.csv" "--target-name=C D"'
        command = command_of(tmp_path, line)
        assert command.args.file == "a b.csv"
        assert command.args.target_name == "C D"

    @pytest.mark.parametrize(
        "text,field,value",
        [
            ("metadata set title -- -foo", "title", "-foo"),
            ("metadata set title -- --", "title", "--"),
            ("metadata set -- -- --", "--", "--"),
            ("metadata set -- -foo --overwrite", "-foo", "--overwrite"),
            ('metadata set title "-foo bar"', "title", "-foo bar"),
            ("metadata set tempo -5", "tempo", "-5"),
            ("metadata set tempo -.5", "tempo", "-.5"),
            ("metadata set title -", "title", "-"),
            ('metadata set notes ""', "notes", ""),
            ("metadata set a=b c=d", "a=b", "c=d"),
        ],
    )
    def test_values_argparse_takes_for_values(self, tmp_path, text, field, value):
        args = command_of(tmp_path, text).args

        assert (args.field, args.value) == (field, value)

    @pytest.mark.parametrize(
        "text,attribute,path",
        [
            (r"save C:\Users\me\piece.tla", "path", r"C:\Users\me\piece.tla"),
            (r'save "C:\Program Files\a.tla"', "path", r"C:\Program Files\a.tla"),
            (r'open "C:\My Scripts\"', "path", "C:\\My Scripts\\"),
            (r"load-media D:\media\a.wav", "path", r"D:\media\a.wav"),
            (r"metadata import ..\fields.json", "path", r"..\fields.json"),
            (
                rf"{BEAT} --file .\a\beats.csv --target-ordinal 1",
                "file",
                r".\a\beats.csv",
            ),
            (
                rf"{BEAT} --file=C:\a\beats.csv --target-ordinal 1",
                "file",
                r"C:\a\beats.csv",
            ),
        ],
    )
    def test_a_windows_path_is_kept_whole(self, tmp_path, text, attribute, path):
        assert getattr(command_of(tmp_path, text).args, attribute) == path

    def test_paths_stay_as_written_and_nothing_looks_for_them(self, tmp_path):
        # FR-019 applies when running, and a file that isn't there is a failed
        # command (FR-013).
        line = f"{BEAT} --file ../no/such.csv --target-ordinal 1"

        assert command_of(tmp_path, line).args.file == "../no/such.csv"

    @pytest.mark.parametrize(
        "text,attribute",
        [
            ("save a\x00b.tla", "path"),
            ("open a\x00b.tla", "path"),
            ("load-media a\x00b.wav", "path"),
            ("metadata import a\x00b.json", "path"),
            (f"{BY_TIME} --file a\x00b.csv --target-ordinal 1", "file"),
        ],
    )
    def test_a_nul_in_a_path_is_left_for_running(self, tmp_path, text, attribute):
        # A failed command, not a refused line (FR-013): running catches the
        # ValueError it gives (TimeLineAnnotator/project-management#279).
        assert "\x00" in getattr(command_of(tmp_path, text).args, attribute)

    @pytest.mark.parametrize(
        "text",
        [
            "timelines add marker --height 9",
            "timelines add marker --height 0",
            "timelines add marker --height -5",
            "timelines add harmony --height 40",
            "timelines add marker --beat-pattern 3",
            "timelines add beat --beat-pattern x",
            'metadata set "media length" 120',
            "metadata set-media-length 0",
            "metadata set-media-length -5",
            "metadata set-media-length nan",
            "metadata set-media-length inf",
            "load-media a.mp3 --duration-if-error -1",
            f"{BY_TIME} --file c.csv --target-ordinal 0",
        ],
    )
    def test_a_value_of_the_right_type_is_left_for_running(self, tmp_path, text):
        # build refuses these when the command runs, with its own texts.
        assert check(script_of(tmp_path, text)) == []

    def test_a_length_keeps_pythons_reading_of_a_number(self, tmp_path):
        length = command_of(tmp_path, "metadata set-media-length nan").args.seconds

        assert math.isnan(length)


class TestRefusedSpellings:
    def test_the_example_of_contracts_run(self, tmp_path, capsys):
        script = script_of(
            tmp_path,
            "clear\n"
            "clear\n"
            "clear\n"
            "timeline add beat --name Measures --beat-pattern 3\n"
            "clear\n"
            "clear\n"
            "clear\n"
            "timelines import beat -f beats.csv --target-name Measures\n"
            "clear\n"
            "clear\n"
            'metadata set composer "W. A. Mozart\n'
            "save K279-1.tla\n",
        )

        for problem in check(script):
            problem.report().print(SCRIPT)

        captured = capsys.readouterr()
        assert captured.err == (
            'import-script.txt, line 4: "timeline" isn\'t a command: use "timelines"\n'
            'import-script.txt, line 8: "-f" isn\'t an option of timelines import beat:'
            ' use "--file"\n'
            "import-script.txt, line 11: a quote isn't closed\n"
        )
        assert captured.out == ""

    def test_spec_user_story_1_scenario_5(self, tmp_path):
        # The line is reported with the right spellings, and with the rest of
        # what's wrong with it.
        assert refusals(tmp_path, "timeline import beat -f beats.csv\n") == [
            (1, '"timeline" isn\'t a command: use "timelines"'),
            (1, '"-f" isn\'t an option of timelines import beat: use "--file"'),
            (1, "the argument --target-name or --target-ordinal is required"),
        ]

    def test_spec_user_story_2_scenario_6(self, tmp_path):
        text = "clear\n" * 39 + "generate-scripts here\n" + "clear\n"

        assert refusals(tmp_path, text) == [
            (40, '"generate-scripts" isn\'t a command'),
        ]

    def test_several_bad_lines_are_all_reported(self, tmp_path):
        text = 'tl add beat\nclear\nsave\nabout\n"a\nclear --force --now\n'

        assert refusals(tmp_path, text) == [
            (1, '"tl" isn\'t a command: use "timelines"'),
            (3, "the argument PATH is required"),
            (4, '"about" isn\'t a command'),
            (5, "a quote isn't closed"),
            (6, '"--now" isn\'t an option of clear'),
        ]

    @pytest.mark.parametrize(
        "text,wrong,right",
        [
            ("timeline add beat", "timeline", "timelines"),
            ("tl add beat", "tl", "timelines"),
            ("timelines add hrc", "hrc", "hierarchy"),
            ("timelines add mrk", "mrk", "marker"),
            ("timelines add bea", "bea", "beat"),
            ("timelines add --name A hrc", "hrc", "hierarchy"),
            (f"timelines import hrc by-time --file c.csv {TARGET}", "hrc", "hierarchy"),
            (
                f"timelines import mrk by-measure --file c.csv {TARGET}"
                " --reference-tl-ordinal 1",
                "mrk",
                "marker",
            ),
            (f"timelines import bea --file c.csv {TARGET}", "bea", "beat"),
        ],
    )
    def test_a_command_of_tilias_other_spellings(self, tmp_path, text, wrong, right):
        assert whys(tmp_path, text) == [f'"{wrong}" isn\'t a command: use "{right}"']

    @pytest.mark.parametrize(
        "text,command,wrong,right",
        [
            ("timelines add beat -n M", "timelines add", "-n", "--name"),
            ("timelines add beat -e 40", "timelines add", "-e", "--height"),
            ("timelines add beat -b 3", "timelines add", "-b", "--beat-pattern"),
            ("load-media a.wav -s no", "load-media", "-s", "--scale-timelines"),
            (
                "metadata set-media-length 3 -s no",
                "metadata set-media-length",
                "-s",
                "--scale-timelines",
            ),
            (f"{BEAT} -f c.csv {TARGET}", BEAT, "-f", "--file"),
            (f"{BEAT} --file c.csv -n Chords", BEAT, "-n", "--target-name"),
            (f"{BEAT} --file c.csv -o 3", BEAT, "-o", "--target-ordinal"),
            (f"{BY_TIME} -f c.csv {TARGET}", BY_TIME, "-f", "--file"),
        ],
    )
    def test_a_short_option(self, tmp_path, text, command, wrong, right):
        assert whys(tmp_path, text) == [
            f'"{wrong}" isn\'t an option of {command}: use "{right}"'
        ]

    @pytest.mark.parametrize(
        "text,command,wrong,right",
        [
            (f"{BEAT} --fil c.csv {TARGET}", BEAT, "--fil", "--file"),
            (f"{BEAT} --f c.csv {TARGET}", BEAT, "--f", "--file"),
            (f"{BEAT} --file c.csv --target-n C", BEAT, "--target-n", "--target-name"),
            (
                f"{BEAT} --file c.csv --target-o 3",
                BEAT,
                "--target-o",
                "--target-ordinal",
            ),
            (f"{BEAT} --fil=c.csv {TARGET}", BEAT, "--fil", "--file"),
            (
                f"{BY_MEASURE} --file c.csv --target-ordinal 3 --reference-tl-n M",
                BY_MEASURE,
                "--reference-tl-n",
                "--reference-tl-name",
            ),
            (
                "timelines add beat --beat-p 3",
                "timelines add",
                "--beat-p",
                "--beat-pattern",
            ),
            ("timelines add beat --na M", "timelines add", "--na", "--name"),
            ("timelines add beat --he 40", "timelines add", "--he", "--height"),
            ("save a.tla --over", "save", "--over", "--overwrite"),
            ("clear --f", "clear", "--f", "--force"),
            ("load-media a.wav --d 3", "load-media", "--d", "--duration-if-error"),
            (
                "load-media a.wav --scale no",
                "load-media",
                "--scale",
                "--scale-timelines",
            ),
        ],
    )
    def test_an_abbreviated_option(self, tmp_path, text, command, wrong, right):
        assert whys(tmp_path, text) == [
            f'"{wrong}" isn\'t an option of {command}: use "{right}"'
        ]

    def test_a_line_is_read_on_with_the_option_its_hint_gives(self, tmp_path):
        assert whys(tmp_path, f"{BEAT} -f c.csv -o x") == [
            f'"-f" isn\'t an option of {BEAT}: use "--file"',
            f'"-o" isn\'t an option of {BEAT}: use "--target-ordinal"',
            "x is not a valid target ordinal.",
        ]

    @pytest.mark.parametrize(
        "text,command,wrong,first,second",
        [
            (
                f"{BEAT} --file c.csv --target C",
                BEAT,
                "--target",
                "--target-name",
                "--target-ordinal",
            ),
            (
                f"{BEAT} --file c.csv --t C",
                BEAT,
                "--t",
                "--target-name",
                "--target-ordinal",
            ),
            (
                f"{BY_MEASURE} --file c.csv --target-ordinal 1 --reference-tl M",
                BY_MEASURE,
                "--reference-tl",
                "--reference-tl-name",
                "--reference-tl-ordinal",
            ),
        ],
    )
    def test_a_prefix_of_two_options_names_both(
        self, tmp_path, text, command, wrong, first, second
    ):
        # And no more than that: which one was meant can't be read on.
        assert whys(tmp_path, text) == [
            f'"{wrong}" isn\'t an option of {command}: use "{first}" or "{second}"'
        ]

    @pytest.mark.parametrize(
        "text,command,option",
        [
            ("save a.tla --bogus", "save", "--bogus"),
            ("save a.tla --bogus=1", "save", "--bogus"),
            ("save a.tla -x", "save", "-x"),
            # An option of another command, or of no other spelling here.
            ("clear --overwrite", "clear", "--overwrite"),
            ("save a.tla --force", "save", "--force"),
            ("save a.tla -f", "save", "-f"),
            ("save a.tla -o", "save", "-o"),
            ("metadata import a.json -f", "metadata import", "-f"),
            ("timelines add beat --row-height 3", "timelines add", "--row-height"),
            # What tilia run doesn't take, though TiLiA does.
            ("save a.tla --help", "save", "--help"),
            ("save a.tla -h", "save", "-h"),
            (
                f"{BY_TIME} --file c.csv {TARGET} --reference-tl-name M",
                BY_TIME,
                "--reference-tl-name",
            ),
            (
                f"{BEAT} --file c.csv {TARGET} --reference-tl-ordinal 1",
                BEAT,
                "--reference-tl-ordinal",
            ),
            # A value can't start with "-", without "--" or "=".
            ("metadata set title -foo", "metadata set", "-foo"),
            ("metadata set tempo -1e5", "metadata set", "-1e5"),
            # The case of a letter is a spelling too.
            ("save a.tla --Overwrite", "save", "--Overwrite"),
        ],
    )
    def test_any_other_option(self, tmp_path, text, command, option):
        assert whys(tmp_path, text) == [f'"{option}" isn\'t an option of {command}']


class TestRefusedCommands:
    @pytest.mark.parametrize(
        "text,word",
        [
            # FR-012's other commands of TiLiA 0.7's, spelled right.
            ("script other.txt", "script"),
            ("components add", "components"),
            ("export a.json", "export"),
            ("generate-scripts here", "generate-scripts"),
            ("about", "about"),
            ("quit", "quit"),
            ("range merge", "range"),
            # TiLiA's aliases of those.
            ("exit", "exit"),
            ("q", "q"),
            # Words of no command.
            ("nonsense", "nonsense"),
            ("Timelines add beat", "Timelines"),
            ("hrc", "hrc"),
            ("--file a.csv", "--file"),
            ('""', ""),
            ("  # not a comment", "#"),
            ('"timelines add" beat', "timelines add"),
            ("save\ta.tla", "save\ta.tla"),
        ],
    )
    def test_a_line_that_starts_with_no_command(self, tmp_path, text, word):
        assert whys(tmp_path, text) == [f'"{word}" isn\'t a command']

    @pytest.mark.parametrize(
        "text,typed,right",
        [
            # FR-012's other commands of TiLiA 0.7's, spelled right.
            ("metadata show", "metadata show", METADATA),
            ("timelines list", "timelines list", TIMELINES),
            ("timelines move 1 2", "timelines move", TIMELINES),
            ("timelines remove 1", "timelines remove", TIMELINES),
            ("timelines beat fill", "timelines beat", TIMELINES),
            (
                "timelines import score --file a.mxl --target-ordinal 1",
                "timelines import score",
                '"timelines import beat", "timelines import marker",'
                ' "timelines import hierarchy", "timelines import range",'
                ' "timelines import harmony" or "timelines import pdf"',
            ),
            # An option where the next word should be.
            ("timelines --name A", "timelines --name", TIMELINES),
            # A word that isn't there.
            ("metadata", "metadata", METADATA),
            ("timelines", "timelines", TIMELINES),
            ("timelines import marker", "timelines import marker", BY),
            (
                "timelines import marker --file a.csv",
                "timelines import marker --file",
                BY,
            ),
        ],
    )
    def test_a_line_that_stops_inside_a_command(self, tmp_path, text, typed, right):
        assert whys(tmp_path, text) == [f'"{typed}" isn\'t a command: use {right}']

    def test_a_word_spelled_otherwise_before_the_one_it_stops_at(self, tmp_path):
        assert whys(tmp_path, "tl list") == [
            '"tl" isn\'t a command: use "timelines"',
            f'"timelines list" isn\'t a command: use {TIMELINES}',
        ]

    @pytest.mark.parametrize("kind", ["range", "score", "pdf", "audiowave", "Beat", ""])
    def test_timelines_add_of_another_kind(self, tmp_path, kind):
        # FR-012: they come with WP28. Quoted, for the empty one.
        assert whys(tmp_path, f'timelines add "{kind}"') == [
            f'"{kind}" isn\'t a kind of timelines add:'
            ' use "beat", "hierarchy", "marker" or "harmony"'
        ]


class TestRefusedArguments:
    @pytest.mark.parametrize(
        "text,missing",
        [
            ("save", ["PATH"]),
            ("save --overwrite", ["PATH"]),
            ("open", ["PATH"]),
            ("load-media", ["PATH"]),
            ("metadata import", ["PATH"]),
            ("metadata set", ["FIELD", "VALUE"]),
            ("metadata set composer", ["VALUE"]),
            ("metadata set-media-length", ["SECONDS"]),
            ("metadata set-media-length --scale-timelines no", ["SECONDS"]),
            ("timelines add", ["KIND"]),
            ("timelines add --name Chords", ["KIND"]),
            (f"{BEAT} {TARGET}", ["--file"]),
            (f"{BY_TIME} {TARGET}", ["--file"]),
        ],
    )
    def test_an_argument_it_needs(self, tmp_path, text, missing):
        assert whys(tmp_path, text) == [
            f"the argument {name} is required" for name in missing
        ]

    @pytest.mark.parametrize(
        "text,why",
        [
            (
                f"{BEAT} --file c.csv",
                "the argument --target-name or --target-ordinal is required",
            ),
            (
                f"{BEAT} --file c.csv {TARGET} --target-ordinal 3",
                "--target-name and --target-ordinal can't both be given",
            ),
            (
                f"{BY_MEASURE} --file c.csv {TARGET}",
                "the argument --reference-tl-name or --reference-tl-ordinal is required",
            ),
            (
                f"{BY_MEASURE} --file c.csv {TARGET}"
                " --reference-tl-name M --reference-tl-ordinal=1",
                "--reference-tl-name and --reference-tl-ordinal can't both be given",
            ),
        ],
    )
    def test_one_of_two_options(self, tmp_path, text, why):
        assert whys(tmp_path, text) == [why]

    def test_all_that_a_line_misses(self, tmp_path):
        assert whys(tmp_path, BY_MEASURE) == [
            "the argument --file is required",
            "the argument --target-name or --target-ordinal is required",
            "the argument --reference-tl-name or --reference-tl-ordinal is required",
        ]

    @pytest.mark.parametrize(
        "text,command,extra",
        [
            ("save a.tla b.tla", "save", "b.tla"),
            ("save my file.tla", "save", "file.tla"),
            ("save a.tla  --overwrite", "save", ""),
            ("clear now", "clear", "now"),
            ("metadata set a b c", "metadata set", "c"),
            ("open a.tla -- b.tla", "open", "b.tla"),
            (f"{BEAT} --file c.csv {TARGET} more", BEAT, "more"),
        ],
    )
    def test_an_argument_too_many(self, tmp_path, text, command, extra):
        assert whys(tmp_path, text) == [f'"{extra}" isn\'t an argument of {command}']

    @pytest.mark.parametrize(
        "text,option",
        [
            ("timelines add beat --name", "--name"),
            ("timelines add beat --height", "--height"),
            ("timelines add beat --beat-pattern", "--beat-pattern"),
            ("timelines add beat --beat-pattern --name A", "--beat-pattern"),
            (f"{BEAT} {TARGET} --file", "--file"),
            (f"{BEAT} --file c.csv --target-name", "--target-name"),
            (f"{BEAT} --file c.csv --target-ordinal", "--target-ordinal"),
            ("load-media a.wav --duration-if-error", "--duration-if-error"),
            ("load-media a.wav --scale-timelines", "--scale-timelines"),
        ],
    )
    def test_an_option_without_its_value(self, tmp_path, text, option):
        assert whys(tmp_path, text) == [f"{option} needs a value"]

    @pytest.mark.parametrize(
        "text,option",
        [
            ("save a.tla --overwrite=yes", "--overwrite"),
            ("clear --force=1", "--force"),
        ],
    )
    def test_an_option_that_takes_no_value(self, tmp_path, text, option):
        assert whys(tmp_path, text) == [f"{option} takes no value"]

    @pytest.mark.parametrize(
        "text,why",
        [
            ("timelines add beat --height abc", "abc is not a valid height."),
            ("timelines add beat --height 12.5", "12.5 is not a valid height."),
            ('timelines add beat --height ""', "an empty value is not a valid height."),
            (
                f"{BEAT} --file c.csv --target-ordinal x",
                "x is not a valid target ordinal.",
            ),
            (
                f"{BY_MEASURE} --file c.csv --target-ordinal 1 --reference-tl-ordinal x",
                "x is not a valid reference tl ordinal.",
            ),
            ("metadata set-media-length abc", NOT_A_LENGTH.format("abc")),
            ('metadata set-media-length ""', NOT_A_LENGTH.format("")),
            ("load-media a.mp3 --duration-if-error abc", NOT_A_LENGTH.format("abc")),
        ],
    )
    def test_a_value_of_the_wrong_type(self, tmp_path, text, why):
        assert whys(tmp_path, text) == [why]

    @pytest.mark.parametrize(
        "text,wrong",
        [
            (
                "metadata set-media-length --scale-timelines maybe abc",
                [NOT_A_SCALE.format("maybe"), NOT_A_LENGTH.format("abc")],
            ),
            (
                f"{BY_MEASURE} --file c.csv --target-ordinal x"
                " --reference-tl-ordinal y",
                [
                    "x is not a valid target ordinal.",
                    "y is not a valid reference tl ordinal.",
                ],
            ),
            (
                "load-media a.wav --duration-if-error abc --scale-timelines maybe",
                [NOT_A_LENGTH.format("abc"), NOT_A_SCALE.format("maybe")],
            ),
        ],
    )
    def test_each_wrong_value_is_reported(self, tmp_path, text, wrong):
        assert whys(tmp_path, text) == wrong

    @pytest.mark.parametrize(
        "command", ["load-media a.wav", "metadata set-media-length 3"]
    )
    def test_scale_timelines_takes_tilias_values(self, tmp_path, command):
        assert whys(tmp_path, f"{command} --scale-timelines maybe") == [
            '"maybe" isn\'t a value of --scale-timelines: use "yes", "no" or "prompt"'
        ]


class TestDashes:
    @pytest.mark.parametrize("text", ["clear --", "open a.tla --", "save a.tla --"])
    def test_a_lone_double_dash_ends_the_options_and_is_no_argument(
        self, tmp_path, text
    ):
        assert whys(tmp_path, text) == []

    def test_an_option_after_a_double_dash_is_not_given(self, tmp_path):
        assert whys(tmp_path, f"{BEAT} {TARGET} -- --file c.csv") == [
            "the argument --file is required",
            EXTRA.format("--file"),
            EXTRA.format("c.csv"),
        ]
        assert whys(tmp_path, f"{BEAT} --file c.csv -- --target-name C") == [
            "the argument --target-name or --target-ordinal is required",
            EXTRA.format("--target-name"),
            EXTRA.format("C"),
        ]


class TestScaleTimelinesDefault:
    @pytest.mark.parametrize(
        "text", ["load-media a.wav", "metadata set-media-length 3"]
    )
    def test_a_line_that_does_not_say_asks(self, tmp_path, text):
        assert command_of(tmp_path, text).args.scale_timelines == "prompt"


class TestHarmonyExtra:
    @pytest.mark.parametrize(
        "text",
        [
            f"timelines import harmony by-time --file c.csv {TARGET}",
            f"timelines import harmony by-measure --file c.csv {TARGET}"
            " --reference-tl-ordinal 1",
        ],
    )
    def test_an_import_needs_it(self, tmp_path, monkeypatch, text):
        monkeypatch.setattr(importers, "harmony_available", lambda: False)
        script = script_of(tmp_path, text)

        problems = check(script)

        assert [(p.line.number, p.why) for p in problems] == [(1, HARMONY_EXTRA)]
        assert script.lines[0].command is None

    def test_its_report_names_the_command_that_installs_it(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(importers, "harmony_available", lambda: False)
        script = script_of(
            tmp_path, f"clear\ntimelines import harmony by-time --file c.csv {TARGET}\n"
        )

        for problem in check(script):
            problem.report().print(SCRIPT)

        assert capsys.readouterr().err == (
            "import-script.txt, line 2:"
            ' harmony import needs: pip install "tilia-core[harmony]"\n'
        )

    def test_it_is_said_with_what_else_the_line_misses(self, tmp_path, monkeypatch):
        monkeypatch.setattr(importers, "harmony_available", lambda: False)

        assert whys(tmp_path, f"timelines import harmony by-time {TARGET}") == [
            HARMONY_EXTRA,
            "the argument --file is required",
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "timelines add harmony --name Chords",
            f"{BY_TIME} --file c.csv {TARGET}",
            # A name is no kind.
            f"{BY_TIME} --file harmony.csv --target-name harmony",
            'metadata set "timelines import harmony" by-time',
        ],
    )
    def test_nothing_else_does(self, tmp_path, monkeypatch, text):
        monkeypatch.setattr(importers, "harmony_available", lambda: False)

        assert check(script_of(tmp_path, text)) == []


class TestTheCheck:
    def test_a_refused_line_has_no_command_and_the_others_have_theirs(self, tmp_path):
        script = script_of(tmp_path, 'clear\nnonsense\n"a\nsave a.tla\n')

        check(script)

        assert [line.command is None for line in script.lines] == [
            False,
            True,
            True,
            False,
        ]
        assert script.lines[0].command.name == "clear"
        assert script.lines[3].command.name == "save"

    def test_it_gives_the_same_answer_twice(self, tmp_path):
        script = script_of(tmp_path, "clear\nnonsense\n")

        first = [(p.line.number, p.why) for p in check(script)]

        assert [(p.line.number, p.why) for p in check(script)] == first
        assert script.lines[0].command.name == "clear"

    def test_a_report_of_a_refused_line_is_a_problem(self, tmp_path):
        problem = check(script_of(tmp_path, "nonsense\n"))[0]

        report = problem.report()

        assert report.kind == "problem"
        assert report.message == problem.why
        assert report.line is problem.line
        assert report.row is None

    def test_a_nul_in_a_refused_line_prints_on_its_line(self, tmp_path, capsys):
        for problem in check(script_of(tmp_path, "non\x00sense\n")):
            problem.report().print(SCRIPT)

        assert capsys.readouterr().err == (
            'import-script.txt, line 1: "non\\x00sense" isn\'t a command\n'
        )


class TestTheParser:
    """What argparse does that its version decides, and tests of the check can't reach
    on every version of Python."""

    def test_it_raises_where_argparse_would_exit(self):
        with pytest.raises(_ParserError, match="anything"):
            _parser("save").error("anything")

    def test_a_missing_argument_said_through_error(self, tmp_path, monkeypatch):
        # Some versions of Python call error() for this even with
        # exit_on_error=False, and others raise ArgumentError.
        def stop(parser, args):
            parser.error("the following arguments are required: PATH")

        monkeypatch.setattr(_Parser, "parse_known_args", stop)

        assert whys(tmp_path, "save") == ["the argument PATH is required"]

    def test_what_it_says_that_names_no_argument_is_given_as_it_is(
        self, tmp_path, monkeypatch
    ):
        def stop(parser, args):
            parser.error("something new")

        monkeypatch.setattr(_Parser, "parse_known_args", stop)

        assert whys(tmp_path, "save") == ["something new"]

    def test_it_takes_no_abbreviation(self):
        args, extras = _parser("save").parse_known_args(["a.tla", "--over"])

        assert extras == ["--over"]
        assert args.overwrite is False


def test_the_kinds_a_script_imports_are_the_importers_own():
    # One list, in `importers`: a kind added there is a command here.
    from tilia_core import importers
    from tilia_core.commands import _script

    for kind in importers.IMPORTED_KINDS:
        assert f"timelines import {kind} by-time" in _script._COMMANDS
        assert f"timelines import {kind} by-measure" in _script._COMMANDS
