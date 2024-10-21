from tilia.ui.windows.inspect import InspectRowKind

INSPECTOR_FIELDS = [
    ('Start', InspectRowKind.LABEL, None),
    ('End', InspectRowKind.LABEL, None),
    ('Step', InspectRowKind.COMBO_BOX, None),
    ('Accidental', InspectRowKind.COMBO_BOX, None),
    ('Octave', InspectRowKind.COMBO_BOX, None),
    ('Label', InspectRowKind.LABEL, None),
    ('Comments', InspectRowKind.LABEL, None),
]

FIELD_NAMES_TO_ATTRIBUTES = {attr: attr.lower().replace(" ", "_") for attr, *_ in INSPECTOR_FIELDS}