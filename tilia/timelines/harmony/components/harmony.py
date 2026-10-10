from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

import music21

from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_string, validate_time
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.constants import (
    ADDED_TONE_QUALITIES,
    CHORD_COMMON_NAME_TO_TYPE,
    NOTE_NAME_TO_INT,
    ROMAN_TO_INT,
    get_inversion_amount,
)
from tilia.timelines.harmony.validators import (
    validate_accidental,
    validate_applied_to,
    validate_custom_text_font_type,
    validate_display_mode,
    validate_inversion,
    validate_level,
    validate_quality,
    validate_step,
)

if TYPE_CHECKING:
    from tilia.timelines.harmony.timeline import HarmonyTimeline


class Harmony(PointLikeTimelineComponent):

    SERIALIZABLE = [
        "time",
        "comments",
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "level",
        "display_mode",
        "custom_text",
        "custom_text_font_type",
    ]
    ORDERING_ATTRS = ("level", "time")

    KIND = ComponentKind.HARMONY

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "time": validate_time,
        "step": validate_step,
        "accidental": validate_accidental,
        "quality": validate_quality,
        "applied_to": validate_applied_to,
        "level": validate_level,
        "display_mode": validate_display_mode,
        "custom_text": validate_string,
        "custom_text_font_type": validate_custom_text_font_type,
        "comments": validate_string,
    }

    def __init__(
        self,
        timeline: HarmonyTimeline,
        id: int,
        time: float,
        step: int = 0,
        accidental: int = 0,
        quality: str = "major",
        inversion: int = 0,
        applied_to: int = 0,
        level: int = 1,
        display_mode: Literal["letter", "roman", "custom"] = "letter",
        custom_text: str = "",
        custom_text_font_type: Literal["analytic", "normal"] = "analytic",
        comments="",
        **_,
    ):
        self.time = time
        self.step = step
        self.accidental = accidental
        self.quality = quality
        self.inversion = inversion
        self.applied_to = applied_to
        self.level = level
        self.display_mode = display_mode
        self.custom_text = custom_text
        self.custom_text_font_type = custom_text_font_type
        self.comments = comments

        super().__init__(timeline, id)

    def __str__(self):
        return f"Harmony({self.step, self.accidental, self.quality, self.inversion}) at {self.time}"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @classmethod
    def from_string(
        cls, time: float, string: str, key: music21.key.Key | str = "C major"
    ):
        music21_object, object_type, added_tone = _get_music21_object_from_text(
            string, key.__str__()
        )

        if not string:
            return None

        if not object_type:
            raise ValueError(
                "Can't create harmony: can't create music21 object from '{string}'"
            )

        params = _get_params_from_music21_object(
            music21_object, object_type, added_tone
        )
        return Harmony(*params)

    def validate_set_data(self, attr: str, value: Any) -> bool:
        if attr == "inversion":
            return validate_inversion(value, self.quality)
        return super().validate_set_data(attr, value)

    def set_data(self, attr: str, value: Any):
        result = super().set_data(attr, value)
        if attr == "quality" and result[1]:
            max_inv = get_inversion_amount(value)
            if self.inversion > max_inv:
                self.inversion = max_inv
                self.update_hash()
        return result


def get_params_from_text(text: str, key: str):
    music21_object, object_type, added_tone = _get_music21_object_from_text(text, key)
    if not object_type:
        return False, None

    params = _get_params_from_music21_object(music21_object, object_type, added_tone)
    if added_tone and params["inversion"] > get_inversion_amount(params["quality"]):
        # The added tone is in the bass, as in "C7b9/Db". No inversion puts it
        # there.
        return False, None
    return True, params


SPECIAL_ABBREVIATIONS_TO_QUALITY = {
    "dimb9": "diminished-minor-ninth",
    "9#5": "augmented-dominant-ninth",
    "m7b5": "half-diminished-seventh",
    "m#7": "minor-major-seventh",
}  # these don't get correctly parsed by music21


def _replace_special_abbreviations(text):
    sub_args = [("dimb9", "ob9"), ("9#5", "+9"), ("m7b5", "ø7"), ("m#7", "minmaj7")]
    for pattern, replacement in sub_args:
        text = re.sub(pattern, replacement, text)

    return text


_BASE_AND_TONE_TO_QUALITY = {
    base_and_tone: quality for quality, base_and_tone in ADDED_TONE_QUALITIES.items()
}

_ALTERATION_TO_ACCIDENTAL = {-1: "b", 0: "", 1: "#"}


