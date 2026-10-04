import pytest

from tilia_core.tql import TQLError, parse

BAD = {
    "": "empty",
    "verse THEN": "label",
    "THEN verse": "keyword THEN",
    "verse THEN THEN chorus": "keyword THEN",
    "verse.": "subtype",
    "verse++": "more than one quantifier",
    "+": "quantifier needs a step",
    "verse{0}": "match nothing",
    "verse{3,2}": "min > max",
    "SRDC(verse THEN chorus)": "parentheses only group",
    "(verse)(chorus)": "parentheses only group",
    "()": "empty group",
    "NOT (verse THEN chorus)": "NOT does not apply to groups",
    "verse OR (a THEN b)": "OR between a label and a group",
    "(a THEN b) OR c": "OR after a group",
    "START THEN intro": "STARTS WITH",
    "bridge THEN END": "ENDS WITH",
    "verse THEN chorus DURING ST IN form": "left side of a relation",
    "verse+ DURING ST IN form": "no quantifier",
    "PAC DURING ST THEN MT": "relates two units",
    "DURING ST": "cannot start with",
    "ST[]": "empty brackets",
    "ST[continuation": "']'",
    "ST[presentation THEN continuation IN form]": "own hierarchy",
    "* WHERE level = 2 OR level = 3": "joined by AND",
    "* WHERE": "condition",
    "* WHERE time ~ 3": "regular expression",
    '* WHERE label ~ "*erse"': "not one",
    "* WHERE label ~ Form(": "parentheses only group",
    "* WHERE bar < 1..3": "range",
    "* WHERE bar = 5..1": "backwards",
    "verse WHERE $3.label = x": "has 1 unit",
    "verse[$1.label = x]": "numbered for WHERE",
    "WHERE $1.label = x": "no numbered units",
    "verse -> DESTROY": "expected an action",
    "verse -> DELETE $1": "takes nothing",
    "verse -> SET label": "'='",
    "verse -> GROUP": "GROUP expects",
    'verse GROUP AS "x"': "action",
    '"unterminated': "unterminated",
    "/unterminated": "unterminated",
    "/(/": "bad regular expression",
    "verse IN": "lane",
    "a WITHIN 3": "unit after the amount",
    "verse IN form WITHIN 2 bars": "single step",
    "verse? WITHIN 2 bars": "single step",
    "verse THEN chorus WITHIN 2 bars IN form": "IN goes before WITHIN",
    "verse THEN chorus IN form WITHIN 2 parsecs": "unit after the amount",
    "verse THEN chorus IN form WITHIN 2 bars WITHIN 1 bar": "unexpected keyword WITHIN",
    "PAC IN cadences BEFORE HC IN cadences WITHIN 3": "unit after the amount",
    "PAC IN cadences BEFORE HC IN cadences WITHIN 3 parsecs": "unit after the amount",
    "a => b": "unexpected",
    "verse {x}": "count",
    "!a": "'!'",
    "STARTS intro": "cannot start with",
    "*[bar = 8 bars]": "bar is a position",
    "*[start > 2 bars]": "go with duration",
    "*[file.duration = 8 bars]": "go with duration",
    "*[label = 8bars]": "go with duration",
    "*[duration = 1:30 bars]": "plain number",
    "*[duration = 90s bars]": "plain number",
    "*[duration = 7bars..9beats]": "mixes units",
    "*[duration = 1:30..9bars]": "mixes units",
    "*[duration ~ 8 bars]": "regular expression",
    "a THEN b WHERE $1.label = $2.label + 2 bars": "added to a time",
    "a THEN b WHERE $1.bar >= $2.bar + 16 bars": "printed bar number",
    "a THEN b WHERE $1.duration >= $2.duration + 2 bars": "added to a time",
    "a THEN b WHERE $1.start >= $2.tl.ordinal + 2": "added to a time",
    "a THEN b WHERE $1.start >= $2.start + bars": "a number with a unit",
    "a THEN b WHERE $1.start >= $2.start +": "needs a distance",
    "a THEN b WHERE $1.start >= $2.start + 2 parsecs": "unknown unit",
    "a THEN b WHERE $1.start >= $2.start + 2parsecs": "unknown unit",
    "a THEN b WHERE $1.start >= $2.start + -2 bars": "sign once",
    "a THEN b WHERE $1.start ~ $2.start + 2 bars": "not a time",
    "a THEN b -> SET $1.label = $2.start + 2 bars": "unexpected",
    "A ENDS BEFORE B": "not a relation",
    "A ENDS AFTER B": "not a relation",
    "STARTS AFTER B": "cannot start with",
    "A STARTS AFTER B THEN C": "relates two units",
    "@ST IN form CONTAINS PAC IN cadences": "needs no @",
    "ST IN form CONTAINS @PAC IN cadences": "needs no @",
    "ST IN form ENDS WITH HC THEN @PAC IN cadences": "needs no @",
    "ST[@presentation THEN continuation] IN form": "only tests",
    "ST[CONTAINS @PAC IN cadences] IN form": "only tests",
    "x THEN *[y[@z]] IN form": "only tests",
    "ST IN form CONTAINS PAC[NOT @x] IN cadences": "only tests",
    "* IN form WHERE ST[@x]": "only tests",
    "@@x": "one @",
    "x THEN @": "marks the step after it",
    "@ THEN x": "marks the step after it",
    "@+": "quantifier needs a step",
    "a@b": "'@'",
    'a THEN b -> TAG $3 "x"': "has 2 units",
    'WHERE level = 2 -> TAG $1 "x"': "no numbered units",
    'a THEN b -> TAG $1.label "x"': "marks units, not a field",
    'a THEN b -> GROUP $1 AS "x"': "GROUP expects",
    "*[bar >= 50%]": "percentage of the piece",
    "*[label = 50%]": "percentage of the piece",
    "*[file.duration = 50%]": "percentage of the piece",
    "*[start ~ 50%]": "regular expression",
    "*[start = 1:00..50%]": "mixes units",
    "*[start = 50%..2 bars]": "range",
    "*[start >= 50 %]": "without a space",
}

