from typing import Literal

from tilia.timelines.base.timeline import Timeline


def get_import_function(tl_type: type(Timeline), by=Literal["time", "measure"]):
    from .csv.beat import beats_from_csv
    from .csv.harmony import import_by_measure as harmony_by_measure
    from .csv.harmony import import_by_time as harmony_by_time
    from .csv.hierarchy import import_by_measure as hierarchy_by_measure
    from .csv.hierarchy import import_by_time as hierarchy_by_time
    from .csv.marker import import_by_measure as marker_by_measure
    from .csv.marker import import_by_time as marker_by_time
    from .csv.pdf import import_by_measure as pdf_by_measure
    from .csv.pdf import import_by_time as pdf_by_time
    from .score.musicxml import notes_from_musicXML as score_from_musicxml

    # TODO: timelines should define their own importers!
    # e.g. BeatTimelineUI.import_from_csv
    from tilia.timelines.beat.timeline import BeatTimeline
    from tilia.timelines.harmony.timeline import HarmonyTimeline
    from tilia.timelines.hierarchy.timeline import HierarchyTimeline
    from tilia.timelines.marker.timeline import MarkerTimeline
    from tilia.timelines.pdf.timeline import PdfTimeline
    from tilia.timelines.score.timeline import ScoreTimeline

    if tl_type == BeatTimeline:
        return beats_from_csv
    elif tl_type == ScoreTimeline:
        return score_from_musicxml
    elif by == "time":
        return {
            MarkerTimeline: marker_by_time,
            HierarchyTimeline: hierarchy_by_time,
            HarmonyTimeline: harmony_by_time,
            PdfTimeline: pdf_by_time,
        }[tl_type]
    elif by == "measure":
        return {
            MarkerTimeline: marker_by_measure,
            HierarchyTimeline: hierarchy_by_measure,
            HarmonyTimeline: harmony_by_measure,
            PdfTimeline: pdf_by_measure,
        }[tl_type]
    else:
        raise ValueError("'by' must be either 'time' or 'measure'")
