"""What TQL 0.2 adds to the language: AND, OR and NOT between labels, NOT on a
group, OR and parentheses between conditions, ``{,n}``, and the bars'
``bar.cadenza``, ``bar.movement`` and ``time_signature``."""

import copy

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import TQLError, explain, parse, syntax

FIXTURES = examples.load()["fixtures"]


def pop():
    return fixture_index.build_index(FIXTURES["pop"])


def pop_with_bars():
    """pop, with bar 5 a cadenza, a second movement from bar 17, in 4/4."""
    fx = copy.deepcopy(FIXTURES["pop"])
    beats = next(tl for tl in fx["timelines"] if tl["kind"] == "beats")
    beats.update(cadenzas=[5], restarts=[17], time_signature="4/4")
    return fixture_index.build_index(fx)


def found(index, text):
    got = tql.run(index, text)
    return [[(c.label, c.start) for s in m.slots for c in s] for m in got.matches]


# --------------------------------------------------------------------------- #
# Labels: NOT binds tightest, then AND, then OR
# --------------------------------------------------------------------------- #
def test_not_and_or_on_one_unit():
    q = parse("NOT (verse OR chorus) AND NOT bridge IN form")
    term = q.pattern.seq.steps[0].item.term
    assert [[(lit.text, lit.negate) for lit in alt.lits] for alt in term.alts] == [
        [("verse", True), ("chorus", True), ("bridge", True)]
    ]
    assert found(pop(), 'NOT (verse OR chorus) AND NOT bridge IN "Form (A)"') == [
        [("intro", 0.0)],
        [("A", 8.0)],
        [("A", 56.0)],
        [("outro", 120.0)],
    ]


def test_and_binds_tighter_than_or():
    alts = parse("a AND b OR c").pattern.seq.steps[0].item.term.alts
    assert [[lit.text for lit in alt.lits] for alt in alts] == [["a", "b"], ["c"]]
    alts = parse("a AND (b OR c)").pattern.seq.steps[0].item.term.alts
    assert [[lit.text for lit in alt.lits] for alt in alts] == [["a", "b"], ["a", "c"]]


def test_and_is_one_unit_with_both():
    assert found(pop(), 'verse AND chorus IN "Form (A)"') == []
    assert found(pop(), 'verse AND NOT chorus IN "Form (A)"') == [
        [("verse", 8.0)],
        [("verse", 24.0)],
        [("verse", 56.0)],
    ]


def test_a_chord_symbol_keeps_its_slash_in_a_chords_lane():
    lit = parse("C/E IN harmony").pattern.seq.steps[0].item.term.alts[0].lits[0]
    assert (lit.kind, lit.raw) == ("chord", "C/E")


@pytest.mark.parametrize("text", ["verse/chorus IN form", "verse/chorus"])
def test_a_slash_between_labels_names_and(text):
    with pytest.raises(TQLError, match="verse AND chorus is a unit with both"):
        parse(text)


# --------------------------------------------------------------------------- #
# NOT on a group, and quantifiers
# --------------------------------------------------------------------------- #
def test_not_on_a_group_of_single_units():
    text = 'NOT ((verse) OR (chorus[color = pink])) IN "Form (A)"'
    item = parse(text).pattern.seq.steps[0].item
    assert isinstance(item, syntax.Group) and item.negate
    assert found(pop(), text) == [
        [("intro", 0.0)],
        [("A", 8.0)],
        [("chorus", 40.0)],
        [("A", 56.0)],
        [("bridge", 88.0)],
        [("chorus", 104.0)],
        [("outro", 120.0)],
    ]


def test_not_on_a_run_suggests_two_ways():
    with pytest.raises(TQLError) as exc:
        parse("NOT (verse THEN chorus) IN form")
    assert "NOT verse THEN NOT chorus" in exc.value.msg
    assert "[NOT (verse THEN chorus)]" in exc.value.msg


def test_up_to_n_is_zero_to_n():
    step = parse("verse{,1} THEN chorus").pattern.seq.steps[0]
    assert (step.lo, step.hi) == (0, 1)
    assert found(pop(), 'verse{,1} THEN chorus IN "Form (A)"') == [
        [("verse", 24.0), ("chorus", 40.0)],
        [("verse", 56.0), ("chorus", 72.0)],
        [("chorus", 104.0)],
    ]


