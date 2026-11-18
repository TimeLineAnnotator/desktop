import re

# What an input for a time accepts while it is typed: the forms
# parse_media_time reads, and the incomplete ones on the way to them.
MEDIA_TIME_PATTERN = r"^\d*(?::\d*(?::\d*)?)?(?:\.\d*)?$"


def format_media_time(audio_time: float | str) -> str:
    # A time before 0 is shown as the same time after 0, with a minus sign.
    sign = "-" if audio_time < 0 else ""
    audio_time = abs(audio_time)
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    minutes = int(float(audio_time) // 60)
    hours = str(minutes // 60) + ":" if minutes >= 60 else ""
    minutes = str(minutes % 60).zfill(2)
    return f"{sign}{hours}{minutes}:{seconds_and_fraction}"


def parse_media_time(text: str) -> float | None:
    """Parse 'HH:MM:SS.f', 'MM:SS.f', or 'SS.f' to seconds. Returns None on invalid input.

    A time before 0, as format_media_time shows it, is invalid: no input for
    a time takes one, and MEDIA_TIME_PATTERN refuses its minus sign.
    """
    if not re.fullmatch(MEDIA_TIME_PATTERN, text):
        return None
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    except ValueError:
        return None
