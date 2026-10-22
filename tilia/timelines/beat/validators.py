from tilia.timelines.beat.pattern import parse


def validate_integer_list(value):
    return all([isinstance(x, int) for x in value])


def validate_beat_pattern(value: str | list[int]) -> bool:
    """
    Accepts pattern text, or a list of bar lengths as stored by files and
    callers from before patterns were text.
    """
    if isinstance(value, str):
        return parse(value).is_complete
    if isinstance(value, list):
        return bool(value) and all(isinstance(x, int) and x >= 1 for x in value)
    return False
