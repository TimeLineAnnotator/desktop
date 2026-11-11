"""A backslash outside a string is an error, not dropped
(TimeLineAnnotator/project-management#391): TQL has no escapes in words.
Strings keep their escapes, and a regular expression its own."""

import pytest

from tilia_core.tql import TQLError, explain, format_error, parse
from tilia_core.tql.syntax import lex


@pytest.mark.parametrize(
    "text, pos",
    [
        ("chorus\\? IN form", 6),
        ("\\[weak\\] IN form", 0),
        ("chorus/\\? IN form", 7),
    ],
)
def test_a_backslash_in_a_word_is_refused_where_it_is(text, pos):
    with pytest.raises(TQLError) as error:
        parse(text)

    assert (error.value.pos, error.value.end) == (pos, pos + 1)
    assert "outside a string" in error.value.msg
    assert "quote" in error.value.msg


def test_the_error_marks_the_backslash():
    text = "verse THEN chorus\\? IN form"
    with pytest.raises(TQLError) as error:
        parse(text)

    shown = format_error(text, error.value).splitlines()
    assert shown[1:] == ["  verse THEN chorus\\? IN form", "                   ^"]


def test_a_backslash_after_a_label_in_brackets_is_refused():
    with pytest.raises(TQLError) as error:
        parse("ST[continuation\\]] IN form")

    assert error.value.pos == 15


def test_a_string_keeps_its_escapes():
    text = '"say \\"hi\\" \\\\ there" IN form'

    strings = [t.value for t in lex(text) if t.type == "STRING"]

    assert strings == ['say "hi" \\ there']
    explain(parse(text))


def test_a_lone_backslash_in_a_string_is_kept():
    strings = [t.value for t in lex('"chorus\\?" IN form') if t.type == "STRING"]

    assert strings == ["chorus\\?"]


def test_a_regular_expression_keeps_its_backslashes():
    query = parse("* IN form WHERE label ~ /\\?/")

    assert "?" in explain(query)


def test_a_backslash_in_a_comment_is_part_of_the_comment():
    parse("verse IN form -- not chorus\\?")
