from __future__ import annotations

import pytest

from tilia_library.chips import (
    Refused,
    as_word,
    replace_statement,
    selection,
    set_statement,
)


def message(call, *args, **kwargs):
    with pytest.raises(Refused) as caught:
        call(*args, **kwargs)
    return str(caught.value)


def test_any_joins_with_or():
    assert selection(["a", "b"], "any", False) == "a OR b"
    assert selection(["a", "b", "c"], "any", True) == "a OR b OR c"


def test_all_joins_with_a_slash_given_a_grammar():
    assert selection(["a", "b"], "all", True) == "a/b"
    assert selection(["a", "b", "c"], "all", True) == "a/b/c"


def test_a_single_category_is_the_word():
    assert selection(["a"], "all", True) == "a"
    assert selection(["a"], "any", False) == "a"


def test_all_needs_a_grammar():
    assert message(selection, ["a", "b"], "all", False) == (
        '"all" needs a label grammar: without one, a label has one category'
    )


def test_order_is_kept_and_duplicates_dropped():
    assert selection(["b", "a", "b"], "any", False) == "b OR a"


def test_nothing_selected_is_refused():
    assert message(selection, [], "any", True) == "select a category"


def test_unknown_mode_is_refused():
    assert message(selection, ["a"], "some", True) == 'mode is "any" or "all"'


@pytest.mark.parametrize("word", ["μετάβαση", "过渡", "מעבר", "🎵", "Überleitung"])
def test_categories_in_several_scripts_are_words(word):
    assert as_word(word) == word
    assert selection([word], "any", False) == word


def test_the_word_is_nfc():
    assert as_word("Überleitung") == "Überleitung"


def test_a_subtype_is_kept():
    assert selection(["bridge.modern"], "any", True) == "bridge.modern"


@pytest.mark.parametrize(
    "category",
    [
        "verse 2",
        'say"hi',
        "a/b",
        "a,b",
        "why?",
        "plus+",
        "star*",
        "then",
        "Or",
        "NOT",
        "--x",
        "*",
        ".x",
        "x.",
        "a..b",
        "a->b",
        "[a]",
        "a=b",
        "a$",
        "",
    ],
)
def test_categories_that_cannot_be_words_are_refused(category):
    assert as_word(category) is None
    assert message(selection, [category], "any", True) == (
        f"{category!r} can't be written in the query language yet: "
        "a category in a query is one word"
    )


def test_a_refused_category_among_others_is_named():
    assert "'verse 2'" in message(selection, ["a", "verse 2"], "any", True)


def test_set_escapes_quotes_and_backslashes():
    assert set_statement(["a"], "any", True, "label", 'say "hi"\\') == (
        'a -> SET label = "say \\"hi\\"\\\\"'
    )


def test_set_on_a_selection():
    assert set_statement(["a", "b"], "all", True, "comments", "x") == (
        'a/b -> SET comments = "x"'
    )


def test_set_refuses_an_unknown_field():
    assert message(set_statement, ["a"], "any", True, "start", "1")


def test_a_colour_is_rrggbb():
    assert (
        set_statement(["a"], "any", True, "color", "#a1B2c3")
        == 'a -> SET color = "#a1B2c3"'
    )
    for bad in ("red", "#fff", "a1b2c3", "#a1b2c3d"):
        assert message(set_statement, ["a"], "any", True, "color", bad) == (
            "a colour is #rrggbb"
        )


def test_set_refuses_what_the_selection_refuses():
    assert message(set_statement, [], "any", True, "label", "x") == "select a category"


def test_replace():
    assert replace_statement(["a"], "any", True, "label", "foo", "bar") == (
        'a WHERE label ~ /^(.*?)foo(.*)$/ -> SET label = "\\1bar\\2"'
    )


def test_replace_escapes_a_slash_in_the_pattern():
    assert replace_statement(["a"], "any", True, "label", "a/b", "c") == (
        'a WHERE label ~ /^(.*?)a\\/b(.*)$/ -> SET label = "\\1c\\2"'
    )


def test_an_escaped_slash_stays_as_it_is():
    assert "(.*?)a\\/b(.*)" in replace_statement(
        ["a"], "any", True, "label", "a\\/b", "c"
    )


def test_replace_escapes_quotes_in_the_replacement():
    assert replace_statement(["a"], "any", True, "label", "x", 'say "y"').endswith(
        '"\\1say \\"y\\"\\2"'
    )


def test_a_non_capturing_group_is_accepted():
    assert "(?:x|y)" in replace_statement(["a"], "any", True, "label", "(?:x|y)", "z")


def test_replace_refusals():
    def replace(pattern="x", replacement="y", **kwargs):
        return message(
            replace_statement,
            ["a"],
            "any",
            True,
            "label",
            pattern,
            replacement,
            **kwargs,
        )

    assert replace(pattern="") == "the pattern is empty"
    assert replace(pattern="(x)") == (
        "the pattern has groups of its own; use (?:…) instead"
    )
    assert replace(pattern="(?P<n>x)").startswith("the pattern has groups")
    assert replace(pattern="(x").startswith("the pattern isn't a regular expression: ")
    assert replace(replacement="a\\1") == "a replacement with \\ can't be written yet"
    assert replace(every=True) == (
        "replacing every occurrence can't be written in the query language yet"
    )


def test_replace_refuses_an_unknown_field():
    assert message(replace_statement, ["a"], "any", True, "start", "x", "y")
