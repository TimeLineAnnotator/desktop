"""A time map for a regular grid of beats, standing in for the real one in tests."""

import bisect
import math
from collections.abc import Mapping, Sequence

from tilia_core.corpus.time_map import Measure, Positions

SNAP = 0.1
EPS = 1e-6
DOWNBEAT_TOL = 0.1


class FakeTimeMap:
    """One bar per printed number in playing order, each ``beats_per_bar``
    beats of ``every`` seconds from ``start``. The map ends at
    ``start + len(numbers) * beats_per_bar * every``. A time within 0.1 s of a
    beat or of the map's end counts as on it; a start just before the end lies
    in the last beat; off the map, answers are None.

    ``timeline_id`` names the beat timeline it stands for, and ``guessed`` says
    whether that timeline was taken as the first beat timeline, because none has
    the role ``time_map`` (contracts/time-map.md)."""

    def __init__(
        self,
        start: float,
        every: float,
        beats_per_bar: int,
        numbers: Sequence[int],
        *,
        timeline_id: str = "",
        guessed: bool = False,
    ) -> None:
        self.timeline_id = timeline_id
        self.guessed = guessed
        self.start = float(start)
        self.every = float(every)
        self.beats_per_bar = beats_per_bar
        self.numbers = list(numbers)
        n_beats = len(self.numbers) * beats_per_bar
        self._slots = [self.start + i * self.every for i in range(n_beats + 1)]
        self.end = self._slots[-1]
        self._downbeats = self._slots[:-1:beats_per_bar]
        self._passes: list[int] = []
        seen: dict[int, int] = {}
        for number in self.numbers:
            seen[number] = seen.get(number, 0) + 1
            self._passes.append(seen[number])

    @classmethod
    def from_fixture(cls, tl: dict) -> "FakeTimeMap":
        """From an examples.toml timeline of kind "beats"."""
        numbers = tl.get("numbers") or list(range(1, tl["bars"] + 1))
        return cls(tl["start"], tl["every"], tl["beats_per_bar"], numbers)

    def beat_times(self) -> list[float]:
        """The time of every beat of every bar; the map's end is none."""
        return self._slots[:-1]

    def _snapped(self, t: float | None) -> float | None:
        if t is None:
            return None
        t = float(t)
        if not math.isfinite(t):
            return None
        s = self._slots
        k = bisect.bisect_left(s, t)
        best, best_d = t, math.inf
        if k < len(s) and s[k] - t <= SNAP:
            best, best_d = s[k], s[k] - t
        if k and t - s[k - 1] <= SNAP and t - s[k - 1] < best_d:
            best = s[k - 1]
        return best

    def _locate(self, t: float | None) -> tuple[int, float] | None:
        raw = t
        t = self._snapped(t)
        s = self._slots
        if t is None or t < s[0] or t > s[-1]:
            return None
        if t == s[-1]:
            # A start just before the map's end snaps to it but lies in the
            # last beat; the end itself is off the map.
            return (len(s) - 2, 1.0) if raw < s[-1] else None
        i = bisect.bisect_right(s, t) - 1
        return i, (t - s[i]) / (s[i + 1] - s[i])

    def _bar_index(self, t: float | None) -> int | None:
        loc = self._locate(t)
        return None if loc is None else loc[0] // self.beats_per_bar

    def _pos(self, t: float | None, unit: str) -> float | None:
        loc = self._locate(t)
        if loc is None:
            return None
        i, f = loc
        if unit == "bar":
            return (i + f) / self.beats_per_bar
        return i + f

    def position(self, t: float, unit: str = "bar") -> float | None:
        """0-based continuous position in bars or beats; the map's end counts."""
        p = self._pos(t, unit)
        if p is None:
            e = self._snapped(t)
            if e is not None and abs(e - self.end) <= EPS:
                p = float(len(self.numbers) if unit == "bar" else len(self._slots) - 1)
        return p

    def length(self, start: float, end: float, unit: str = "bar") -> float | None:
        a = self._pos(start, unit)
        b = self.position(end, unit)
        if a is None or b is None:
            return None
        return round(b - a, 6)

    def unit_seconds(self, t: float, unit: str) -> float | None:
        """How long the beat ("beat") or the bar ("bar") holding ``t`` lasts."""
        if self._locate(t) is None:
            return None
        return self.every * (self.beats_per_bar if unit == "bar" else 1)

    def measures(self) -> list[tuple[float, float, int, str]]:
        """(start, end, printed number, label) of every bar in playing order."""
        ends = self._downbeats[1:] + [self.end]
        return [
            (a, b, n, str(n))
            for a, b, n in zip(self._downbeats, ends, self.numbers, strict=True)
        ]

    def bar(self, t: float) -> int | None:
        j = self._bar_index(t)
        return None if j is None else self.numbers[j]

    def end_bar(self, end: float, start: float | None = None) -> int | None:
        """The bar a span ending at ``end`` ends in; an end on a downbeat
        belongs to the bar before. A span so short that its end snaps to its
        ``start`` (or before it) ends in its start's bar (#104, 2026-10-10)."""
        e = self._snapped(end)
        if start is not None:
            s = self._snapped(start)
            if e is not None and s is not None and e <= s:
                return self.bar(start)
        if e is None or e <= self.start or e > self.end:
            return None
        return self.numbers[bisect.bisect_left(self._downbeats, e) - 1]

    def beat(self, t: float) -> float | None:
        """1-based, fractional beat within the bar."""
        loc = self._locate(t)
        if loc is None:
            return None
        i, f = loc
        return i % self.beats_per_bar + 1 + f

    def pass_of(self, t: float) -> int | None:
        j = self._bar_index(t)
        return None if j is None else self._passes[j]

    def bar_count(self, t: float) -> int | None:
        j = self._bar_index(t)
        return None if j is None else j + 1

    def bar_label(self, t: float) -> str | None:
        b = self.bar(t)
        return None if b is None else str(b)

    def measure_beats(self, t: float) -> int | None:
        return None if self._bar_index(t) is None else self.beats_per_bar

    def is_downbeat(self, t: float | None) -> bool:
        if t is None or not math.isfinite(float(t)):
            return False
        d = self._downbeats
        k = bisect.bisect_left(d, float(t))
        near = min(abs(d[x] - t) for x in (k - 1, k) if 0 <= x < len(d))
        return near <= DOWNBEAT_TOL

    # -- what the index stores (contracts/time-map.md) ------------------------ #
    def measure_rows(self) -> list[Measure]:
        """One record per bar, in playing order, for the ``measures`` table."""
        return [
            Measure(
                count=count,
                number=number,
                label=label,
                start=start,
                end=end,
                beats=self.beats_per_bar,
                pass_=self.pass_of(start),
                beat_unit=4,
                time_signature=f"{self.beats_per_bar}/4",
                assumed=False,
            )
            for count, (start, end, number, label) in enumerate(self.measures(), 1)
        ]

    def positions(self, start: float, end: float) -> Positions | None:
        """Where a unit from ``start`` to ``end`` falls; None when its start is
        off the map. A point ends in the bar it starts in."""
        bar = self.bar(start)
        if bar is None:
            return None
        return Positions(
            bar=bar,
            end_bar=bar if start == end else self.end_bar(end, start),
            beat=self.beat(start),
            pass_=self.pass_of(start),
            bar_count=self.bar_count(start),
            bar_label=self.bar_label(start),
            bar_beat_count=self.measure_beats(start),
            downbeat=self.is_downbeat(start),
        )


def time_map_of(document, roles: Mapping[str, str | None]) -> FakeTimeMap | None:
    """The fake time map of a document (WP9's signature, contracts/time-map.md):
    from the beat timeline whose role is ``time_map``, else the first beat
    timeline (``guessed``); None without a beat timeline. It reads the timeline
    as ``corpus_docs`` writes it: a beat component per beat of a regular grid,
    ``beats_in_measure`` (or ``beat_pattern``) and ``measure_numbers``."""
    beat_timelines = [tl for tl in document.timelines if tl.kind == "beat"]
    chosen = [tl for tl in beat_timelines if roles.get(tl.id) == "time_map"]
    guessed = not chosen
    timelines = chosen or beat_timelines
    if not timelines:
        return None
    tl = timelines[0]
    times = sorted(float(c.attrs["time"]) for c in tl.components if c.kind == "beat")
    if not times:
        return None
    per_bar = (tl.attrs.get("beats_in_measure") or tl.attrs["beat_pattern"])[0]
    every = times[1] - times[0] if len(times) > 1 else 1.0
    return FakeTimeMap(
        times[0],
        every,
        per_bar,
        tl.attrs["measure_numbers"],
        timeline_id=tl.id,
        guessed=guessed,
    )
