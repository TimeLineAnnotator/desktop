from typing import Any, Callable

from tilia.parsers.csv.csv import display_column_not_found_error, AttributeData


def _get_attrs_indices(params: list[str], headers: list[str]) -> [int]:
    result = []

    for p in params:
        try:
            result.append(headers.index(p))
        except ValueError:
            result.append(None)

    return result


def _validate_required_attrs(params: list[str], indices: [int | None]):
    for i, param in enumerate(params):
        if indices[i] is None:
            return False, f'"{param}" not found on CSV header.'
    return True, ''


def _parse_attr_data(
    row_data: dict[str:Any], attr_data: list[AttributeData], required_attrs: list[str]
):
    attr_to_value = {}
    errors = []
    for attr, parse_func, i in attr_data:
        try:
            value = row_data[i]
        except IndexError:
            if attr in required_attrs:
                return False, [f"Missing value for {attr}"], {}
            else:
                errors.append(f"Missing value for {attr}")
                continue
        try:
            attr_to_value[attr] = parse_func(value)
        except ValueError as exc:
            appended_text = str(exc).replace('APPEND:', '') if str(exc).startswith('APPEND:') else ''
            if attr in required_attrs:
                return False, [f"{value=} is not a valid {attr}. " + appended_text], {}
            else:
                errors.append(f"{value=} is not a valid {attr}. " + appended_text)
    return True, errors, attr_to_value


def _get_attr_data(
    attrs_with_parsers: list[tuple[str, Callable]], indices: list[int]
) -> list[AttributeData]:
    return [
        (attr, parser, indices[i])
        for i, (attr, parser) in enumerate(attrs_with_parsers)
        if indices[i] is not None
    ]
