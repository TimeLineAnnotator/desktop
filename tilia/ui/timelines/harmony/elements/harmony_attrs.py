from tilia.timelines.harmony.constants import HARMONY_QUALITIES, NOTE_NAME_TO_INT
from tilia.ui.format import format_media_time
from tilia.ui.timelines.copy_paste import CopyAttributes
from tilia.ui.timelines.harmony.constants import ACCIDENTAL_TO_INT
from tilia.ui.timelines.harmony.utils import INT_TO_APPLIED_TO_SUFFIX, with_unknown
from tilia.ui.windows.inspect import InspectRowKind
from tilia_core.rules import FONT_TYPES, HARMONY_DISPLAY_MODES, get_inversion_amount

_INV_TO_STRING = {0: "", 1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}


def _inversion_items(quality: str, inversion: int) -> list[tuple[str, int]]:
    if quality not in HARMONY_QUALITIES:
        # Its inversions can't be known: the one the file holds.
        return [(_INV_TO_STRING.get(inversion, str(inversion)), inversion)]
    items = [(_INV_TO_STRING[i], i) for i in range(get_inversion_amount(quality) + 1)]
    return with_unknown(items, inversion)


def get_inversion_inspect_args():
    return {"items": []}


def get_quality_inspect_args():
    return {
        "items": [
            (quality.replace("-", " ").capitalize(), quality)
            for quality in HARMONY_QUALITIES
        ]
    }


def get_accidental_inspect_args():
    return {"items": [(acc, x) for acc, x in ACCIDENTAL_TO_INT.items()]}


def get_step_inspect_args():
    return {"items": [(name, value) for name, value in NOTE_NAME_TO_INT.items()]}


def get_display_mode_args():
    return {"items": [(mode, mode) for mode in HARMONY_DISPLAY_MODES]}


def get_custom_label_font_args():
    return {"items": [(type, type) for type in FONT_TYPES]}


def get_applied_to_inspect_args():
    return {"items": [(v, k) for k, v in INT_TO_APPLIED_TO_SUFFIX.items()]}


INSPECTOR_FIELDS = [
    ("Time", InspectRowKind.LABEL, None),
    ("Label", InspectRowKind.LABEL, None),
    ("Step", InspectRowKind.COMBO_BOX, get_step_inspect_args),
    ("Accidental", InspectRowKind.COMBO_BOX, get_accidental_inspect_args),
    ("Quality", InspectRowKind.COMBO_BOX, get_quality_inspect_args),
    ("Inversion", InspectRowKind.COMBO_BOX, get_inversion_inspect_args),
    ("Applied to", InspectRowKind.COMBO_BOX, get_applied_to_inspect_args),
    ("Display mode", InspectRowKind.COMBO_BOX, get_display_mode_args),
    ("Custom label", InspectRowKind.SINGLE_LINE_EDIT, None),
    ("Custom label font", InspectRowKind.COMBO_BOX, get_custom_label_font_args),
    ("Comments", InspectRowKind.MULTI_LINE_EDIT, None),
]


def get_field_names_to_attributes():
    result = {attr: attr.lower().replace(" ", "_") for attr, *_ in INSPECTOR_FIELDS}
    result["Custom label"] = "custom_text"
    result["Custom label font"] = "custom_text_font_type"
    return result


FIELD_NAMES_TO_ATTRIBUTES = get_field_names_to_attributes()


DEFAULT_COPY_ATTRIBUTES = CopyAttributes(
    values=[
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "comments",
        "display_mode",
        "custom_text",
        "custom_text_font_type",
    ],
    context=["time", "KIND"],
)


def get_inspector_dict(harmony):
    return {
        "__items_update": {
            "Step": with_unknown(
                get_step_inspect_args()["items"], harmony.get_data("step")
            ),
            "Accidental": with_unknown(
                get_accidental_inspect_args()["items"], harmony.get_data("accidental")
            ),
            "Quality": with_unknown(
                get_quality_inspect_args()["items"], harmony.get_data("quality")
            ),
            "Inversion": _inversion_items(
                harmony.get_data("quality"), harmony.get_data("inversion")
            ),
            "Applied to": with_unknown(
                get_applied_to_inspect_args()["items"], harmony.get_data("applied_to")
            ),
            "Display mode": with_unknown(
                get_display_mode_args()["items"], harmony.get_data("display_mode")
            ),
            "Custom label font": with_unknown(
                get_custom_label_font_args()["items"],
                harmony.get_data("custom_text_font_type"),
            ),
        },
        "Label": harmony.label,
        "Time": format_media_time(harmony.get_data("time")),
        "Comments": harmony.get_data("comments"),
        "Step": harmony.get_data("step"),
        "Accidental": harmony.get_data("accidental"),
        "Quality": harmony.get_data("quality"),
        "Inversion": harmony.get_data("inversion"),
        "Applied to": harmony.get_data("applied_to"),
        "Display mode": harmony.get_data("display_mode"),
        "Custom label": harmony.get_data("custom_text"),
        "Custom label font": harmony.get_data("custom_text_font_type"),
    }
