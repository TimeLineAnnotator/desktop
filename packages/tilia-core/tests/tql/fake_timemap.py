"""A time map for a regular grid of beats, standing in for the real one in tests."""

import bisect
import math
from collections.abc import Sequence

SNAP = 0.1
EPS = 1e-6
DOWNBEAT_TOL = 0.1


class FakeTimeMap:
    """One bar per printed number in playing order, each ``beats_per_bar``
    beats of ``every`` seconds from ``start``. The map ends at
    ``start + len(numbers) * beats_per_bar * every``. A time within 0.1 s of a
    beat or of the map's end counts as on it; off the map, answers are None."""

    def __init__(
        self, start: float, every: float, beats_per_bar: int, numbers: Sequence[int]
    ) -> None:
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
        t = self._snapped(t)
        s = self._slots
        if t is None or t < s[0] or t >= s[-1]:
            return None
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

    def end_bar(self, end: float) -> int | None:
        """The bar a span ending at ``end`` ends in; an end on a downbeat
        belongs to the bar before."""
        e = self._snapped(end)
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
