from tilia.ui.windows.beat_pattern import AskBeatPattern
from tilia.ui.windows.fill_beat_timeline import FillBeatTimeline, BeatTimeline
import tilia.errors


def ask_for_beat_pattern():
    def validate_result():
        if not result:
            return False
        return all([x.isnumeric() for x in result])

    result, accept = AskBeatPattern().ask()

    if not accept:
        return False, []

    elif not validate_result():
        tilia.errors.display(tilia.errors.BEAT_PATTERN_ERROR)
        return ask_for_beat_pattern()
    else:
        return True, list(map(int, result))


def ask_beat_timeline_fill_method() -> tuple[
    bool, None | tuple[BeatTimeline, BeatTimeline.FillMethod, float]
]:
    return FillBeatTimeline.select()
