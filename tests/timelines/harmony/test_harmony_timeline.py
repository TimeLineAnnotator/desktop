import pytest

from tilia.timelines.harmony.components.mode import (
    get_params_from_text as get_mode_params_from_text,
)
from tilia.timelines.harmony.constants import MODE_TYPES
from tilia_core.rules import get_inversion_amount


class TestGetInversionAmount:
    def test_triad_has_two_inversions(self):
        assert get_inversion_amount("major") == 2

    def test_seventh_chord_has_three_inversions(self):
        assert get_inversion_amount("dominant-seventh") == 3

    def test_ninth_chord_has_four_inversions(self):
        assert get_inversion_amount("dominant-ninth") == 4

    def test_eleventh_chord_has_five_inversions(self):
        assert get_inversion_amount("dominant-11th") == 5

    def test_thirteenth_chord_has_six_inversions(self):
        assert get_inversion_amount("dominant-13th") == 6

    def test_added_tone_adds_no_inversion(self):
        # A dominant seventh with a flat ninth has the dominant seventh's three.
        assert get_inversion_amount("dominant-seventh-flat-ninth") == 3

    def test_invalid_quality_raises_value_error(self):
        with pytest.raises(ValueError):
            get_inversion_amount("not-a-quality")

    @pytest.mark.parametrize(
        "quality",
        ["Italian", "French", "German", "Neapolitan", "Tristan", "power"],
    )
    def test_qualities_without_inversion_display_have_no_inversions(self, quality):
        # These qualities either have no inversions in standard tonal harmony
        # (the augmented sixths are defined by having b6 in the bass) or their
        # label is a fixed string regardless of bass note, so the inspector
        # and add-harmony dialog shouldn't offer inversions for them.
        assert get_inversion_amount(quality) == 0


class TestInversionValidation:
    def test_inversion_within_quality_range_is_accepted(self, harmony_tl):
        harmony, _ = harmony_tl.create_harmony(quality="major")
        _, success = harmony.set_data("inversion", 2)
        assert success
        assert harmony.inversion == 2

    def test_inversion_exceeding_quality_range_is_rejected(self, harmony_tl):
        harmony, _ = harmony_tl.create_harmony(quality="major")
        _, success = harmony.set_data("inversion", 3)
        assert not success
        assert harmony.inversion == 0

    def test_negative_inversion_is_rejected(self, harmony_tl):
        harmony, _ = harmony_tl.create_harmony(quality="major")
        _, success = harmony.set_data("inversion", -1)
        assert not success

    def test_ninth_chord_accepts_fourth_inversion(self, harmony_tl):
        harmony, _ = harmony_tl.create_harmony(quality="dominant-ninth")
        _, success = harmony.set_data("inversion", 4)
        assert success
        assert harmony.inversion == 4

    def test_ninth_chord_rejects_fifth_inversion(self, harmony_tl):
        harmony, _ = harmony_tl.create_harmony(quality="dominant-ninth")
        _, success = harmony.set_data("inversion", 5)
        assert not success


class TestModeKey:
    def test_major_mode_key(self, harmony_tl):
        mode, _ = harmony_tl.create_mode(type="major")
        assert mode.key.mode == "major"

    def test_minor_mode_key(self, harmony_tl):
        mode, _ = harmony_tl.create_mode(type="minor")
        assert mode.key.mode == "minor"

    def test_dorian_mode_key(self, harmony_tl):
        mode, _ = harmony_tl.create_mode(type="dorian")
        assert mode.key.mode == "dorian"

    def test_phrygian_mode_key(self, harmony_tl):
        mode, _ = harmony_tl.create_mode(type="phrygian")
        assert mode.key.mode == "phrygian"


# What a file can hold that TiLiA can't read of a mode's key: its tonic, by its
# step or its accidental, or its type. A file's components are created
# unchecked, as the reader keeps a mode that breaks a rule. Each step is the one
# the `applied_to` updates read.
MODES_TILIA_CANT_READ = {
    "tonic's step": {"step": 9},
    "tonic's accidental": {"step": 4, "accidental": 5},
    "type": {"step": 4, "type": "some-future-type"},
}

# What a type names, whatever its capitals: the type of the key TiLiA reads.
TYPES_TILIA_CAN_READ = {
    "major": "major",
    "minor": "minor",
    "dorian": "dorian",
    "phrygian": "phrygian",
    "lydian": "lydian",
    "mixolydian": "mixolydian",
    "locrian": "locrian",
    "ionian": "major",
    "aeolian": "minor",
}

