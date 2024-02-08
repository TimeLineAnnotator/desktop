from tilia.timelines.harmony.constants import MODE_TYPES
from tilia.ui.format import format_media_time
from tilia.ui.timelines.copy_paste import CopyAttributes
from tilia.ui.timelines.harmony.constants import ACCIDENTAL_TO_INT, NOTE_NAME_TO_INT
from tilia.ui.windows.inspect import InspectRowKind


def get_mode_inspect_args():
    return {"items": [(kind, kind) for kind in MODE_TYPES]}


def get_accidental_inspect_args():
    return {"items": [(acc, x) for acc, x in ACCIDENTAL_TO_INT.items()]}


def get_step_inspect_args():
    return {"items": [(name, value) for name, value in NOTE_NAME_TO_INT.items()]}


INSPECTOR_FIELDS = [
    ("Time", InspectRowKind.LABEL, None),
    ("Label", InspectRowKind.LABEL, None),
    ("Step", InspectRowKind.COMBO_BOX, get_step_inspect_args),
    ("Accidental", InspectRowKind.COMBO_BOX, get_accidental_inspect_args),
    ("Type", InspectRowKind.COMBO_BOX, get_mode_inspect_args),
    ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
]

FIELD_NAMES_TO_ATTRIBUTES = {
    attr: attr.lower().replace(" ", "_") for attr, *_ in INSPECTOR_FIELDS
}

DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
    by_element_value=[],
    by_component_value=[
        "step",
        "accidental",
        "type",
        "level",
        "comments",
    ],
    support_by_element_value=[],
    support_by_component_value=["time", "KIND"],
)


def get_inspector_dict(mode):
    return {
        "Label": mode.label,
        "Time": format_media_time(mode.get_data("time")),
        "Comments": mode.get_data("comments"),
        "Step": mode.get_data("step"),
        "Accidental": mode.get_data("accidental"),
        "Type": mode.get_data("type"),
    }
