from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricPosition:
    measure: int
    beat: float
    measure_beat_count: int
    # The measure's label: its number as text, unless the file names it otherwise
    # ("16a"). None where nothing gives one, and the number shows.
    label: str | None = None
    # Note that beats and measures are 1-based. E.g. MetricPosition(2, 1, 4) is
    # the first beat in the second measure, which has 4 beats in it.
    # Knowing the number of beats in the measure is necessary for arithmetic with metric positions.
    # A time's position (`Get.METRIC_POSITION`) is the core's, with its beat as the
    # core gives it: 2.37 lies 37% of the way from the measure's second beat to its
    # third.

    def __eq__(self, other):
        return self.measure == other.measure and self.beat == other.beat

    def __str__(self) -> str:
        """As TiLiA shows it: the measure's label, then the beat to two decimals, a
        whole beat without them, as `12.2.37` and `12.2` (FR-044)."""
        beat = f"{self.beat:.2f}"
        if beat.endswith(".00"):
            beat = beat[: -len(".00")]
        label = self.label if self.label is not None else str(self.measure)
        return f"{label}.{beat}"

    def __sub__(self, other):
        """
        Subtracting MetricPositions result in MetricInterval, and is straightforward when
        dealing with measures with the same beat count:
        MetricPosition(1, 1, 4) - MetricPosition(1, 1, 4) == MetricInterval(0, 0, 4)  (i.e. 4 beats)
        MetricPosition(2, 1, 4) - MetricPosition(1, 1, 4) == MetricInterval(1, 0, 4)  (i.e. 1 measure)
        MetricPosition(3, 2, 4) - MetricPosition(1, 1, 4) == MetricInterval(2, 1, 4)  (i.e. 2 measures and 1 beat)
        MetricPosition(2, 1, 4) - MetricPosition(1, 3, 4) == MetricInterval(0, 2, 4)  (i.e. 2 beats)

        When the beat counts differ, the largest one is used to decide how many "fractional"
        beats will sum to a full measure. For instance:
        MetricPosition(2, 1, 4) - MetricPosition(1, 3, 5) == MetricInterval(0, 5) (5 beats)
                                                          != MetricInterval(1, 1) (1 measure and a 1 beat)
        """
        measures = self.measure - other.measure
        beats = self.beat - other.beat
        if beats < 0:
            measures -= 1
            beats = max(self.measure_beat_count, other.measure_beat_count) + beats

        return MetricInterval(measures=measures, beats=beats)


def format_metric_span(
    start: MetricPosition | None, end: MetricPosition | None
) -> str | None:
    """A span's start and end as TiLiA shows them, `12.2.37 / 14.1`, with `-` for
    either when it lies off the time map. None when both do."""
    if start is None and end is None:
        return None
    return " / ".join("-" if place is None else str(place) for place in (start, end))


@dataclass
class MetricInterval:
    measures: int
    beats: float
    # MetricInterval is 0-based, unlike MetricPosition.
    # Arithmetic with MetricIntervals is not implemented at the moment
    # but it is possible.

    def __eq__(self, other):
        return self.measures == other.measures and self.beats == other.beats
