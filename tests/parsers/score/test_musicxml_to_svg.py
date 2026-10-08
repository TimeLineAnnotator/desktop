import json

import pytest

from tilia.parsers.score.musicxml_to_svg import load_svg_script

PREFIX = "loadSVG("


@pytest.mark.parametrize(
    "data",
    [
        "<work-title>Plain</work-title>",
        "<work-title>A `backtick` in the title</work-title>",
        "<credit-words>${alert(1)}</credit-words>",
        '<lyric><text>"quoted" \ backslash</text></lyric>',
        "<lyric><text>Grüß Gott 副歌\nnext line</text></lyric>",
        "<a>\u2028\u2029</a>",
    ],
)
def test_score_is_passed_as_a_string_literal(data):
    script = load_svg_script(data)
    assert script.startswith(PREFIX) and script.endswith(")")
    argument = script[len(PREFIX) : -1]
    # A double-quoted JSON string, never a template literal: `${...}` stays text.
    assert argument.startswith('"')
    assert json.loads(argument) == data
