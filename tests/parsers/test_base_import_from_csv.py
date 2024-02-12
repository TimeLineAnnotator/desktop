from tilia.parsers.csv.csv import (
    get_params_indices,
)

def test_get_params_columns():
    headers = ["_", "h1", "h2", "_", "h3"]
    expected = {"h1": 1, "h2": 2, "h3": 4}

    assert get_params_indices(["h1", "h2"], []) == {}
    assert get_params_indices(["h1", "h2", "h3"], headers) == expected
    assert get_params_indices(["_"], headers) == {"_": 0}
    assert get_params_indices(["notthere"], headers) == {}


