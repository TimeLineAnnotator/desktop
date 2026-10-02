from fractions import Fraction


def format_numerator(numerator: Fraction) -> str:
    """A whole number, or a whole number plus a fraction: "4", "4 1/3", "1/2"."""
    whole = numerator.numerator // numerator.denominator
    remainder = numerator - whole
    if not remainder:
        return str(whole)
    fraction = f"{remainder.numerator}/{remainder.denominator}"
    return f"{whole} {fraction}" if whole else fraction


def format_media_time(audio_time: float | str) -> str:
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    minutes = int(float(audio_time) // 60)
    hours = str(minutes // 60) + ":" if minutes >= 60 else ""
    minutes = str(minutes % 60).zfill(2)
    return f"{hours}{minutes}:{seconds_and_fraction}"


def parse_media_time(text: str) -> float | None:
    """Parse 'HH:MM:SS.f', 'MM:SS.f', or 'SS.f' to seconds. Returns None on invalid input."""
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
