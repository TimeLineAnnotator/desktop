import re

import examples
import pytest

from tilia_core.tql import TQLError, format_error, parse
from tilia_core.tql.syntax import (
    Children,
    Compare,
    Downbeat,
    Group,
    RelCond,
    RelPattern,
    SeqPattern,
)


def lit0(text):
    return parse(text).pattern.seq.steps[0].item.term.alts[0].lits[0]


def first_cond(text):
    return parse(text).pattern.seq.steps[0].item.conds[0]


def refused(text):
    with pytest.raises(TQLError) as exc:
        parse(text)
    assert "not part of TQL" in exc.value.msg
    return exc.value


def test_every_printed_example_parses():
    for e in examples.load()["examples"]:
        try:
            parse(e.query)
        except TQLError as exc:
            pytest.fail(f"example {e.n} failed: {format_error(e.query, exc)}")


def test_steps_and_quantifiers():
    q = parse("verse+ THEN chorus IN form")
    assert isinstance(q.pattern, SeqPattern) and q.pattern.lane.text == "form"
    s0, s1 = q.pattern.seq.steps
    assert (s0.lo, s0.hi) == (1, None) and (s1.lo, s1.hi) == (1, 1)
    assert s0.item.term.alts[0].lits[0].text == "verse"


def test_children_and_relation_inside_brackets():
    q = parse("ST[continuation{2} AND CONTAINS PAC IN cadences] IN form")
    u = q.pattern.seq.steps[0].item
    assert isinstance(u.conds[0], Children) and isinstance(u.conds[1], RelCond)
    ch = u.conds[0].seq.steps[0]
    assert (ch.lo, ch.hi) == (2, 2)
    rel = u.conds[1].relation
    assert rel.rel == "CONTAINS" and rel.lane.text == "cadences"
    assert q.pattern.lane.text == "form"  # the outer IN


def test_relation_patterns():
    q = parse("* IN cadences ENDS ST IN form")
    assert isinstance(q.pattern, RelPattern)
    assert q.pattern.lane.text == "cadences" and q.pattern.relation.rel == "ENDS"
    assert q.pattern.relation.lane.text == "form"

    assert parse("ST IN form ENDS WITH PAC IN cadences").pattern.relation.rel == (
        "ENDS_WITH"
    )
    assert parse("* IN keys SAME START ST IN form").pattern.relation.rel == (
        "SAME_START"
    )
    q = parse("ST IN form NOT CONTAINS PAC IN cadences")
    assert q.pattern.relation.negate is True


def test_relation_within():
    q = parse("HC IN cadences BEFORE PAC IN cadences WITHIN 8 bars")
    assert q.pattern.relation.within.amount == 8
    assert q.pattern.relation.within.unit == "bar"
    q = parse("HC IN cadences BEFORE PAC IN cadences WITHIN 2s")
    assert q.pattern.relation.within.unit == "s"


def test_whole_lane_orders():
    assert parse("STARTS WITH intro IN form").pattern.order == "STARTS_WITH"
    g = parse("CONSISTS OF (verse THEN chorus){2} IN form").pattern.seq.steps[0]
    assert isinstance(g.item, Group) and (g.lo, g.hi) == (2, 2)


@pytest.mark.parametrize(
    "text, want",
    [
        ("(verse? THEN chorus?)* THEN bridge", (0, None)),
        ("((verse+)*)+", (1, None)),
        ("(a THEN b) *", (0, None)),
        ('"verse"* THEN chorus', (0, None)),
        ("ST[x]* THEN y", (0, None)),
    ],
)
def test_quantifier_after_an_item(text, want):
    st = parse(text).pattern.seq.steps[0]
    assert (st.lo, st.hi) == want


def test_nested_quantifiers_and_group_options():
    inner = parse("((verse+)*)+").pattern.seq.steps[0].item.options[0].steps[0]
    assert (inner.lo, inner.hi) == (0, None)
    q = parse("(verse THEN chorus) OR (verse THEN bridge) IN form")
    assert len(q.pattern.seq.steps[0].item.options) == 2