def _get_music21_object_from_text(
    text: str, key: str
) -> (
    tuple[music21.harmony.ChordSymbol | music21.roman.RomanNumeral, str, str]
    | tuple[None, None, str]
):
    """
    Return the music21 object for the text, its kind, and the tone the text
    adds to the object's quality, or "" if they are no added-tone quality.
    """
    text, prefixed_accidental = _extract_prefixed_accidental(text)
    text = _format_postfix_accidental(text)
    text = _replace_special_abbreviations(text)
    if text.startswith(tuple(NOTE_NAME_TO_INT)) and not prefixed_accidental:
        spelled = _spell_added_tone(text)
        try:
            symbol = music21.harmony.ChordSymbol(spelled)
            added_tone = _get_added_tone(symbol)
            # music21 reads no parentheses, so a text that needed respelling
            # is read only as an added-tone quality: "C7(b9)" is read, while
            # "Cm7(b9)" is refused, as before.
            if added_tone or spelled == text:
                return symbol, "letter", added_tone
        # This is a bare expect because I don't know
        # exactly what exceptions music21 can throw.
        except:  # noqa
            pass
    elif text.startswith(("I", "i", "V", "v")):
        # music21 reads a tone after a Roman numeral's figures as another
        # figure, so the numeral is read without it.
        text, added_tone = _split_roman_added_tone(text)
        try:
            roman_numeral = music21.roman.RomanNumeral(prefixed_accidental + text, key)
            quality = CHORD_COMMON_NAME_TO_TYPE[roman_numeral.commonName]
            if added_tone and (quality, added_tone) not in _BASE_AND_TONE_TO_QUALITY:
                raise KeyError(added_tone)
            return roman_numeral, "roman", added_tone
        except (ValueError, KeyError):
            pass

    return None, None, ""


def _spell_added_tone(text: str) -> str:
    """
    Spell an added tone as music21 reads it: "C7(b9)" as "C7b9", and "C(9)",
    "C(add9)" and "C6/9" with "add", as "Cadd9" and "C6add9".
    """
    text = text.replace("6/9", "6add9")
    return re.sub(
        r"\((?:add)?([b#]?)(\d+)\)", lambda match: (match[1] or "add") + match[2], text
    )


def _get_added_tone(symbol: music21.harmony.ChordSymbol) -> str:
    """
    Return the tone the chord symbol adds to its chord type, as "b9", if
    together they are an added-tone quality. Otherwise return "", and the
    chord symbol is read as its chord type, as before.
    """
    modifications = symbol.chordStepModifications
    if len(modifications) != 1 or modifications[0].modType != "add":
        return ""
    modification = modifications[0]
    alteration = modification.interval.semitones if modification.interval else 0
    accidental = _ALTERATION_TO_ACCIDENTAL.get(alteration)
    if accidental is None:
        return ""
    tone = accidental + str(modification.degree)
    return tone if (symbol.chordKind, tone) in _BASE_AND_TONE_TO_QUALITY else ""


# A tone added after a Roman numeral's figures: "V7b9", "V65(b9)". A tone
# without an accidental needs "add" or parentheses, since "V9" is a ninth
# chord and "I6" an inversion.
_ROMAN_ADDED_TONE_PATTERNS = (
    re.compile(r"\((?:add)?([b#]?)(\d+)\)$"),
    re.compile(r"add([b#]?)(\d+)$"),
    re.compile(r"([b#])(9|11|13)$"),
)


def _split_roman_added_tone(text: str) -> tuple[str, str]:
    """Split "V7b9/IV" into "V7/IV" and "b9". The tone is "" if there is none."""
    numeral, slash, applied_to = text.partition("/")
    for pattern in _ROMAN_ADDED_TONE_PATTERNS:
        if match := pattern.search(numeral):
            accidental, degree = match.groups()
            numeral = numeral[: match.start()]
            if accidental and not numeral[-1:].isdigit():
                # An altered tone is added to a seventh chord: "Vb9" is "V7b9".
                numeral += "7"
            return numeral + slash + applied_to, accidental + degree
    return text, ""


def _get_params_from_music21_object(
    obj: music21.harmony.ChordSymbol | music21.roman.RomanNumeral,
    kind: str,
    added_tone: str = "",
) -> dict:
    step = NOTE_NAME_TO_INT[obj.root().step]
    accidental = int(obj.root().alter)
    inversion = obj.inversion() if obj.inversion() else 0
    if kind == "roman":
        quality = CHORD_COMMON_NAME_TO_TYPE[obj.commonName]
        applied_to = (
            ROMAN_TO_INT[obj.secondaryRomanNumeral.figure.upper()]
            if obj.secondaryRomanNumeral
            else 0
        )
    else:
        quality = obj.chordKind
        applied_to = 0
    if added_tone:
        quality = _BASE_AND_TONE_TO_QUALITY[quality, added_tone]

    return {
        "step": step,
        "accidental": accidental,
        "inversion": inversion,
        "quality": quality,
        "applied_to": applied_to,
    }


def _format_postfix_accidental(text):
    text = re.sub("([A-G][b#]*)-", "\\1m", text)
    text = re.sub("([A-G])bb", "\\1--", text)
    text = re.sub("([A-G])b", "\\1-", text)
    return text


def _extract_prefixed_accidental(text):
    if not text:
        return "", ""

    accidental = ""

    while text and text[0] in ["-", "#", "b"]:
        accidental += text[0]
        text = text[1:]

    return text, accidental
