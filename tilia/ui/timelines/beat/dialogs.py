from tilia.timelines.beat.pattern import PlannedBar
from tilia.ui.windows.beat_pattern import BarsEdit, BeatPatternDialog
from tilia.ui.windows.beat_unit import BeatUnitDialog, BeatUnitInput
from tilia.ui.windows.fill_beat_timeline import BeatTimeline, FillBeatTimeline


def ask_for_beat_pattern(initial_text: str = "") -> tuple[bool, str]:
    """Asks for the bars of a timeline that has no beats yet."""
    accepted, result = BeatPatternDialog.ask(initial_text)
    return accepted, result.pattern if result else ""


def ask_for_bars(
    initial_text: str,
    beat_count: int,
    current_bars: list[PlannedBar],
    numbers: list[int],
) -> tuple[bool, BarsEdit | None]:
    """Asks for changes to the bars of a timeline that has beats."""
    return BeatPatternDialog.ask(initial_text, beat_count, current_bars, numbers)


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