def test_brackets_and_which_in_belongs_to_what():
    q = parse("TR THEN ST[CONTAINS PAC IN cadences] IN form")
    assert q.pattern.lane.text == "form"
    assert q.pattern.seq.steps[1].item.conds[0].relation.lane.text == "cadences"

    q = parse("[color = pink] THEN bridge")
    assert q.pattern.seq.steps[0].item.term is None
    c = q.pattern.seq.steps[0].item.conds[0]
    assert c.field.name == "color" and c.value.kind == "word"
    assert c.value.value == "pink"

    q = parse("*[bar = 12..16 AND pass = 2] IN form")
    c0, c1 = q.pattern.seq.steps[0].item.conds
    assert c0.value.kind == "range" and c0.value.value == (12, 16)
    assert c1.value.value == 2


def test_times_and_positions():
    q = parse("* IN markers WHERE time > 1:30")
    assert q.where[0].value.value == 90
    assert isinstance(first_cond("PAC[downbeat] IN cadences"), Downbeat)
    c0 = first_cond("PAC[NOT downbeat AND bar = 9] IN cadences")
    assert isinstance(c0, Downbeat) and c0.negate is True
    assert first_cond("continuation[parent = ST] IN form").field.name == "parent"
    assert first_cond("*[bar.count = 3]").field.name == "bar.count"


def test_field_scopes():
    q = parse('V7[key = "c"] THEN I IN harmony WHERE file.composer = "Mozart"')
    assert q.where[0].field.scope == "file" and q.where[0].field.name == "composer"
    q = parse(r'WHERE tl.name ~ /^Form \((.+)\)$/ -> SET tl.name = "\1"')
    assert q.pattern is None and q.where[0].field.scope == "tl"
    assert q.action.assigns[0].value.value == r"\1"


def test_negated_conditions():
    assert first_cond("ST[NOT continuation]").negate is True
    assert first_cond("ST[NOT CONTAINS PAC IN cadences]").relation.negate is True
    assert isinstance(first_cond("*[NOT label = verse]"), Compare)


def test_literals():
    q = parse('bridge.modern THEN "Chorus 1" THEN /^_?v/ THEN verse/chorus')
    lits = [st.item.term.alts[0].lits for st in q.pattern.seq.steps]
    assert lits[0][0].text == "bridge" and lits[0][0].sub == "modern"
    assert lits[1][0].kind == "exact" and lits[1][0].text == "Chorus 1"
    assert lits[2][0].kind == "regex" and lits[2][0].text == "^_?v"
    assert [lit.text for lit in lits[3]] == ["verse", "chorus"]


def test_slash_with_a_wildcard():
    q = parse("chorus / *")
    kinds = [lit.kind for lit in q.pattern.seq.steps[0].item.term.alts[0].lits]
    assert kinds == ["word", "any"]


def test_punctuation_inside_words():
    q = parse('_?verse+ THEN "verse?"')
    assert q.pattern.seq.steps[0].item.term.alts[0].lits[0].text == "_?verse"
    assert q.pattern.seq.steps[0].lo == 1 and q.pattern.seq.steps[0].hi is None

    q = parse("A'.compound THEN b'|seq")
    assert q.pattern.seq.steps[0].item.term.alts[0].lits[0].text == "A'"
    assert q.pattern.seq.steps[1].item.term.alts[0].lits[0].text == "b'|seq"


def test_wildcard_with_a_quantifier():
    q = parse("*+ THEN bridge")
    assert q.pattern.seq.steps[0].item.term.alts[0].lits[0].kind == "any"
    assert (q.pattern.seq.steps[0].lo, q.pattern.seq.steps[0].hi) == (1, None)


