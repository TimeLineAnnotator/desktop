from typing import Any

from tilia.parsers.csv.csv import display_column_not_found_error, AttributeData


def _get_attrs_indices(params: [str], headers: [str]) -> [int]:
    result = []

    for p in params:
        try:
            result.append(headers.index(p))
        except ValueError:
            result.append(None)

    return result


def _validate_required_attrs(params: [str], indices: [int | None]):
    for i, param in enumerate(params):
        if indices[i] is None:
            display_column_not_found_error(param)
            return False
    return True


def _parse_attr_data(
    row_data: dict[str:Any], attr_data: AttributeData, required_attrs: [str]
):
    attr_to_value = {}
    errors = []
    for attr, parse_func, i in attr_data:
        value = row_data[i]
        try:
            attr_to_value[attr] = parse_func(value)
        except ValueError:
            if attr in required_attrs:
                return False, [f"{value=} | {value} is not a valid {attr}"], {}
            else:
                errors.append(f"{value=} | {value} is not a valid {attr}")
    return True, "", attr_to_value


def _get_attr_data(
    attrs_with_parsers: [tuple[str:int]], indices: [int]
) -> [AttributeData]:
    return [
        (attr, parser, indices[i])
        for i, (attr, parser) in enumerate(attrs_with_parsers)
        if indices[i] is not None
    ]
