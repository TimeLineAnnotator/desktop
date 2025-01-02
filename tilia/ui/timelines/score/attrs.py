from tilia.ui.windows.inspect import InspectRowKind

INSPECTOR_FIELDS = [
    ("Start", InspectRowKind.LABEL, None),
    ("End", InspectRowKind.LABEL, None),
    ("Start / end (metric)", InspectRowKind.LABEL, None),
    ("Note", InspectRowKind.LABEL, None),
    ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
]

FIELD_NAMES_TO_ATTRIBUTES = {
    attr: attr.lower().replace(" ", "_") for attr, *_ in INSPECTOR_FIELDS
}