def test_comments_and_string_values():
    assert len(parse("verse -- a comment\nTHEN chorus").pattern.seq.steps) == 2
    assert parse('verse WHERE label ~ "^v"').where[0].value.kind == "string"
    # a value glues the '?' back on
    assert parse("* WHERE label = verse?").where[0].value.value == "verse?"


def test_keywords_are_case_insensitive_and_contextual():
    q = parse("verse then chorus in form")
    assert len(q.pattern.seq.steps) == 2 and q.pattern.lane.text == "form"
    # 'end' is a label here
    assert lit0("end THEN coda").text == "end"
    assert parse("end/cad").pattern.seq.steps[0].item.term.alts[0].lits[1].text == "cad"


def test_regex_after_a_contextual_start():
    q = parse('* IN "A" SAME START /^v/ IN "B"')
    lit = q.pattern.relation.target.steps[0].item.term.alts[0].lits[0]
    assert lit.kind == "regex"


def test_set_action():
    q = parse('verse THEN chorus -> SET $2.label = "refrain", $1.color = "#ff0000"')
    assert q.action.verb == "SET"
    assert [a.field.index for a in q.action.assigns] == [2, 1]
    q = parse('* IN "Form (A)" SAME * IN "Form (B)" -> SET $2.label = $1.label')
    assert q.action.assigns[0].value.kind == "ref"


def test_group_action():
    q = parse('verse+ THEN chorus -> GROUP AS "A_compound" ON enclosing -> SKIP')
    a = q.action
    assert a.verb == "GROUP" and a.label == "A_compound" and a.color is None
    assert [(r.shape, r.resolution, r.tag) for r in a.on] == [
        ("enclosing", "SKIP", None)
    ]
    assert a.tag is None and a.unit is None


def test_group_action_with_a_colour_and_every_rule():
    q = parse(
        'a -> GROUP AS "x" COLOR "#ffc0cb" on FREE -> insert congruent -> add-category '
        'enclosing -> SKIP TAG "enclosing on free" crossing -> SKIP TAG ""'
    )
    assert (q.action.label, q.action.color) == ("x", "#ffc0cb")
    assert [(r.shape, r.resolution, r.tag) for r in q.action.on] == [
        ("free", "INSERT", None),
        ("congruent", "ADD-CATEGORY", None),
        ("enclosing", "SKIP", "enclosing on free"),
        ("crossing", "SKIP", ""),
    ]


def test_group_without_on_fills_no_defaults():
    assert parse('a -> GROUP AS "x"').action.on == []


def test_ungroup_action():
    a = parse("a THEN b -> UNGROUP -- gone").action
    assert a.verb == "UNGROUP" and a.on == []


def test_delete_action():
    q = parse('bridge.modern[parent = "compound B"] -> DELETE -- gone')
    assert q.action.verb == "DELETE"


def test_tag_and_untag_actions():
    q = parse("verse -> UNTAG *")
    assert q.action.verb == "UNTAG" and q.action.tag == "*" and q.action.unit is None
    q = parse('verse -> TAG "x" -- why we tag')  # a comment after the verb
    assert q.action.tag == "x"
    q = parse('verse -> TAG "a -- b"')  # but not inside its string
    assert q.action.tag == "a -- b"
    assert parse('verse -> TAG "say \\"hi\\""').action.tag == 'say "hi"'


def test_tag_and_untag_name_whose_units():
    q = parse('* IN "Form (A)" SAME * IN "Form (B)" -> TAG $0 "disagree" -- both')
    assert (q.action.unit, q.action.tag) == (0, "disagree")
    assert q.action.text == 'TAG $0 "disagree"'
    q = parse('a THEN b -> UNTAG $2 "x"')
    assert (q.action.verb, q.action.unit, q.action.tag) == ("UNTAG", 2, "x")
    q = parse("a THEN b -> UNTAG $1 *")
    assert (q.action.unit, q.action.tag) == (1, "*")


