from dataclasses import dataclass


@dataclass
class MetricPosition:
    measure: int
    beat: int
    measure_beat_count: int
    # Note that beats and measures are 1-based. E.g. MetricPosition(2, 1, 4) is
    # the first beat in the second measure, which has 4 beats in it.
    # Knowing the number of beats in the measure is necessary for arithmetic with metric positions.

    def __eq__(self, other):
        return self.measure == other.measure and self.beat == other.beat

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


@dataclass
class MetricInterval:
    measures: int
    beats: int
    # MetricInterval is 0-based, unlike MetricPosition.
    # Arithmetic with MetricIntervals is not implemented at the moment
    # but it is possible.

    def __eq__(self, other):
        return self.measures == other.measures and self.beats == other.beats
