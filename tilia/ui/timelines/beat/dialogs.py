from tilia.requests import post, Post
from tilia.ui.windows.beat_pattern import AskBeatPattern


def ask_for_beat_pattern():
    def validate_result():
        if not result:
            return False
        if not all([x.isnumeric() for x in result]):
            return False
        else:
            return True

    result, accept = AskBeatPattern().ask()

    if not accept:
        return False, []

    elif not validate_result():
        post(
            Post.DISPLAY_ERROR,
            "Insert beat pattern",
            "Beat pattern must be one or more numbers.",
        )
        return ask_for_beat_pattern()
    else:
        return True, list(map(int, result))