def test_a_string_holding_on_is_not_an_on_clause():
    q = parse('a -> GROUP AS "turn on"')
    assert q.action.label == "turn on" and q.action.on == []


@pytest.mark.parametrize(
    "text, want",
    [
        ('"compound B"[duration = 8 bars]', ("number", 8.0, "bar")),
        ("*[duration = 8bars]", ("number", 8.0, "bar")),
        ("*[duration >= 32 beats]", ("number", 32.0, "beat")),
        ("*[duration = 1 measure]", ("number", 1.0, "bar")),
        ("*[duration = 7..9 bars]", ("range", (7.0, 9.0), "bar")),
        ("*[duration = 7..9bars]", ("range", (7.0, 9.0), "bar")),
        ("*[duration = 7bars..9bars]", ("range", (7.0, 9.0), "bar")),
        ("*[duration > 30 s]", ("number", 30.0, None)),
        ("*[duration = 10..20 seconds]", ("range", (10.0, 20.0), None)),
        ("*[duration > 90seconds]", ("number", 90.0, None)),
    ],
)
def test_durations(text, want):
    v = first_cond(text).value
    assert (v.kind, v.value, v.unit) == want


def test_duration_in_a_where_keeps_its_raw_text():
    v = parse("verse IN form WHERE $1.duration = 8 bars").where[0].value
    assert v.unit == "bar" and v.raw == "8 bars"


@pytest.mark.parametrize(
    "text, form",
    [
        ("*[duration < 500 ms]", "500 ms"),
        ("*[duration < 500ms]", "500ms"),
        ("*[start > 500ms]", "500ms"),
        ("*[duration = 100..500ms]", "500ms"),
        ("*[duration = 500ms..2s]", "500ms"),
    ],
)
def test_values_in_milliseconds_are_refused(text, form):
    err = refused(text)
    assert err.msg == f"{form} is not part of TQL v0.1.0"
    assert text[err.pos : err.end] == form


def test_times_as_hours_minutes_seconds_are_refused():
    err = refused("* WHERE start > 1:30:00")
    assert err.msg == "1:30:00 is not part of TQL v0.1.0"
    assert (err.pos, err.end) == (16, 23)
    refused("*[start = 0:10:00..1:00:00]")
    refused("a THEN b WHERE $1.start >= $2.start + 1:30:00")


def test_minutes_and_seconds_are_still_times():
    assert parse("* WHERE start > 1:30").where[0].value.value == 90
    assert parse("* WHERE start = 0:05.5").where[0].value.value == 5.5


def test_a_percentage_with_duration_is_refused():
    err = refused("*[duration >= 10%]")
    assert err.msg == "duration >= 10% is not part of TQL v0.1.0"
    refused("*[duration = 10%..20%]")
    refused("a THEN b WHERE $1.duration >= 10%")


def test_unit_numbers_pick_nothing_by_name():
    err = refused("a THEN b WHERE $1.first.label = x")
    assert err.msg == "$1.first is not part of TQL v0.1.0"
    err = refused("a THEN b -> SET $2.last.label = x")
    assert err.msg == "$2.last is not part of TQL v0.1.0"
    refused('a THEN b -> TAG $1.last "x"')


def test_negative_unit_numbers_are_refused():
    err = refused("a THEN b -> UNTAG $-1 *")
    assert err.msg == "$-1 is not part of TQL v0.1.0"
    assert (err.pos, err.end) == (18, 21)
    refused("a THEN b WHERE $-1.label = x")


def test_fields_named_like_a_pick_stay_readable_after_a_scope():
    q = parse("a THEN b WHERE $1.tl.last = x")
    f = q.where[0].field
    assert (f.scope, f.name, f.index) == ("tl", "last", 1)


def test_within_in_milliseconds_stays_valid():
    q = parse("STARTS WITH intro THEN verse IN form WITHIN 500 ms WHERE level = 1")
    assert q.pattern.order == "STARTS_WITH" and q.pattern.within.unit == "ms"
    assert q.pattern.within.amount == 500 and q.where
    assert parse("a THEN b WITHIN 500ms").pattern.within.unit == "ms"


