def validate_step(value):
    return value in range(0, 7)


def validate_accidental(value):
    return value in [-2, -1, 0, 1, 2]
