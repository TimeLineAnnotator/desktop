# NOT COMPLETE
# TODO:
#     - Add <tie>
import itertools
from pathlib import Path
from zipfile import ZipFile
from typing import Optional, Any
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.score.components import Note
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.clef import Clef
from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT


class TiliaMXLReader:
    def __init__(
        self,
        path: Path,
        file_kwargs: Optional[dict[str, Any]] = None,
        reader_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.path = path
        self.file_kwargs = file_kwargs or {}
        self.reader_kwargs = reader_kwargs or {}

    def __enter__(self):
        if ".mxl" in self.path:
            with ZipFile(self.path) as zipfile, zipfile.open(
                "META-INF/container.xml", **self.file_kwargs
            ) as meta:
                full_path = (
                    ET.parse(meta, **self.reader_kwargs)
                    .findall(".//rootfile")[0]
                    .get("full-path")
                )
                self.file = zipfile.open(full_path, **self.file_kwargs)
        else:
            self.file = open(self.path, **self.file_kwargs)

        return ET.parse(self.file, **self.reader_kwargs).getroot()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.file.close()


def notes_from_musicXML(
    score_tl: ScoreTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str | Any]] = None,
    reader_kwargs: Optional[dict[str | Any]] = None,
) -> list[str]:
    """
    Create notes in a timeline from data extracted from a .musicXML(uncompressed) or .mxl(compressed) file.
    Returns an array of descriptions of any CreateComponentErrors raised during note creation.
    """
    errors = []
    parts = {}
    metric_division = MetricDivision()

    sign_to_octave = {"C": 4, "F": 3, "G": 4}
    sign_to_line = {"C": 0, "F": 1, "G": -1}

    def _create_component(component_kind: ComponentKind, kwargs: dict) -> int | None:
        component, fail_reason = score_tl.create_component(component_kind, **kwargs)
        # print(component_kind, kwargs, component is not None)
        if not component:
            errors.append(fail_reason)
            return None
        return component.id

    def _metric_to_time(measure_number: int, division: int) -> list[float]:
        a = beat_tl.get_time_by_measure(
            **metric_division.get_fraction(measure_number, division)
        )
        return a

    def _parse_attributes(attributes: ET.Element | Any, part_id: str):
        times = _metric_to_time(
            metric_division.measure_num[1], metric_division.div_position[1]
        )
        for attribute in attributes:
            constructor_kwargs = dict()
            component_kind = None
            match attribute.tag:
                case "divisions":
                    metric_division.update_divisions(int(attribute.text))
                    continue

                case "key":
                    constructor_kwargs = {
                        "fifths": int(attribute.find("fifths").text),
                    }
                    staff_numbers = list(part_id_to_staves[part_id].keys())
                    component_kind = ComponentKind.KEY_SIGNATURE
                case "time":
                    ts_numerator = int(attribute.find("beats").text)
                    ts_denominator = int(attribute.find("beat-type").text)
                    metric_division.update_ts(ts_numerator, ts_denominator)
                    constructor_kwargs = {
                        "numerator": ts_numerator,
                        "denominator": ts_denominator,
                        "staff_index": part_id_to_staves[part_id],
                    }
                    staff_numbers = list(part_id_to_staves[part_id].keys())
                    component_kind = ComponentKind.TIME_SIGNATURE
                case "clef":
                    sign = attribute.find("sign").text
                    line = int(l.text) - 3 if (l := attribute.find("line")) else 0
                    octave_change = (
                        int(o.text)
                        if (o := attribute.find("clef-octave-change"))
                        else 0
                    )

                    if sign not in {"C", "F", "G"}:
                        errors.append(f"<{attribute.tag}> - {sign} not implemented")
                        continue

                    constructor_kwargs = {
                        "line_number": sign_to_line[sign] - line,
                        "icon": Clef.ICON.get(sign),
                        "step": NOTE_NAME_TO_INT[sign],
                        "octave": sign_to_octave[sign] + octave_change,
                    }
                    staff_numbers = (
                        [attribute.get("number")]
                        if attribute.get("number") is not None
                        else ["1"]
                    )
                    component_kind = ComponentKind.CLEF
                case _:
                    continue

            for time in times:
                for staff_number in staff_numbers:
                    _create_component(
                        component_kind,
                        constructor_kwargs
                        | {
                            "time": time,
                            "staff_index": part_id_to_staves[part_id][staff_number],
                        },
                    )

    def _parse_note_tie(element: ET.Element) -> Note.TieType:
        tie = element.find("tie")
        if tie is None:
            return Note.TieType.NONE
        elif tie.text == "start":
            return Note.TieType.START
        else:
            return Note.TieType.STOP

    def _parse_note(element: ET.Element | Any, part_id: str):
        if element.find("grace") is not None:
            errors.append(f"<grace> not implemented.")
            return

        duration = int(element.find("duration").text)
        constructor_kwargs = dict()

        if element.find("rest") is not None:
            metric_division.update_measure_position(duration)
            return

        if element.find("pitch") is not None:
            constructor_kwargs["step"] = NOTE_NAME_TO_INT[
                element.find("pitch/step").text
            ]
            constructor_kwargs["octave"] = int(element.find("pitch/octave").text)
            constructor_kwargs["display_accidental"] = (
                True if element.find("accidental") is not None else False
            )
            alter = element.find("pitch/alter")
            constructor_kwargs["accidental"] = (
                int(alter.text) if alter is not None else 0
            )

        if element.find("unpitched") is not None:
            constructor_kwargs["step"] = NOTE_NAME_TO_INT[
                element.find("unpitched/display-step").text
            ]
            constructor_kwargs["accidental"] = 0
            constructor_kwargs["octave"] = int(
                element.find("unpitched/display-octave").text
            )

        constructor_kwargs["tie_type"] = _parse_note_tie(element)

        if not constructor_kwargs.keys():
            return

        is_chord = element.find("chord") is not None
        start_times = _metric_to_time(
            metric_division.measure_num[1],
            metric_division.div_position[0 if is_chord else 1],
        )
        end_times = _metric_to_time(
            metric_division.measure_num[1],
            metric_division.div_position[0 if is_chord else 1] + duration,
        )
        if element.find("staff") is not None:
            constructor_kwargs["staff_index"] = part_id_to_staves[part_id][
                element.find("staff").text
            ]
        else:
            constructor_kwargs["staff_index"] = part_id_to_staves[part_id]["1"]

        if not is_chord:
            metric_division.update_measure_position(duration)

        for start, end in zip(start_times, end_times):
            _create_component(
                ComponentKind.NOTE,
                constructor_kwargs | {"start": start, "end": end},
            )

    def _parse_element(element: ET.Element | Any, part_id: str):
        match element.tag:
            case "attributes":
                _parse_attributes(element, part_id)
            case "note":
                _parse_note(element, part_id)
            case "backup":
                duration = int(element.find("duration").text)
                metric_division.update_measure_position(-duration)
            case "forward":
                duration = int(element.find("duration").text)
                metric_division.update_measure_position(duration)
            case _:
                pass

    def _parse_partwise(part: ET.Element | Any, part_id: str):
        for measure in part.findall("measure"):
            metric_division.update_measure_number(int(measure.attrib["number"]))
            for element in measure:
                _parse_element(element, part_id)

            times = _metric_to_time(
                metric_division.measure_num[1], metric_division.div_position[1]
            )
            for time in times:
                _create_component(
                    ComponentKind.BAR_LINE,
                    {
                        "time": time,
                    },
                )

    def _parse_timewise(measure: ET.Element | Any):
        metric_division.update_measure_number(int(measure.attrib["number"]))
        div_position_start = metric_division.div_position
        for part in measure.findall("part"):
            part_index = part_id_to_staves[part.get("id")]
            for element in part:
                _parse_element(element, part_index)

            times = _metric_to_time(
                metric_division.measure_num[1], metric_division.div_position[1]
            )
            for time in times:
                _create_component(
                    ComponentKind.BAR_LINE,
                    {"time": time, "staff_index": part_index},
                )

            metric_division.div_position = div_position_start

    def _parse_staves(tree: ET):
        staff_counter = itertools.count()
        part_ids = [p.get("id") for p in tree.findall("part-list/score-part")]
        part_id_to_staves = {
            p.get("id"): {} for p in tree.findall("part-list/score-part")
        }

        for id in part_ids:
            staff_numbers = sorted(
                list(
                    set(
                        [
                            s.text
                            for s in tree.findall(f".//part[@id='{id}']//note/staff")
                        ]
                    )
                )
            )
            if not staff_numbers:
                staff_numbers = ["1"]
            for number in staff_numbers:
                staff_index = next(staff_counter)
                _create_component(
                    ComponentKind.STAFF,
                    {
                        "index": staff_index,
                        "line_count": 5,
                    },
                )
                part_id_to_staves[id][number] = staff_index

        return part_id_to_staves

    with TiliaMXLReader(path, file_kwargs, reader_kwargs) as reader:

        part_id_to_staves = _parse_staves(reader)

        match reader.tag:
            case "score-partwise":
                for part in reader.findall("part"):
                    _parse_partwise(part, part.get("id"))

            case "score-timewise":
                for measure in reader.findall("measure"):
                    metric_division.update_measure_number(int(measure.attrib["number"]))
                    pass
                    _parse_timewise(measure)
            case _:
                errors.append("File not read")

        return errors


@dataclass
class MetricDivision:
    measure_num: tuple = (0, 0)
    div_position: tuple = (0, 0)
    div_per_quarter: int = 1
    ts_numerator: int = 1
    ts_denominator: int = 1
    max_div_per_measure: int = 1

    def update_measure_position(self, divisions: int):
        self.div_position = (self.div_position[1], self.div_position[1] + divisions)

    def update_measure_number(self, measure_number: int):
        self.measure_num = (self.measure_num[1], measure_number)
        self.div_position = (self.div_position[1], 0)

    def update_divisions(self, division_per_quarter):
        self.div_per_quarter = division_per_quarter
        self.update_max_divs()

    def update_ts(self, numerator, denominator):
        self.ts_numerator = numerator
        self.ts_denominator = denominator
        self.update_max_divs()

    def update_max_divs(self):
        self.max_div_per_measure = (
            4 / self.ts_denominator * self.ts_numerator * self.div_per_quarter
        )

    def get_fraction(self, measure_number, div_position):
        return {
            "number": measure_number,
            "fraction": div_position / self.max_div_per_measure,
        }
