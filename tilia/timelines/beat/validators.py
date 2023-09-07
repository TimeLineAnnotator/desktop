def validate_beat_pattern(value):
    return all([isinstance(x, int) for x in value])
