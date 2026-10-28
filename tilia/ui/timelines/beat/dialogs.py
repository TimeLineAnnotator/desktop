from tilia.timelines.beat.pattern import PlannedBar
from tilia.ui.windows.beat_pattern import BarsEdit, BeatPatternDialog
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
    focus_bar: int | None = None,
) -> tuple[bool, BarsEdit | None]:
    """
    Asks for changes to the bars of a timeline that has beats, showing the
    row of `focus_bar` first.
    """
    return BeatPatternDialog.ask(
        initial_text, beat_count, current_bars, numbers, focus_bar
    )


def ask_beat_timeline_fill_method() -> tuple[
    bool, None | tuple[BeatTimeline, BeatTimeline.FillMethod, float]
]:
    return FillBeatTimeline.select()