# Every query here raises a TQLError that names its fragment and points into the text.
# `*[start = 1:00..50%]` and the like keep m:ss times; h:mm:ss, milliseconds as a
# value, `$n.first`, `$n.last`, `$-1` and a percentage with `duration` are refused
# as "not part of TQL v0.1.0" (see test_tql_syntax.py).


@pytest.mark.parametrize("text, fragment", list(BAD.items()))
def test_bad_query_raises_with_a_position(text, fragment):
    with pytest.raises(TQLError) as exc:
        parse(text)
    assert fragment.lower() in exc.value.msg.lower()
    assert exc.value.pos is not None
    assert 0 <= exc.value.pos <= max(len(text), 1)
    assert exc.value.pos <= exc.value.end


@pytest.mark.parametrize(
    "text, fragment",
    [
        ('a THEN b -> GROUP AS ""', "non-empty label"),
        ("a -> GROUP AS x", "GROUP expects"),
        ('a -> GROUP AS "x" COLOR', "GROUP expects"),
        ("a -> UNGROUP now", "UNGROUP takes no arguments, got 'now'"),
        ("a -> TAG x", "TAG must be a double-quoted string, got 'x'"),
        ('a -> TAG ""', "TAG needs a non-empty value"),
        ("a -> UNTAG", "UNTAG must be a double-quoted string, got ''"),
        ('a -> UNTAG " "', "UNTAG needs a non-empty value"),
        ('a -> TAG "x" ON free -> INSERT', "ON only applies to GROUP"),
        ('a -> GROUP AS "x" ON', "ON clause is empty"),
        ('a -> GROUP AS "x" ON nowhere -> INSERT', "ON expects a shape name"),
        ('a -> GROUP AS "x" ON free INSERT', "ON free must be followed by '->'"),
        ('a -> GROUP AS "x" ON free -> MERGE', "unknown resolution 'MERGE' for free"),
        ('a -> GROUP AS "x" ON free -> INSERT free -> SKIP', "ON lists 'free' twice"),
        ('a -> GROUP AS "x" ON free -> INSERT now', "unexpected 'now' after INSERT"),
        ('a -> GROUP AS "x" ON free -> INSERT TAG "y"', "TAG may only follow SKIP"),
        ('a -> GROUP AS "x" ON free -> SKIP TAG y', "TAG must be a double-quoted"),
    ],
)
def test_bad_actions_keep_their_messages(text, fragment):
    with pytest.raises(TQLError) as exc:
        parse(text)
    assert fragment in exc.value.msg
    assert text[exc.value.pos :].startswith(("GROUP", "UNGROUP", "TAG", "UNTAG"))
    assert exc.value.end == len(text)


@pytest.mark.parametrize(
    "text, form",
    [
        ('a THEN b -> TAG $1.first "x"', "$1.first"),
        ("a THEN b WHERE $2.last.label = x", "$2.last"),
        ("a THEN b -> UNTAG $-1 *", "$-1"),
        ("* WHERE start > 1:30:00", "1:30:00"),
        ("*[duration < 500 ms]", "500 ms"),
        ("*[duration >= 10%]", "duration >= 10%"),
    ],
)
def test_forms_left_to_the_prototype(text, form):
    with pytest.raises(TQLError) as exc:
        parse(text)
    assert exc.value.msg == f"{form} is not part of TQL v0.1.0"
    assert text[exc.value.pos : exc.value.end] == form
