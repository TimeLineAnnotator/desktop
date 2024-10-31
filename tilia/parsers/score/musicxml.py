# NOT COMPLETE
# TODO:
#     - Convert metric position to time
#     - Figure out what clef kwargs mean
#     - Put elements into correct stave
#     - Add <tie>

from pathlib import Path
from zipfile import ZipFile
from typing import Optional, Any
import xml.etree.ElementTree as ET
from enum import auto, Enum
from dataclasses import dataclass
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
    timeline: ScoreTimeline,
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

    def _create_component(component_kind: ComponentKind, kwargs: dict) -> int | None:
        # print(component_kind, kwargs)
        component, fail_reason = timeline.create_component(component_kind, **kwargs)
        if not component:
            errors.append(fail_reason)
            return None
        return component.id

    def _parse_attributes(attributes: ET.Element | Any, part_index: int):
        for attribute in attributes:
            match attribute.tag:
                case "divisions":
                    ms.update_divisions(int(attribute.text))

                case "key":
                    kwargs = {
                        "fifths": attribute.find("fifths").text,
                        "time": ms.metric_to_time(
                            ms.measure_num[1], ms.div_position[1]
                        ),
                        "part_index": part_index,
                    }
                    _create_component(ComponentKind.KEY_SIGNATURE, kwargs)
                case "time":
                    ts_numerator = int(attribute.find("beats").text)
                    ts_denominator = int(attribute.find("beat-type").text)
                    ms.update_ts(ts_numerator, ts_denominator)
                    kwargs = {
                        "numerator": ts_numerator,
                        "denominator": ts_denominator,
                        "time": ms.metric_to_time(
                            ms.measure_num[1], ms.div_position[1]
                        ),
                        "part_index": part_index,
                    }
                    _create_component(ComponentKind.TIME_SIGNATURE, kwargs)
                case "clef":
                    kwargs = {
                        "icon": Clef.ICON[attribute.find("sign").text],
                        "line_number": int(attribute.find("line").text) - 3,
                        "time": ms.metric_to_time(
                            ms.measure_num[1], ms.div_position[1]
                        ),
                        "part_index": part_index,
                    }
                    _create_component(ComponentKind.CLEF, kwargs)
                case _:
                    errors.append(f"{attribute.tag} not implemented.")

    def _parse_note(element: ET.Element | Any, part_index: int):
        if element.find("grace") is not None:
            errors.append(f"grace not implemented.")
            return

        duration = int(element.find("duration").text)
        kwargs = dict()

        if element.find("rest") is not None:
            ms.update_measure_position(duration)
            return

        if element.find("pitch") is not None:
            kwargs["step"] = element.find("pitch/step").text
            kwargs["accidental"] = (
                0 if (a := element.find("pitch/alter")) is None else a.text
            )
            kwargs["octave"] = element.find("pitch/octave").text

        if element.find("unpitched") is not None:
            kwargs["step"] = element.find("unpitched/display-step").text
            kwargs["accidental"] = 0
            kwargs["octave"] = element.find("unpitched/display-octave").text

        if not kwargs.keys():
            return

        is_chord = element.find("chord") is not None
        kwargs["start"] = ms.metric_to_time(
            ms.measure_num[1], ms.div_position[0 if is_chord else 1]
        )
        kwargs["end"] = ms.metric_to_time(
            ms.measure_num[1], ms.div_position[0 if is_chord else 1] + duration
        )
        kwargs["part_index"] = part_index
        if not is_chord:
            ms.update_measure_position(duration)
        _create_component(ComponentKind.NOTE, kwargs)

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
            _create_component(
                ComponentKind.BAR_LINE,
                {
                    "time": ms.metric_to_time(ms.measure_num[1], ms.div_position[1]),
                    "part_index": part_index,
                },
            )

    def _parse_timewise(measure: ET.Element | Any):
        ms.update_measure_number(int(measure.attrib["number"]))
        div_position_start = ms.div_position
        for part in measure.findall("part"):
            part_index = parts[part.get("id")]
            for element in part:
                _parse_element(element, part_index)
            _create_component(
                ComponentKind.BAR_LINE,
                {
                    "time": ms.metric_to_time(ms.measure_num[1], ms.div_position[1]),
                    "part_index": part_index,
                },
            )
            ms.div_position = div_position_start

    with TiliaMXLReader(path, file_kwargs, reader_kwargs) as reader:
        for score_part in reader.findall("part-list/score-part"):
            parts[score_part.get("id")] = _create_component(
                ComponentKind.STAFF,
                {
                    "position": len(parts),
                    "line_count": 5,
                    "time": ms.metric_to_time(ms.measure_num[1], ms.div_position[1]),
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

    def metric_to_time(self, measure_num, div_position):
        if div_position == self.max_div_per_measure:
            div_position = 0
            measure_num = self.measure_num[1] + 1
        return (
            measure_num
            + div_position // self.div_per_quarter * 0.1
            + div_position % self.div_per_quarter * 0.01
        )
