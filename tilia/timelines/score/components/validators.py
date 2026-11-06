def validate_step(value):
    return value in range(0, 7)


def validate_accidental(value):
    # In semitones. MusicXML writes quarter tones as halves.
    return value in [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]


def validate_tie_type(value):
    from .note import Note

    return value in Note.TieType
