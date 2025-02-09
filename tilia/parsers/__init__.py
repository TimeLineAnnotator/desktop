from typing import Literal

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from .csv.marker import import_by_measure as marker_by_measure
from .csv.marker import import_by_time as marker_by_time
from .csv.hierarchy import import_by_measure as hierarchy_by_measure
from .csv.hierarchy import import_by_time as hierarchy_by_time
from .csv.beat import beats_from_csv
from .csv.harmony import import_by_measure as harmony_by_measure
from .csv.harmony import import_by_time as harmony_by_time
from .csv.pdf import import_by_measure as pdf_by_measure
from .csv.pdf import import_by_time as pdf_by_time
from .score.musicxml import notes_from_musicXML as score_from_musicxml


def get_import_function(tl_kind: TlKind, by=Literal["time", "measure"]):
    if tl_kind == TlKind.BEAT_TIMELINE:
        return beats_from_csv
    elif tl_kind == TlKind.SCORE_TIMELINE:
        return score_from_musicxml
    elif by == "time":
        return {
            TlKind.MARKER_TIMELINE: marker_by_time,
            TlKind.HIERARCHY_TIMELINE: hierarchy_by_time,
            TlKind.HARMONY_TIMELINE: harmony_by_time,
            TlKind.PDF_TIMELINE: pdf_by_time,
        }[tl_kind]
    elif by == "measure":
        return {
            TlKind.MARKER_TIMELINE: marker_by_measure,
            TlKind.HIERARCHY_TIMELINE: hierarchy_by_measure,
            TlKind.HARMONY_TIMELINE: harmony_by_measure,
            TlKind.PDF_TIMELINE: pdf_by_measure,
        }[tl_kind]
    else:
        raise ValueError("'by' must be either 'time' or 'measure'")
