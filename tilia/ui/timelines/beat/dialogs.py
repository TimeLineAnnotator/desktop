from collections.abc import Callable

from tilia.ui.windows.beat_pattern import BeatPatternDialog
from tilia.ui.windows.beat_unit import BeatUnitDialog, BeatUnitInput
from tilia.ui.windows.fill_beat_timeline import BeatTimeline, FillBeatTimeline


def ask_for_beat_pattern(
    initial_text: str = "",
    beat_count: int | None = None,
    get_overwritten_bars: Callable[[list[int]], list[int]] | None = None,
) -> tuple[bool, str]:
    return BeatPatternDialog.ask(initial_text, beat_count, get_overwritten_bars)


def ask_for_beat_unit(
    denominator: int,
    units: str,
    beat_count: int | None = None,
    show_scope: bool = True,
) -> tuple[bool, BeatUnitInput | None]:
    return BeatUnitDialog.ask(denominator, units, beat_count, show_scope)


def ask_beat_timeline_fill_method() -> tuple[
    bool, None | tuple[BeatTimeline, BeatTimeline.FillMethod, float]
]:
    return FillBeatTimeline.select()
