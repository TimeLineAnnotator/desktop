import music21.harmony as _m21h
import music21.key as _m21k

HARMONY_DISPLAY_MODES = ["letter", "roman", "custom"]
HARMONY_ACCIDENTALS = [2, 1, 0, -1, -2]
MODE_TYPES = [m for m in _m21k.modeSharpsAlter.keys() if m not in ("ionian", "aeolian")]
FONT_TYPES = ["analytic", "normal"]
HARMONY_QUALITIES = list(_m21h.CHORD_TYPES.keys())


def get_inversion_amount(quality: str) -> int:
    if quality not in HARMONY_QUALITIES:
        raise ValueError(f'Invalid harmony quality "{quality}"')
    intervals_str = str(_m21h.CHORD_TYPES[quality][0])  # type: ignore[index]
    return len(intervals_str.split(",")) - 1
