from tilia.timelines.harmony.constants import (
    HARMONY_QUALITIES,
    HARMONY_INVERSIONS,
    HARMONY_DISPLAY_MODES,
    HARMONY_ACCIDENTALS,
    MODE_TYPES,
    FONT_TYPES,
)


def validate_quality(value):
    return value in HARMONY_QUALITIES


def validate_inversion(value):
    return value in HARMONY_INVERSIONS


def validate_accidental(value):
    return value in HARMONY_ACCIDENTALS


def validate_display_mode(value):
    return value in HARMONY_DISPLAY_MODES


def validate_mode_type(value):
    return value in MODE_TYPES


def validate_custom_text_font_type(value):
    return value in FONT_TYPES


def validate_level(value):
    return validate_level_count(value)


def validate_step(value):
    return value in range(0, 7)


def validate_applied_to(value):
    return validate_step(value)


def validate_level_count(value):
    return 3 > value >= 1