# --------------------------------------------------------------------------- #
# Conditions: OR, parentheses, and children in brackets
# --------------------------------------------------------------------------- #
def test_or_between_conditions():
    assert found(pop(), '*[level = 2 OR duration < 10] IN "Form (A)"') == [
        [("intro", 0.0)],
        [("A", 8.0)],
        [("A", 56.0)],
        [("outro", 120.0)],
    ]


def test_not_before_grouped_conditions():
    got = found(pop(), '*[NOT (level = 1 OR duration > 40)] IN "Form (A)"')
    assert got == [[("A", 56.0)]]


def test_and_outside_parentheses_joins_two_tests_of_children():
    # each A has a verse child and a chorus child, but no child is both
    assert found(pop(), 'A[verse AND chorus] IN "Form (A)"') == [
        [("A", 8.0)],
        [("A", 56.0)],
    ]
    assert found(pop(), 'A[(verse AND chorus)] IN "Form (A)"') == []


def test_or_in_where():
    q = parse('* IN "Form (A)" WHERE level = 2 OR label = intro')
    assert isinstance(q.where[0], syntax.AnyOf)


# --------------------------------------------------------------------------- #
# Bars: bar.cadenza, bar.movement, time_signature
# --------------------------------------------------------------------------- #
def test_bar_cadenza_is_true_or_false():
    index = pop_with_bars()
    assert found(index, "*[bar.cadenza = true] IN bars") == [[("5", 16.0)]]
    assert found(index, "*[bar.cadenza != false] IN bars") == [[("5", 16.0)]]
    assert len(found(index, "*[bar.cadenza = FALSE] IN bars")) == 31


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("*[bar.cadenza = 1] IN bars", "true or false, as in [bar.cadenza = true]"),
        ("*[bar.cadenza = yes] IN bars", "not yes"),
        ("*[bar.cadenza < true] IN bars", "compare it with = or !="),
    ],
)
def test_bar_cadenza_refuses_other_values(text, fragment):
    with pytest.raises(
        TQLError, match=fragment.replace("[", r"\[").replace("]", r"\]")
    ):
        parse(text)


def test_bar_movement_counts_from_one():
    index = pop_with_bars()
    assert found(index, '*[bar.movement = 2] IN "Form (A)"') == [
        [("chorus", 72.0)],
        [("bridge", 88.0)],
        [("chorus", 104.0)],
        [("outro", 120.0)],
    ]
    assert len(found(index, "*[bar.movement = 1] IN bars")) == 16


def test_true_is_a_word_elsewhere():
    v = parse("*[label = true]").pattern.seq.steps[0].item.conds[0].value
    assert (v.kind, v.value) == ("word", "true")


def test_time_signature_of_bars():
    index = pop_with_bars()
    assert len(found(index, '*[time_signature = "4/4"] IN bars')) == 32
    assert found(index, '*[time_signature = "3/4"] IN bars') == []
    assert found(index, '*[time_signature = "4/4"] IN "Form (A)"') == []


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("*[time_signature = 6/8] IN bars", 'quote a time signature: "6/8"'),
        ('*[time_signature = "6:8"] IN bars', "is not a time signature"),
        ('*[bar = 1] IN bars -> SET time_signature = "6/x"', "is not a time signature"),
        (
            "*[bar = 1] IN bars -> SET time_signature = 6",
            "takes a quoted time signature",
        ),
        ('verse IN form -> SET time_signature = "6/8"', "writes bars"),
        ('* -> SET time_signature = "6/8"', "writes bars"),
        ('*[bar = 1] THEN * IN bars -> SET time_signature = "6/8"', "writes bars"),
    ],
)
def test_time_signature_refusals(text, fragment):
    with pytest.raises(TQLError, match=fragment):
        parse(text)


@pytest.mark.parametrize("value", ["6/8", "2+2+3/8", "12/8"])
def test_set_time_signature_on_bars(value):
    q = parse(f'*[bar = 1..16] IN bars -> SET time_signature = "{value}"')
    (a,) = q.action.assigns
    assert (a.field.name, a.value.value) == ("time_signature", value)


# --------------------------------------------------------------------------- #
# Explanations
# --------------------------------------------------------------------------- #
def test_explain_not_and():
    e = explain(parse('NOT (verse OR chorus) AND NOT bridge IN "Form (A)"'))
    assert "not labelled verse, chorus or bridge" in e, e


def test_explain_bar_cadenza():
    e = explain(parse("*[bar.cadenza = true] IN bars"))
    assert "the bar.cadenza is true" in e, e