@pytest.mark.parametrize(
    "text, want",
    [
        ("$2.start + 16 bars", (16.0, "bar")),
        ("$2.start+16bars", (16.0, "bar")),
        ("$2.end - 2 beats", (-2.0, "beat")),
        ("$2.end -2beats", (-2.0, "beat")),
        ("$2.start + 10 s", (10.0, "s")),
        ("$2.start + 10s", (10.0, "s")),
        ("$2.start + 500 ms", (0.5, "s")),
        ("$2.time - 1:30", (-90.0, "s")),
        ("$2.start + 10", (10.0, "s")),
        ("$2.start + 1 measure", (1.0, "bar")),
    ],
)
def test_distances(text, want):
    v = parse(f"a THEN b WHERE $1.start >= {text}").where[0].value
    name = re.match(r"\$2\.([a-z]+)", text).group(1)
    assert (v.kind, v.value.index, v.value.name, v.offset, v.raw) == (
        "ref",
        2,
        name,
        want,
        text,
    )


def test_distances_in_a_where_with_other_conditions():
    q = parse(
        "PAC IN cadences DURING ST IN form WHERE $1.start >= $2.start + 4 bars AND "
        "$1.start < $2.end"
    )
    assert q.where[0].value.offset == (4.0, "bar") and q.where[1].value.offset is None
    q = parse("ST IN form AFTER MT IN form WHERE start >= $2.end + 2 bars")
    assert q.where[0].field.index is None and q.where[0].value.offset == (2.0, "bar")


def test_then_within_after_the_lane():
    p = parse("verse THEN chorus IN form WITHIN 2 bars").pattern
    assert isinstance(p, SeqPattern) and p.lane.text == "form"
    assert (p.within.amount, p.within.unit) == (2, "bar")
    assert parse("verse THEN chorus WITHIN 2 bars").pattern.within.unit == "bar"
    assert parse("verse+ IN form WITHIN 4s").pattern.within.unit == "s"
    assert parse("(a THEN b) IN form WITHIN 1 beat").pattern.within.unit == "beat"
    assert parse("verse THEN chorus IN form").pattern.within is None


def test_starts_before_and_starts_after():
    r = parse("ST IN form STARTS AFTER MT IN form WITHIN 16 bars").pattern.relation
    assert (r.rel, r.lane.text, r.within.unit) == ("STARTS_AFTER", "form", "bar")
    assert parse("A STARTS BEFORE B").pattern.relation.rel == "STARTS_BEFORE"
    assert parse("A starts after B").pattern.relation.rel == "STARTS_AFTER"
    assert parse("A NOT STARTS BEFORE B").pattern.relation.negate is True
    c0 = first_cond("ST[STARTS AFTER MT IN form] IN form")
    assert isinstance(c0, RelCond) and c0.relation.rel == "STARTS_AFTER"
    assert parse("* IN cadences STARTS ST IN form").pattern.relation.rel == "STARTS"
    assert parse("MT STARTS WITH presentation").pattern.relation.rel == "STARTS_WITH"
    target = parse("A STARTS AFTER /^v/").pattern.relation.target
    assert target.steps[0].item.term.alts[0].lits[0].kind == "regex"


def test_at_marks_the_target():
    q = parse("* THEN @bridge THEN * IN form")
    assert [st.target for st in q.pattern.seq.steps] == [False, True, False]
    assert q.has_target and q.slot_count == 3 and q.pattern.seq.steps[1].pos == 7
    assert not parse("* THEN bridge THEN * IN form").has_target
    assert not parse("ST IN form CONTAINS PAC IN cadences").has_target


