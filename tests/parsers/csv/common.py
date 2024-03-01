def assert_in_errors(string: str, errors: list[str]):
    all_errors = "".join(errors)
    assert string in all_errors