# music21 makes a key of the first six, with a key signature that doesn't match its
# scale.
TYPES_TILIA_CANT_READ = [
    "hypodorian",
    "Hypophrygian",
    "hypolydian",
    "hypomixolydian",
    "hypolocrian",
    "hypoaeolian",
    "some-future-type",
    "harmonic minor",
    "chromatic",
    "major ",
    "maj",
    "",
]

with_a_mode_tilia_cant_read = pytest.mark.parametrize(
    "unreadable",
    MODES_TILIA_CANT_READ.values(),
    ids=MODES_TILIA_CANT_READ.keys(),
)


def key_name(key) -> tuple[str, str]:
    return key.tonic.name, key.mode


class TestAKeyTiLiACantRead:
    """After a mode whose tonic or type TiLiA can't read, up to the next mode,
    TiLiA can't read the key, and what needs one takes C major (Anne, 2026-11-19,
    TimeLineAnnotator/project-management#605, a)."""

    @with_a_mode_tilia_cant_read
    def test_its_key_is_c_major(self, harmony_tl, unreadable):
        mode, _ = harmony_tl.create_mode(0, checked=False, **unreadable)

        assert key_name(mode.key) == ("C", "major")
        assert key_name(harmony_tl.get_key_by_time(1)) == ("C", "major")

    @with_a_mode_tilia_cant_read
    def test_the_key_can_t_be_read_up_to_the_next_mode(self, harmony_tl, unreadable):
        harmony_tl.create_mode(10, checked=False, **unreadable)
        harmony_tl.create_mode(20, step=1)  # D major

        assert harmony_tl.can_read_key_by_time(5)  # before any mode: C major
        assert not harmony_tl.can_read_key_by_time(10)
        assert not harmony_tl.can_read_key_by_time(15)
        assert harmony_tl.can_read_key_by_time(20)
        assert key_name(harmony_tl.get_key_by_time(25)) == ("D", "major")

    @pytest.mark.parametrize("mode_type", TYPES_TILIA_CANT_READ, ids=repr)
    def test_every_other_type_can_t_be_read(self, harmony_tl, mode_type):
        mode, _ = harmony_tl.create_mode(0, step=4, type=mode_type, checked=False)

        assert not harmony_tl.can_read_key_by_time(1)
        assert key_name(mode.key) == ("C", "major")


class TestTheTypesTiLiACanRead:
    """Nine, whatever their capitals: those TiLiA offers, ionian as major and
    aeolian as minor (Anne, 2026-11-25, TimeLineAnnotator/project-management#677,
    1c)."""

    @pytest.mark.parametrize("spell", [str.lower, str.capitalize, str.upper])
    @pytest.mark.parametrize("mode_type, key_type", TYPES_TILIA_CAN_READ.items())
    def test_its_key(self, harmony_tl, mode_type, key_type, spell):
        spelling = spell(mode_type)
        mode, _ = harmony_tl.create_mode(0, step=4, type=spelling, checked=False)

        assert harmony_tl.can_read_key_by_time(1)
        assert key_name(mode.key) == ("G", key_type)
        assert mode.get_data("type") == spelling

    def test_they_are_the_ones_tilia_offers_and_two_more(self):
        assert set(TYPES_TILIA_CAN_READ) == {*MODE_TYPES, "ionian", "aeolian"}

    @pytest.mark.parametrize("mode_type", ["ionian", "Aeolian", "Major"])
    def test_only_the_ones_tilia_offers_can_be_given(self, harmony_tl, mode_type):
        # As spelled: one a file holds is read, and stays until another is picked.
        mode, _ = harmony_tl.create_mode(0)

        assert mode.set_data("type", mode_type) == (None, False)
        assert mode.get_data("type") == "major"