def test_at_on_groups():
    st = parse("@(verse THEN chorus)+ THEN bridge").pattern.seq.steps[0]
    assert st.target and isinstance(st.item, Group) and (st.lo, st.hi) == (1, None)
    q = parse("(verse THEN @chorus)+ THEN bridge")
    assert q.has_target and not q.pattern.seq.steps[0].target
    assert q.pattern.seq.steps[0].item.options[0].steps[1].target
    assert parse("STARTS WITH @intro THEN verse IN form").pattern.seq.steps[0].target


def test_at_on_any_kind_of_step():
    steps = parse("x THEN @* THEN @/^v/").pattern.seq.steps
    assert steps[1].item.term.alts[0].lits[0].kind == "any"
    assert steps[2].target and steps[2].item.term.alts[0].lits[0].kind == "regex"
    assert parse("@[color = pink] THEN bridge").pattern.seq.steps[0].item.term is None
    assert lit0('"a@b" THEN c').text == "a@b"


def test_at_with_a_tag_action():
    q = parse('* THEN @bridge THEN * IN form -> TAG "inner"')
    assert q.has_target and q.action.tag == "inner"


@pytest.mark.parametrize(
    "text, want",
    [
        ("chorus[start >= 50%]", ("number", 50.0, "%")),
        ("*[end <= 67.5%]", ("number", 67.5, "%")),
        ("*[time > .5%]", ("number", 0.5, "%")),
        ("*[start = 25%..75%]", ("range", (25.0, 75.0), "%")),
        ("*[start = 25..75%]", ("range", (25.0, 75.0), "%")),
    ],
)
def test_percentages_of_the_piece(text, want):
    v = first_cond(text).value
    assert (v.kind, v.value, v.unit) == want


def test_percentages_in_where_and_distances():
    assert parse("chorus IN form WHERE start >= 50%").where[0].value.unit == "%"
    v = parse("a THEN b WHERE $2.start >= $1.start + 10%").where[0].value
    assert v.offset == (10.0, "%") and v.raw == "$1.start + 10%"


def test_text_in_any_script():
    assert lit0("Sätze").text == lit0('"Sätze"').text == "Sätze"
    assert lit0("/sätze/").text == "sätze"
    q = parse("副歌 THEN 主歌 IN form")
    assert [st.item.term.alts[0].lits[0].text for st in q.pattern.seq.steps] == [
        "副歌",
        "主歌",
    ]
    assert len(parse("ın THEN ſame").pattern.seq.steps) == 2  # not IN, not SAME
    lane = parse('* IN "Form (Éloïse)"').pattern.lane
    assert lane.text == "Form (Éloïse)"
    assert parse("* WHERE label = Sätze").where[0].value.value == "Sätze"


def test_error_offsets_count_characters_as_typed():
    with pytest.raises(TQLError) as exc:
        parse("Sätze THEN")
    assert exc.value.pos == len("Sätze THEN")


def test_deep_nesting_is_an_error():
    with pytest.raises(TQLError) as exc:
        parse("[" * 400 + "x" + "]" * 400)
    assert "too deeply" in exc.value.msg


def test_slot_count():
    assert parse("verse THEN chorus").slot_count == 2
    assert parse("ST IN form CONTAINS HC THEN PAC IN cadences").slot_count == 3
    assert parse("ST IN form NOT CONTAINS PAC IN cadences").slot_count == 1
    assert parse("WHERE level = 1").slot_count == 0


def test_query_keeps_its_text():
    assert parse("verse THEN chorus").text == "verse THEN chorus"


def test_error_str_is_the_message():
    with pytest.raises(TQLError) as exc:
        parse("verse THEN")
    assert str(exc.value) == exc.value.msg


def test_format_error_underlines_the_culprit():
    text = "verse THEN\nTHEN chorus"
    with pytest.raises(TQLError) as exc:
        parse(text)
    shown = format_error(text, exc.value)
    assert shown.splitlines()[1:] == ["  THEN chorus", "  ^^^^"]
    assert format_error("x", TQLError("plain")) == "plain"
