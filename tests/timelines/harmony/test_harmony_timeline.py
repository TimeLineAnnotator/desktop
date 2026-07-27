import pytest

from tilia.timelines.harmony.constants import get_inversion_amount


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