class TestAppliedToNextToAModeTiLiACantRead:
    """Adding or deleting a mode leaves the `applied_to` of the harmonies after it
    as it is where either mode's key can't be read, by its tonic or its type: what
    they were applied to can't be known (Anne, 2026-11-19,
    TimeLineAnnotator/project-management#606, a). Each case's numbers are ones
    that the recomputation would change."""

    @staticmethod
    def applied_to(harmony_tl) -> int:
        (harmony,) = harmony_tl.harmonies()
        return harmony.get_data("applied_to")

    @with_a_mode_tilia_cant_read
    def test_adding_a_mode_after_one_tilia_can_t_read(self, harmony_tl, unreadable):
        harmony_tl.create_mode(0, checked=False, **unreadable)
        harmony_tl.create_harmony(5, step=4, applied_to=0)  # G

        mode, _ = harmony_tl.create_mode(3, step=3)  # F major

        assert mode is not None
        assert self.applied_to(harmony_tl) == 0

    @with_a_mode_tilia_cant_read
    def test_adding_a_mode_tilia_can_t_read(self, harmony_tl, unreadable):
        harmony_tl.create_mode(0, step=6)  # B major
        harmony_tl.create_harmony(5, step=4, applied_to=3)

        mode, _ = harmony_tl.create_mode(3, checked=False, **unreadable)

        assert mode is not None
        assert self.applied_to(harmony_tl) == 3

    @with_a_mode_tilia_cant_read
    def test_deleting_a_mode_after_one_tilia_can_t_read(self, harmony_tl, unreadable):
        harmony_tl.create_mode(0, checked=False, **unreadable)
        mode, _ = harmony_tl.create_mode(3, step=3)  # F major
        harmony_tl.create_harmony(5, step=4, applied_to=6)

        harmony_tl.delete_components([mode])

        assert mode not in harmony_tl.modes()
        assert self.applied_to(harmony_tl) == 6

    @with_a_mode_tilia_cant_read
    def test_deleting_a_mode_tilia_can_t_read(self, harmony_tl, unreadable):
        harmony_tl.create_mode(0, step=6)  # B major
        mode, _ = harmony_tl.create_mode(3, checked=False, **unreadable)
        harmony_tl.create_harmony(5, step=4, applied_to=3)

        harmony_tl.delete_components([mode])

        assert mode not in harmony_tl.modes()
        assert self.applied_to(harmony_tl) == 3

    # As TiLiA spells it, and as only a file can.
    @pytest.mark.parametrize("mode_type", ["major", "Ionian"])
    def test_adding_a_mode_after_one_tilia_can_read_recomputes_it(
        self, harmony_tl, mode_type
    ):
        harmony_tl.create_mode(0, step=4, type=mode_type, checked=False)  # G
        harmony_tl.create_harmony(5, step=4, applied_to=0)

        harmony_tl.create_mode(3, step=3)  # F major

        assert self.applied_to(harmony_tl) == 1  # 0 + 4 - 3

    @pytest.mark.parametrize("mode_type", ["major", "Ionian"])
    def test_deleting_a_mode_after_one_tilia_can_read_recomputes_it(
        self, harmony_tl, mode_type
    ):
        harmony_tl.create_mode(0, step=4, type=mode_type, checked=False)  # G
        mode, _ = harmony_tl.create_mode(3, step=3)  # F major
        harmony_tl.create_harmony(5, step=4, applied_to=6)

        harmony_tl.delete_components([mode])

        assert self.applied_to(harmony_tl) == 5  # 6 + 3 - 4


class TestModeParamsFromText:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("C", {"step": 0, "accidental": 0, "type": "major"}),
            ("f#", {"step": 3, "accidental": 1, "type": "minor"}),
        ],
    )
    def test_valid_symbol(self, text, expected):
        assert get_mode_params_from_text(text) == (True, expected)

    @pytest.mark.parametrize("text", ["F:min", "X", "V", ""])
    def test_invalid_symbol_fails_without_raising(self, text):
        assert get_mode_params_from_text(text) == (False, None)


class TestValidateComponentCreation:
    def test_allows_harmony_at_same_time_as_mode(self, harmony_tl):
        harmony_tl.create_harmony()
        harmony_tl.create_mode()

        assert len(harmony_tl) == 2

    def test_allows_mode_at_same_time_as_harmony(self, harmony_tl):
        harmony_tl.create_mode()
        harmony_tl.create_harmony()

        assert len(harmony_tl) == 2

    def test_harmony_at_same_time_fails(self, harmony_tl):
        harmony_tl.create_harmony()
        harmony_tl.create_harmony()

        assert len(harmony_tl) == 1

    def test_mode_at_same_time_fails(self, harmony_tl):
        harmony_tl.create_mode()
        harmony_tl.create_mode()

        assert len(harmony_tl) == 1
