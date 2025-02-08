from __future__ import annotations

from typing import Callable

import tilia.errors
import tilia.parsers
from tilia.parsers.csv.beat import beats_from_csv
from tilia.requests import get, Get, post, Post
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.dialogs.by_time_or_by_measure import ByTimeOrByMeasure
from tilia.ui.timelines.collection.collection import TimelineUIs


def on_import_from_csv(timeline_uis: TimelineUIs, tlkind: TlKind) -> None:
    if not _validate_timeline_kind_on_import_from_csv(timeline_uis, tlkind):
        return

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
        return

    timeline = get(Get.TIMELINE, timeline_ui.id)
    if timeline.components and not _confirm_timeline_overwrite_on_import_from_csv():
        return

    if tlkind == TlKind.SCORE_TIMELINE:
        time_or_measure = "measure"
        beat_tlui = _get_beat_timeline_ui_for_import_from_csv(timeline_uis)
        if not beat_tlui:
            return

        beat_tl = get(Get.TIMELINE, beat_tlui.id)
        success, path = get(
            Get.FROM_USER_FILE_PATH,
            "Import components",
            ["musicXML files (*.musicxml; *.mxl)"],
        )

    else:
        if tlkind == TlKind.BEAT_TIMELINE:
            time_or_measure = "time"
        else:
            time_or_measure = _get_by_time_or_by_measure_from_user()

        if time_or_measure == "measure":
            beat_tlui = _get_beat_timeline_ui_for_import_from_csv(timeline_uis)
            if not beat_tlui:
                return

            beat_tl = get(Get.TIMELINE, beat_tlui.id)
        else:
            beat_tl = None

        success, path = get(
            Get.FROM_USER_FILE_PATH, "Import components", ["CSV files (*.csv)"]
        )

    if not success:
        return

    tlkind_to_funcs: dict[TlKind, dict[str, Callable]] = {
        TlKind.MARKER_TIMELINE: {
            "time": tilia.parsers.csv.marker.import_by_time,
            "measure": tilia.parsers.csv.marker.import_by_measure,
        },
        TlKind.HIERARCHY_TIMELINE: {
            "time": tilia.parsers.csv.hierarchy.import_by_time,
            "measure": tilia.parsers.csv.hierarchy.import_by_measure,
        },
        TlKind.BEAT_TIMELINE: {"time": beats_from_csv},
        TlKind.HARMONY_TIMELINE: {
            "time": tilia.parsers.csv.harmony.import_by_time,
            "measure": tilia.parsers.csv.harmony.import_by_measure,
        },
        TlKind.PDF_TIMELINE: {
            "time": tilia.parsers.csv.pdf.import_by_time,
            "measure": tilia.parsers.csv.pdf.import_by_measure,
        },
        TlKind.SCORE_TIMELINE: {
            "measure": tilia.parsers.score.musicxml.notes_from_musicXML,
        },
    }

    prev_state = get(Get.APP_STATE)

    timeline.clear()

    try:
        if time_or_measure == "time":
            success, errors = tlkind_to_funcs[tlkind]["time"](timeline, path)
        elif time_or_measure == "measure":
            success, errors = tlkind_to_funcs[tlkind]["measure"](
                timeline, beat_tl, path
            )
        else:
            raise ValueError("Invalid time_or_measure value '{time_or_measure}'")
    except UnicodeDecodeError:
        tilia.errors.display(tilia.errors.INVALID_CSV_ERROR, path)
        return

    if not success:
        post(Post.APP_STATE_RESTORE, prev_state)
        if errors:
            _display_import_from_csv_errors(success, errors)
        return

    if errors:
        _display_import_from_csv_errors(success, errors)

    if tlkind == TlKind.SCORE_TIMELINE:
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, timeline.id)

    post(Post.APP_RECORD_STATE, "Import from csv file")


def _get_by_time_or_by_measure_from_user():
    dialog = ByTimeOrByMeasure()
    if not dialog.exec():
        return
    return dialog.get_option()


def _validate_timeline_kind_on_import_from_csv(
    timeline_uis: TimelineUIs, tlkind: TlKind
):
    if not timeline_uis.get_timeline_uis_by_attr("TIMELINE_KIND", tlkind):
        tilia.errors.display(
            tilia.errors.CSV_IMPORT_FAILED,
            f"No timelines of type '{tlkind}' found.",
        )
        return False
    return True


def _confirm_timeline_overwrite_on_import_from_csv():
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
