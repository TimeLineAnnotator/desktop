from tilia_core.tql import explain, parse


def test_delete_action():
    q = parse('bridge.modern[parent = "compound B"] -> DELETE -- gone')
    assert "delete each matched unit" in explain(q)


def test_tag_action_names_whose_units():
    q = parse('* IN "Form (A)" SAME * IN "Form (B)" -> TAG $0 "disagree" -- both')
    assert 'TAG $0 "disagree"' in explain(q)


def test_duration_in_bars():
    e = explain(parse('"compound B"[duration = 8 bars] IN form'))
    assert "the duration is 8 bars" in e, e


def test_duration_range_and_beat():
    e = explain(parse("*[duration = 7..9 bars AND duration != 1 beat]"))
    assert "between 7 and 9 bars" in e and "is not 1 beat" in e, e


def test_relation_within():
    e = explain(parse("HC IN cadences BEFORE PAC IN cadences WITHIN 1 bar"))
    assert e.endswith("within 1 bar."), e


def test_sequence_within():
    e = explain(parse("HC THEN PAC IN cadences WITHIN 8 bars"))
    assert (
        "labelled HC, followed by a unit labelled PAC, where consecutive units "
        "may be up to 8 bars apart"
    ) in e, e


def test_group_within():
    e = explain(parse("(a THEN b)+ WITHIN 2s"))
    assert "(a unit labelled a, followed by a unit labelled b)" in e, e


def test_distance_plus():
    e = explain(
        parse("PAC IN cadences DURING ST IN form WHERE $1.start >= $2.start + 4 bars")
    )
    assert "the start of $1 is at least the start of $2 plus 4 bars" in e, e


def test_distance_minus():
    e = explain(parse("a THEN b WHERE $2.end <= $1.end - 10 s"))
    assert "the end of $2 is at most the end of $1 minus 10s" in e, e


def test_starts_after_relation():
    e = explain(parse("ST IN form STARTS AFTER MT IN form WITHIN 16 bars"))
    assert e == (
        "A unit labelled ST in form that starts after a unit labelled MT in "
        "form, within 16 bars."
    ), e


def test_not_starts_before():
    assert "does not start before" in explain(parse("A NOT STARTS BEFORE B"))


def test_target_step():
    e = explain(parse("* THEN @bridge THEN * IN form"))
    assert "a unit labelled bridge (the result), directly followed by any unit" in e, e


def test_label_word_condition_reads_as_step():
    assert "where it is labelled verse" in explain(parse("*[label = verse]"))


def test_label_word_condition_on_unit():
    e = explain(parse("a THEN b WHERE $2.label != verse"))
    assert "$2 is not labelled verse" in e


def test_label_word_condition_on_any_unit():
    e = explain(parse("a THEN b WHERE $0.label != x"))
    assert "no unit of the match is labelled x" in e


def test_label_string_condition_is_a_field_comparison():
    assert 'the label is "Verse"' in explain(parse('*[label = "Verse"]'))


def test_percentages_of_the_piece():
    e = explain(parse("*[start >= 33% AND end <= 67%] IN form"))
    assert (
        "the start is at least 33% of the piece and the end is at most 67% of the "
        "piece"
    ) in e, e


def test_percentage_range():
    e = explain(parse("*[start = 25%..75%]"))
    assert "between 25 and 75% of the piece" in e, e


def test_relation_reads_as_sentence():
    e = explain(parse("PAC IN cadences ENDS MT IN form"))
    assert "is the last thing in" in e and e.endswith("."), e


def test_sequence_reads_as_sentence():
    e = explain(parse("verse+ THEN chorus IN form"))
    assert e.startswith("In form: one or more of a unit labelled verse"), e


def test_negated_contains():
    e = explain(parse("ST IN form NOT CONTAINS PAC IN cadences"))
    assert "contains no unit labelled PAC" in e, e
