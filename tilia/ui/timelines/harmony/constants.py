import music21.harmony
import music21.pitch

ACCIDENTAL_TO_INT = {"": 0, "♯": 1, "♭": -1, "𝄪": 2, "𝄫": -2}


class Accidental:
    TYPE_TO_NUMBER_TO_SYMBOL = {
        "music21": {0: "", 1: "#", -1: "-", 2: "##", -2: "--"},
        "musanalysis": {
            -2: "`b`b",
            -1: "`b",
            0: "",
            1: "`#",
            2: "`x",
        },
        "frontend": {
            -2: "bb",
            -1: "b",
            0: "",
            1: "#",
            2: "##",
        },
    }

    @staticmethod
    def get_from_int(symbol_type: str, value: int):
        if symbol_type not in Accidental.TYPE_TO_NUMBER_TO_SYMBOL:
            raise ValueError("Invalid symbol type")

        number_to_symbol = Accidental.TYPE_TO_NUMBER_TO_SYMBOL[symbol_type]

        def get_substitute():
            if isinstance(value, float) or isinstance(value, int):
                positivity = 1 if value > 0 else -1
                tones = int(abs(value // 2))
                semitones = int(abs(value % 2))
                return (
                    number_to_symbol[positivity] * semitones
                    + number_to_symbol[positivity * 2] * tones
                )
            raise KeyError

        return number_to_symbol.get(value, get_substitute())


STEP_TO_PITCH_CLASS = {
    i: music21.pitch.Pitch(s).pitchClass
    for i, s in enumerate(["C", "D", "E", "F", "G", "A", "B"])
}

QUALITY_TO_ABBREVIATION = {
    qlt: data[1][0] for qlt, data in music21.harmony.CHORD_TYPES.items()
}
