import itertools
from pathlib import Path
from zipfile import ZipFile
from typing import Optional, Any
from dataclasses import dataclass
from bisect import bisect

from lxml import etree

from tilia.requests import Get, get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.score.components import Note
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.clef import Clef
from tilia.ui.strings import INSERT_MEASURE_ZERO_TITLE, INSERT_MEASURE_ZERO_PROMPT, INSERT_MEASURE_ZERO_FAILED
from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT


class TiliaMXLReader:
    def __init__(
        self,
        path: str,
        file_kwargs: Optional[dict[str, Any]] = None,
        reader_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.path = path
        self.file_kwargs = file_kwargs or {}
        self.reader_kwargs = reader_kwargs or {}

    def _get_mxl_data(self):
        with ZipFile(self.path) as zipfile, zipfile.open(
                "META-INF/container.xml", **self.file_kwargs
        ) as meta:
            full_path = (
                etree.parse(meta, **self.reader_kwargs)
                .findall(".//rootfile")[0]
                .get("full-path")
            )
            data = zipfile.open(full_path, **self.file_kwargs)
        return data

    def __enter__(self):

        if ".mxl" in self.path:
            self.file = self._get_mxl_data()
        else:
            self.file = open(self.path, **self.file_kwargs)

        return self.file

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.file.close()


def notes_from_musicXML(
    score_tl: ScoreTimeline,
    beat_tl: BeatTimeline,
    path: str,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create notes in a timeline from data extracted from a .musicXML(uncompressed) or .mxl(compressed) file.
    Returns a boolean indicating if the process was successful and
    an array with descriptions of any errors during the process.
    """
    errors = []
    metric_division = MetricDivision()

    sign_to_octave = {"C": 4, "F": 3, "G": 4}
    sign_to_line = {"C": 0, "F": 1, "G": -1}

    def _create_component(component_kind: ComponentKind, kwargs: dict) -> int | None:
        component, fail_reason = score_tl.create_component(component_kind, **kwargs)
        if not component:
            errors.append(fail_reason)
            return None
        return component.id

    def _create_elements(elements: dict) -> None:
        for elem in elements:
            if not elem:
                continue
            if "kwargs" in elem.keys():
                _create_components(elem)
            if "to_annotate" in elem.keys():
                __annotate_metric_position(
                    elem["element"], metric_division, elem["div_pos"]
                )

    def _create_components(elem: dict) -> None:
        start_times, end_times = _get_note_times(
            metric_division.measure_num, elem["div_pos"], elem["duration"]
        )
        # start_times and end_times are always sorted. If start_times[n] is greater than end_time[n], all start_times[n+] will also be greater than end_times[n], which would create a segment-like component with start > end. Therefore, pop off head of end_times until a suitable end_time is found.
        while len(start_times) and len(end_times):
            if (start := start_times[0]) < (end := end_times[0]):
                _create_component(
                    ComponentKind.NOTE,
                    elem["kwargs"] | {"start": start, "end": end},
                )
                start_times.pop(0)
                end_times.pop(0)
                continue
            while len(end_times) and start_times[0] > end_times[0]:
                end_times.pop(0)

    def _metric_to_time(
        measure_number: int, division: int, is_end=False
    ) -> list[float]:
        return beat_tl.get_time_by_measure(
            **metric_division.get_fraction(measure_number, division),
            is_segment_end=is_end,
        )

    def _parse_attributes(part: etree._Element, part_id: str):
        metric_pos_to_attributes = dict()
        for attributes in part.iter("attributes"):
            measure_number = int(attributes.getparent().get("number"))
            prev_divs = 0
            cur_div = 0
            for prev_note in attributes.itersiblings(
                *["note", "backup", "forward"], preceding=True
            ):
                match prev_note.tag:
                    case "backup":
                        cur_div -= int(prev_note.find("duration").text)
                    case _:
                        cur_div += int(prev_note.find("duration").text)

                prev_divs = max(prev_divs, cur_div)
            if prev_divs > 0:
                next_divs = 0
                cur_div = 0
                for next_note in attributes.itersiblings(
                    *["note", "backup", "forward"]
                ):
                    match next_note.tag:
                        case "backup":
                            cur_div -= int(next_note.find("duration").text)
                        case _:
                            cur_div += int(next_note.find("duration").text)
                    next_divs = max(next_divs, cur_div)
                measure_number += prev_divs / (prev_divs + next_divs)
            _parse_attribute(attributes, part_id, measure_number)
            metric_pos_to_attributes[measure_number] = attributes

        metric_pos = sorted(metric_pos_to_attributes.keys())
        if beat_tl.measure_numbers[0] not in metric_pos:
            _parse_attribute(
                metric_pos_to_attributes[metric_pos[0]],
                part_id,
                beat_tl.measure_numbers[0],
                0,
            )
        for m in range(len(beat_tl.measure_numbers) - 1):
            if beat_tl.measure_numbers[m] + 1 == beat_tl.measure_numbers[m + 1]:
                continue
            index = bisect(metric_pos, beat_tl.measure_numbers[m + 1])
            if (
                index < len(metric_pos)
                and beat_tl.measure_numbers[m]
                < metric_pos[index]
                < beat_tl.measure_numbers[m + 1]
            ):
                found_positions = [
                    i
                    for i, v in enumerate(beat_tl.measure_numbers)
                    if v == beat_tl.measure_numbers[m + 1]
                ]
                _parse_attribute(
                    metric_pos_to_attributes[metric_pos[index]],
                    part_id,
                    beat_tl.measure_numbers[m + 1],
                    found_positions.index(m + 1),
                )

    def _parse_attribute(
        attributes: etree._Element,
        part_id: str,
        metric_pos: float,
        list_position: None | int = None,
    ):
        times = beat_tl.get_time_by_measure(metric_pos // 1, metric_pos % 1)
        for attribute in attributes:
            match attribute.tag:
                case "key":
                    constructor_kwargs = {
                        "fifths": int(attribute.find("fifths").text),
                    }
                    staff_numbers = list(part_id_to_staves[part_id].keys())
                    component_kind = ComponentKind.KEY_SIGNATURE
                case "time":
                    ts_numerator = int(attribute.find("beats").text)
                    ts_denominator = int(attribute.find("beat-type").text)
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

            if list_position is not None:
                for staff_number in staff_numbers:
                    _create_component(
                        component_kind,
                        constructor_kwargs
                        | {
                            "time": times[list_position],
                            "staff_index": part_id_to_staves[part_id][staff_number],
                        },
                    )
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

    def _parse_note_tie(element: etree._Element) -> Note.TieType:
        ties = element.findall("tie")
        if not ties:
            return Note.TieType.NONE
        tie_types = {tie.attrib["type"] for tie in ties}
        if "start" in tie_types and "stop" in tie_types:
            return Note.TieType.START_STOP
        elif "start" in tie_types:
            return Note.TieType.START
        else:
            return Note.TieType.STOP

    def _parse_pitch(element: etree._Element) -> dict:
        alter = element.find("pitch/alter")
        return {
            "step": NOTE_NAME_TO_INT[element.find("pitch/step").text],
            "octave": int(element.find("pitch/octave").text),
            "display_accidental": (
                True if element.find("accidental") is not None else False
            ),
            "accidental": int(alter.text) if alter is not None else 0,
        }

    def _parse_unpitched(element: etree._Element) -> dict:
        return {
            "step": NOTE_NAME_TO_INT[element.find("unpitched/display-step").text],
            "accidental": 0,
            "octave": int(element.find("unpitched/display-octave").text),
        }

    def __annotate_metric_position(
        element: etree._Element, metric_division: MetricDivision, div_position: int
    ) -> None:
        n = etree.SubElement(element, "notations")
        t = etree.SubElement(n, "technical")
        f = etree.SubElement(t, "fingering")
        f.text = f"{metric_division.measure_num}␟{div_position}␟{metric_division.max_div_per_measure}"

    def _get_note_times(
        measure_num: int, div_position: int, duration: int
    ) -> tuple[list[float], list[float]]:
        start_times = _metric_to_time(measure_num, div_position)
        end_times = _metric_to_time(measure_num, div_position + duration, True)
        return start_times.copy(), end_times.copy()

    def _parse_staff(element: etree._Element, part_id: str):
        return part_id_to_staves[part_id][element.find("staff").text]

    def _parse_note(element: etree._Element, part_id: str) -> dict[str, Any]:
        if element.find("grace") is not None:
            # We do not support grace notes yet.
            return dict()
        elif element.find("cue") is not None:
            # We do not support cue notes yet.
            return dict()

        duration = int(element.find("duration").text)
        constructor_kwargs = dict()

        if element.find("rest") is not None:
            metric_division.update_measure_position(duration)
            return {
                "div_pos": metric_division.div_position[1],
                "element": element,
                "to_annotate": True,
            }

        if element.find("pitch") is not None:
            constructor_kwargs = _parse_pitch(element)

        if element.find("unpitched") is not None:
            constructor_kwargs = _parse_unpitched(element)

        if not constructor_kwargs.keys():
            return dict()

        constructor_kwargs["tie_type"] = _parse_note_tie(element)

        if element.find("staff") is not None:
            constructor_kwargs["staff_index"] = _parse_staff(element, part_id)
        else:
            constructor_kwargs["staff_index"] = part_id_to_staves[part_id]["1"]

        is_chord = element.find("chord") is not None

        output = {
            "div_pos": metric_division.div_position[0 if is_chord else 1],
            "duration": duration,
            "element": element,
            "kwargs": constructor_kwargs,
            "to_annotate": not is_chord,
        }

        if not is_chord:
            metric_division.update_measure_position(duration)

        return output

    def _parse_element(element: etree._Element, part_id: str) -> dict[str, Any]:
        match element.tag:
            case "note":
                return _parse_note(element, part_id)
            case "backup":
                duration = int(element.find("duration").text)
                metric_division.update_measure_position(-duration)
            case "forward":
                duration = int(element.find("duration").text)
                metric_division.update_measure_position(duration)
            case _:
                pass
        return dict()

    def _parse_part(part: etree._Element, part_id: str):
        _parse_attributes(part, part_id)
        for measure in part.findall("measure"):
            metric_division.update_measure_number(int(measure.attrib["number"]))
            elements_to_create = []
            for element in measure:
                elements_to_create.append(_parse_element(element, part_id))
            _create_elements(elements_to_create)

            times = _metric_to_time(
                metric_division.measure_num, metric_division.div_position[1]
            )
            for time in times:
                _create_component(
                    ComponentKind.BAR_LINE,
                    {
                        "time": time,
                    },
                )

    def _parse_staves(tree: etree._Element):
        staff_counter = itertools.count()
        part_id_to_staves = {
            p.get("id"): {} for p in tree.findall("part-list/score-part")
        }

        for id in part_id_to_staves.keys():
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

    reader_kwargs = reader_kwargs or {}

    with TiliaMXLReader(path, file_kwargs, reader_kwargs) as file:
        tree = etree.parse(file, **reader_kwargs).getroot()

    if tree.tag == "score-timewise":
        tree = _convert_to_partwise(tree)
    elif tree.tag != "score-partwise":
        return False, [f"File `{path}` is not valid musicxml."]

    if tree.find('.//measure[@number="0"]') is not None and (0 not in beat_tl.measure_numbers) and (1 in beat_tl.measure_numbers):
        if not get(Get.FROM_USER_YES_OR_NO, INSERT_MEASURE_ZERO_TITLE, INSERT_MEASURE_ZERO_PROMPT):
            return False, []

        success, reason = _insert_measure_zero(tree, beat_tl)
        if not success:
            return False, [INSERT_MEASURE_ZERO_FAILED.format(reason)]

    part_id_to_staves = _parse_staves(tree)
    for part in tree.findall("part"):
        _parse_part(part, part.get("id"))

    score_tl.mxl_updated(str(etree.tostring(tree, xml_declaration=True), "utf-8"))

    return True, errors


@dataclass
class MetricDivision:
    """
    Tracks the current number of divisions and resets to 1 in the new measure
    """

    measure_num: int = 0
    div_position: tuple = (0, 0)
    max_div_per_measure: int = 1

    def update_measure_position(self, divisions: int):
        self.div_position = (self.div_position[1], self.div_position[1] + divisions)
        self.check_max_divs()

    def update_measure_number(self, measure_number: int):
        self.measure_num = measure_number
        self.div_position = (self.div_position[1], 0)
        self.max_div_per_measure = 1

    def check_max_divs(self):
        self.max_div_per_measure = max(self.max_div_per_measure, self.div_position[1])

    def get_fraction(self, measure_number, div_position):
        return {
            "number": measure_number,
            "fraction": div_position / self.max_div_per_measure,
        }


def _convert_to_partwise(element: etree.Element) -> etree.Element:
    xsl_path = Path("parsers", "score", "timewise_to_partwise.xsl")
    with open(str(xsl_path.resolve()), "r", encoding="utf-8") as xsl:
        xsl_tree = etree.parse(xsl)

    transform = etree.XSLT(xsl_tree)
    return transform(element)


def _insert_measure_zero(tree: etree.Element, beat_tl: BeatTimeline) -> tuple[bool, str]:
    measure_zero = tree.find('.//measure[@number="0"]')
    measure_zero_divisions = sum([int(d.text) for d in measure_zero.findall("note//duration")])
    measure_one = tree.find('.//measure[@number="1"]')
    measure_one_divisions = sum([int(d.text) for d in measure_one.findall("note//duration")])
    return beat_tl.add_measure_zero(measure_zero_divisions / measure_one_divisions)
