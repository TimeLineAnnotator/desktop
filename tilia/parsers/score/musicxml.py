# NOT COMPLETE
# TODO:
#     - Put elements into correct stave
#     - Add <tie>

from pathlib import Path
from zipfile import ZipFile
from typing import Optional, Any
import xml.etree.ElementTree as ET
from enum import auto, Enum
from dataclasses import dataclass

from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.clef import Clef


class ComponentKind(Enum):
    PDF_MARKER = auto()
    MODE = auto()
    HARMONY = auto()
    BEAT = auto()
    MARKER = auto()
    NOTE = auto()
    HIERARCHY = auto()
    AUDIOWAVE = auto()
    STAFF = auto()
    CLEF = auto()
    BAR_LINE = auto()
    TIME_SIGNATURE = auto()
    KEY_SIGNATURE = auto()


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
        if ".mxl" in self.path.suffix:
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
    ms = MetricDivision()

    sign_to_step = {"C": 0, "F": 3, "G": 4}
    sign_to_octave = {"C": 4, "F": 3, "G": 4}
    sign_to_line = {"C": 0, "F": 1, "G": -1}

    def _create_component(component_kind: ComponentKind, kwargs: dict) -> int | None:
        # print(component_kind, kwargs)
        component, fail_reason = score_tl.create_component(component_kind, **kwargs)
        if not component:
            errors.append(fail_reason)
            return None
        return component.id

    def _metric_to_time(measure_number: int, division: int) -> list[float]:
        return beat_tl.get_time_by_measure(ms.get_fraction(measure_number, division))

    def _parse_attributes(attributes: ET.Element | Any, part_index: int):
        times = _metric_to_time(ms.get_fraction(ms.measure_num[1], ms.div_position[1]))
        for attribute in attributes:
            constructor_kwargs = dict()
            component_kind = None
            match attribute.tag:
                case "divisions":
                    ms.update_divisions(int(attribute.text))

                case "key":
                    constructor_kwargs = {
                        "fifths": attribute.find("fifths").text,
                        "part_index": part_index,
                    }
                    component_kind = ComponentKind.KEY_SIGNATURE
                case "time":
                    ts_numerator = int(attribute.find("beats").text)
                    ts_denominator = int(attribute.find("beat-type").text)
                    ms.update_ts(ts_numerator, ts_denominator)
                    constructor_kwargs = {
                        "numerator": ts_numerator,
                        "denominator": ts_denominator,
                        "part_index": part_index,
                    }
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
                        errors.append(f"{attribute.tag} - {sign} not implemented")
                        continue

                    constructor_kwargs = {
                        "line_number": sign_to_line[sign] - line,
                        "icon": Clef.ICON.get(sign),
                        "step": sign_to_step[sign],
                        "octave": sign_to_octave[sign] + octave_change,
                        "part_index": part_index,
                    }
                case _:
                    errors.append(f"{attribute.tag} not implemented.")
                    continue

            for time in times:
                _create_component(
                    component_kind,
                    constructor_kwargs | {"time": time},
                )

    def _parse_note(element: ET.Element | Any, part_index: int):
        if element.find("grace") is not None:
            errors.append(f"grace not implemented.")
            return

        duration = int(element.find("duration").text)
        constructor_kwargs = dict()

        if element.find("rest") is not None:
            ms.update_measure_position(duration)
            return

        if element.find("pitch") is not None:
            constructor_kwargs["step"] = element.find("pitch/step").text
            constructor_kwargs["accidental"] = (
                0 if (a := element.find("pitch/alter")) is None else a.text
            )
            constructor_kwargs["octave"] = element.find("pitch/octave").text

        if element.find("unpitched") is not None:
            constructor_kwargs["step"] = element.find("unpitched/display-step").text
            constructor_kwargs["accidental"] = 0
            constructor_kwargs["octave"] = element.find("unpitched/display-octave").text

        if not constructor_kwargs.keys():
            return

        is_chord = element.find("chord") is not None
        start_times = _metric_to_time(
            ms.get_fraction(ms.measure_num[1], ms.div_position[0 if is_chord else 1])
        )
        end_times = _metric_to_time(
            ms.get_fraction(
                ms.measure_num[1], ms.div_position[0 if is_chord else 1] + duration
            )
        )
        constructor_kwargs["part_index"] = part_index
        if not is_chord:
            ms.update_measure_position(duration)

        for start, end in zip(start_times, end_times):
            _create_component(
                ComponentKind.KEY_SIGNATURE,
                constructor_kwargs | {"start": start, "end": end},
            )

    def _parse_element(element: ET.Element | Any, part_index: int):
        match element.tag:
            case "attributes":
                _parse_attributes(element, part_index)
            case "note":
                _parse_note(element, part_index)
            case "backup":
                duration = int(element.find("duration").text)
                ms.update_measure_position(-duration)
            case "forward":
                duration = int(element.find("duration").text)
                ms.update_measure_position(duration)
            case _:
                errors.append(f"{element.tag} not implemented.")

    def _parse_partwise(part: ET.Element | Any, part_index: int):
        for measure in part.findall("measure"):
            ms.update_measure_number(int(measure.attrib["number"]))
            for element in measure:
                _parse_element(element, part_index)

            times = _metric_to_time(
                ms.get_fraction(ms.measure_num[1], ms.div_position[1])
            )
            for time in times:
                _create_component(
                    ComponentKind.BAR_LINE, {"time": time, "part_index": part_index}
                )

    def _parse_timewise(measure: ET.Element | Any):
        ms.update_measure_number(int(measure.attrib["number"]))
        div_position_start = ms.div_position
        for part in measure.findall("part"):
            part_index = parts[part.get("id")]
            for element in part:
                _parse_element(element, part_index)

            times = _metric_to_time(
                ms.get_fraction(ms.measure_num[1], ms.div_position[1])
            )
            for time in times:
                _create_component(
                    ComponentKind.BAR_LINE, {"time": time, "part_index": part_index}
                )

            ms.div_position = div_position_start

    with TiliaMXLReader(path, file_kwargs, reader_kwargs) as reader:
        for score_part in reader.findall("part-list/score-part"):
            parts[score_part.get("id")] = _create_component(
                ComponentKind.STAFF,
                {
                    "position": len(parts),
                    "line_count": 5,
                },
            )

        match reader.tag:
            case "score-partwise":
                for part in reader.findall("part"):
                    _parse_partwise(part, parts[part.get("id")])
            case "score-timewise":
                for measure in reader.findall("measure"):
                    ms.update_measure_number(int(measure.attrib["number"]))
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
        return measure_number, div_position / self.max_div_per_measure
