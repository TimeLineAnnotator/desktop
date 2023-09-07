from . import basic


def last_selected_by_kind(kinds):
    return basic.compose(
        [(basic.by_kinds, (kinds,), {}), (basic.last_selected, (), {})]
    )
