from typing import Literal

import tilia.errors
import tilia.parsers
from tilia.requests import get, Get
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.dialogs.by_time_or_by_measure import ByTimeOrByMeasure
from tilia.ui.strings import UTF8_DECODE_FAILED
from tilia.ui.timelines.collection.collection import TimelineUIs
from tilia.parsers import get_import_function


def on_import_to_timeline(
    timeline_uis: TimelineUIs, tlkind: TlKind
) -> tuple[Literal["success", "failure", "cancelled"], list[str]]:
    if not _validate_timeline_kind_on_import(timeline_uis, tlkind):
        return "failure", [f"No timeline of kind {tlkind} found."]

    tls_of_kind = timeline_uis.get_timeline_uis_by_attr("TIMELINE_KIND", tlkind)
    if len(tls_of_kind) == 1:
        timeline_ui = tls_of_kind[0]
    else:
        timeline_ui = timeline_uis.ask_choose_timeline(
            "Import components from CSV",
            "Choose timeline where components will be created",
            tlkind,
        )

    if not timeline_ui:
        return "cancelled", ["User cancelled when choosing timeline."]

    timeline = get(Get.TIMELINE, timeline_ui.id)
    if timeline.components and not _confirm_timeline_overwrite_on_import():
        return "cancelled", ["User rejected components overwrite."]

    if tlkind == TlKind.SCORE_TIMELINE:
        time_or_measure = "measure"
        beat_tlui = _get_beat_timeline_ui_for_import_from_csv(timeline_uis)
        if not beat_tlui:
            return "failure", ["No beat timeline found for importing score timeline."]

        beat_tl = get(Get.TIMELINE, beat_tlui.id)
        success, path = get(
            Get.FROM_USER_FILE_PATH,
            "Import components",
            ["musicXML files (*.musicxml *.mxl, *.xml)"],
        )

    else:
        if tlkind == TlKind.BEAT_TIMELINE:
            time_or_measure = "time"
        else:
            success, time_or_measure = _get_by_time_or_by_measure_from_user()
            if not success:
                return "cancelled", [
                    "User cancelled when choosing by time or by measure."
                ]

        if time_or_measure == "measure":
            beat_tlui = _get_beat_timeline_ui_for_import_from_csv(timeline_uis)
            if not beat_tlui:
                return "failure", ["No beat timeline found for importing by measure."]

            beat_tl = get(Get.TIMELINE, beat_tlui.id)
        else:
            beat_tl = None

        success, path = get(
            Get.FROM_USER_FILE_PATH, "Import components", ["CSV files (*.csv)"]
        )

    if not success:
        return "cancelled", ["User cancelled when choosing file to import."]

    timeline.clear()

    func = get_import_function(tlkind, time_or_measure)
    if time_or_measure == "time":
        args = (timeline, path)
    elif time_or_measure == "measure":
        args = (timeline, beat_tl, path)
    else:
        raise ValueError("Invalid time_or_measure value.")  # pragma: no cover

    try:
        success, errors = func(*args)
    except UnicodeDecodeError:
        file_type = "musicXML" if tlkind == TlKind.SCORE_TIMELINE else "CSV"
        return "failure", [UTF8_DECODE_FAILED.format(path, file_type)]

    return ("success" if success else "failure"), errors


def _get_by_time_or_by_measure_from_user():
    dialog = ByTimeOrByMeasure()
    return (True, dialog.get_option()) if dialog.exec() else (False, None)


def _validate_timeline_kind_on_import(timeline_uis: TimelineUIs, tlkind: TlKind):
    if not timeline_uis.get_timeline_uis_by_attr("TIMELINE_KIND", tlkind):
        tilia.errors.display(
            tilia.errors.CSV_IMPORT_FAILED,
            f"No timelines of type '{tlkind}' found.",
        )
        return False
    return True


def _confirm_timeline_overwrite_on_import():
    return get(
        Get.FROM_USER_YES_OR_NO,
        "Import from CSV",
        "Selected timeline is not empty. Existing components will be deleted when importing. Are you sure you want to continue?",
    )


def _get_beat_timeline_ui_for_import_from_csv(timeline_uis: TimelineUIs):
    beat_tls = timeline_uis.get_timeline_uis_by_attr(
        "TIMELINE_KIND", TlKind.BEAT_TIMELINE
    )
    if not beat_tls:
        tilia.errors.display(
            tilia.errors.CSV_IMPORT_FAILED,
            "No beat timelines found. Must have a beat timeline if importing by measure.",
        )
        return
    elif len(beat_tls) == 1:
        return beat_tls[0]
    else:
        return timeline_uis.ask_choose_timeline(
            "Import components from CSV",
            "Choose timeline with measures to be used when importing",
            TlKind.BEAT_TIMELINE,
        )


def _display_import_from_csv_errors(success: bool, errors: list[str]):
    errors_str = "\n".join(errors)
    if success:
        tilia.errors.display(tilia.errors.CSV_IMPORT_SUCCESS_ERRORS, errors_str)
    else:
        tilia.errors.display(tilia.errors.CSV_IMPORT_FAILED, errors_str)
