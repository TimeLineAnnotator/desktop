"""A beat grid for a MusicXML score: its measures and how many beats each has.

It lets a score be imported without media. The beats are equidistant: each
measure has as many as its time signature counts, or as many as fit its notes
when they fill it otherwise (a pickup, a cadenza, a measure with no time
signature, where a beat is a quarter note).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

from tilia.parsers.score.musicxml import TiliaMXLReader, _convert_to_partwise

# Seconds per beat when the score gives no tempo.
DEFAULT_SECONDS_PER_BEAT = 1.0
QUARTERS_PER_WHOLE = 4


@dataclass(frozen=True)
class ScoreMeasures:
    """The measures of a score, in the order they are written."""

    numbers: list[int]
    beat_counts: list[int]
    # Quarter notes per minute at the start of the score, if it gives one.
    tempo: float | None
    # The beat type (the denominator) of the first time signature, if any.
    first_beat_type: int | None
    title: str

    @property
    def beat_count(self) -> int:
        return sum(self.beat_counts)

    def seconds_per_beat(self) -> float:
        """How long a beat lasts, from the score's first tempo, counting a beat
        as its first time signature does. All beats last as long."""
        if not self.tempo:
            return DEFAULT_SECONDS_PER_BEAT
        beat_in_quarters = QUARTERS_PER_WHOLE / (self.first_beat_type or 4)
        return 60 / self.tempo * beat_in_quarters


def _read_tree(
    path: str, file_kwargs: dict[str, Any] | None, reader_kwargs: dict[str, Any]
) -> etree._Element:
    with TiliaMXLReader(path, file_kwargs, reader_kwargs) as file:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(file, parser=parser, **reader_kwargs).getroot()
    if tree.tag == "score-timewise":
        tree = _convert_to_partwise(tree)
    return tree


def _beats_in_time_signature(time: etree._Element) -> tuple[int, int] | None:
    """The beats a time signature counts and its beat type, or None for one
    without beats (senza misura)."""
    beats = time.findall("beats")
    beat_types = time.findall("beat-type")
    if not beats or not beat_types:
        return None
    try:
        # "3+2" counts five beats, and so does a composite signature, given
        # as several beats and beat-type pairs of the same beat type.
        count = sum(
            int(part) for b in beats for part in (b.text or "").split("+") if part
        )
        beat_type = int(beat_types[0].text)
    except ValueError:
        return None
    if count < 1 or beat_type < 1:
        return None
    return count, beat_type


def _length_in_divisions(measure: etree._Element) -> int:
    """How far the measure's notes reach, in divisions."""
    position = 0
    length = 0
    for element in measure:
        duration = element.find("duration")
        if duration is None or not (duration.text or "").strip():
            # A grace note, or something that takes no time.
            continue
        value = int(duration.text)
        match element.tag:
            case "note":
                if element.find("chord") is None:
                    position += value
            case "forward":
                position += value
            case "backup":
                position -= value
            case _:
                continue
        length = max(length, position)
    return length


def _title(tree: etree._Element, path: str) -> str:
    # A movement's title first: the songs of a cycle share their work title.
    for xpath in ("movement-title", "work/work-title"):
        element = tree.find(xpath)
        if element is not None and (element.text or "").strip():
            return element.text.strip()
    return Path(path).stem


def _first_tempo(tree: etree._Element) -> float | None:
    """The tempo the score starts at: one given in its first measure, in any
    part. A later one isn't taken for the start."""
    sounds = (
        sound
        for part in tree.findall("part")
        if (measure := part.find("measure")) is not None
        for sound in measure.iter("sound")
    )
    for sound in sounds:
        try:
            tempo = float(sound.get("tempo", ""))
        except ValueError:
            continue
        if tempo > 0:
            return tempo
    return None


def measures_from_musicxml(
    path: str,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> tuple[ScoreMeasures | None, list[str]]:
    """The measures of the score at `path`, or None and why there are none.

    Measures come from the first part: in a partwise score, all parts have the
    same measures. As the score import does, implicit measures other than a
    pickup numbered 0 are skipped.
    """
    reader_kwargs = reader_kwargs or {}
    try:
        tree = _read_tree(path, file_kwargs, reader_kwargs)
    except (OSError, etree.XMLSyntaxError) as error:
        return None, [f"Can't read `{path}`: {error}"]
    if tree.tag != "score-partwise":
        return None, [f"File `{path}` is not valid musicxml."]
    if (part := tree.find("part")) is None:
        return None, [f"`{path}` has no parts."]

    numbers = []
    beat_counts = []
    divisions = 1
    time_signature: tuple[int, int] | None = None
    first_beat_type = None
    for measure in part.findall("measure"):
        number = measure.get("number", "")
        if measure.get("implicit") == "yes" and number != "0":
            continue
        try:
            numbers.append(int(number))
        except ValueError:
            return None, [f"Measure number `{number}` is not a whole number."]

        for attributes in measure.iter("attributes"):
            if (element := attributes.find("divisions")) is not None:
                try:
                    divisions = int(float(element.text or "")) or 1
                except ValueError:
                    return None, [
                        f"Measure `{number}` has divisions `{element.text}`,"
                        " which is not a number."
                    ]
            if (element := attributes.find("time")) is not None:
                time_signature = _beats_in_time_signature(element)
                if time_signature and first_beat_type is None:
                    first_beat_type = time_signature[1]

        quarters = _length_in_divisions(measure) / divisions
        if time_signature:
            count, beat_type = time_signature
            beats = quarters * beat_type / QUARTERS_PER_WHOLE
            # A measure its notes don't fill, such as one with a whole-measure
            # rest written short, keeps the time signature's beats.
            if quarters == 0 or abs(beats - count) < 1e-6:
                beat_counts.append(count)
            else:
                beat_counts.append(max(1, round(beats)))
        else:
            beat_counts.append(max(1, round(quarters)))

    if not numbers:
        return None, [f"`{path}` has no measures."]

    return (
        ScoreMeasures(
            numbers=numbers,
            beat_counts=beat_counts,
            tempo=_first_tempo(tree),
            first_beat_type=first_beat_type,
            title=_title(tree, path),
        ),
        [],
    )
