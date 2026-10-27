from tilia_core import tql


def test_public_names():
    for name in ("parse", "explain", "format_error", "TQLError", "Query"):
        assert hasattr(tql, name), name


def test_explain_a_parsed_query():
    assert tql.explain(tql.parse("verse THEN chorus IN form")).startswith("In form:")
