from itertools import combinations

import pytest

from tilia.timelines.score.pcset import (
    SEMITONES,
    analyse,
    forte_name,
    interval_class_vector,
    inversions,
    normal_form,
    prime_form,
    transpositions,
)


class TestNormalForm:
    def test_empty(self):
        assert normal_form([]) == ()

    def test_most_compact_rotation(self):
        # In semitones: B, C, E.
        assert normal_form([0, 4, 11], SEMITONES) == (11, 0, 4)

    def test_quarter_tones(self):
        assert normal_form([23, 1, 3]) == (23, 1, 3)

    def test_ignores_doublings_and_octaves(self):
        assert normal_form([0, 24, 48, 5]) == (0, 5)

    def test_symmetric_set_starts_on_lowest(self):
        assert normal_form([0, 6, 12, 18]) == (0, 6, 12, 18)


class TestPrimeForm:
    @pytest.mark.parametrize(
        "pcs,prime",
        [
            ([0, 4, 7], (0, 3, 7)),  # major triad, 3-11
            ([0, 3, 7], (0, 3, 7)),
            ([0, 3, 6, 9], (0, 3, 6, 9)),
            ([0, 1, 4, 6], (0, 1, 4, 6)),  # 4-Z15
            # Where Rahn and Forte differ, Rahn's.
            ([0, 1, 5, 6, 8], (0, 1, 5, 6, 8)),  # 5-20
            ([0, 1, 3, 6, 8, 9], (0, 2, 3, 6, 7, 9)),  # 6-Z29
            ([0, 1, 4, 5, 7, 9], (0, 1, 4, 5, 7, 9)),  # 6-31
        ],
    )
    def test_known_prime_forms_in_semitones(self, pcs, prime):
        assert prime_form(pcs, SEMITONES) == prime

    def test_quarter_tone_trichord(self):
        # C, C quarter-sharp, E.
        assert prime_form([0, 1, 8]) == (0, 1, 8)
        # Its inversion has the same prime form.
        assert prime_form([0, 7, 8]) == (0, 1, 8)

    @pytest.mark.parametrize("n", range(24))
    def test_same_under_transposition_and_inversion(self, n):
        pcs = [0, 1, 5, 11, 14]
        expected = prime_form(pcs)
        assert prime_form([pc + n for pc in pcs]) == expected
        assert prime_form([n - pc for pc in pcs]) == expected

    def test_counts_the_224_set_classes_of_12_notes(self):
        classes = {
            prime_form(subset, SEMITONES)
            for size in range(13)
            for subset in combinations(range(12), size)
        }
        assert len(classes) == 224

    def test_counts_the_set_classes_of_three_notes_in_24(self):
        # Each class is one orbit of the group of transpositions and inversions.
        orbits = set()
        for subset in combinations(range(24), 3):
            orbit = frozenset(
                frozenset((sign * pc + n) % 24 for pc in subset)
                for n in range(24)
                for sign in (1, -1)
            )
            orbits.add(orbit)
        classes = {prime_form(subset) for subset in combinations(range(24), 3)}
        assert len(classes) == len(orbits)


class TestIntervalClassVector:
    def test_major_triad_in_semitones(self):
        assert interval_class_vector([0, 4, 7], SEMITONES) == (0, 0, 1, 1, 1, 0)

    def test_has_twelve_classes_in_quarter_tones(self):
        assert len(interval_class_vector([0, 1])) == 12

    def test_quarter_tone_and_half_octave(self):
        assert interval_class_vector([0, 1]) == (1,) + (0,) * 11
        assert interval_class_vector([0, 12]) == (0,) * 11 + (1,)

    def test_empty(self):
        assert interval_class_vector([]) == (0,) * 12


class TestForteName:
    @pytest.mark.parametrize(
        "semitones,name",
        [
            ([0, 3, 7], "3-11"),
            ([0, 4, 7], "3-11"),
            ([0, 1, 4, 6], "4-Z15"),
            ([0, 1, 5, 6, 8], "5-20"),
            ([0, 1, 3, 6, 8, 9], "6-Z29"),
        ],
    )
    def test_of_a_set_in_semitones(self, semitones, name):
        assert forte_name([pc * 2 for pc in semitones]) == name

    def test_of_a_set_of_only_quarter_tones(self):
        # A major triad a quarter tone up.
        assert forte_name([1, 9, 15]) == "3-11"

    def test_none_for_a_set_mixing_semitones_and_quarter_tones(self):
        assert forte_name([0, 1, 8]) is None

    def test_none_for_the_empty_set(self):
        assert forte_name([]) is None


def test_analyse():
    analysis = analyse([8, 0, 14, 24])
    assert analysis.pitch_classes == (0, 8, 14)
    assert analysis.cardinality == 3
    assert analysis.normal_form == (0, 8, 14)
    assert analysis.prime_form == (0, 6, 14)
    assert analysis.interval_class_vector == ((0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0))
    # A major triad.
    assert analysis.forte_name == "3-11"


class TestOperations:
    def test_transposition(self):
        assert transpositions([0, 5, 14], [5, 10, 19]) == (5,)

    def test_transposition_wraps(self):
        assert transpositions([20, 22], [2, 4]) == (6,)

    def test_inversion(self):
        # 5 - 0, 5 - 5, 5 - 14.
        assert inversions([0, 5, 14], [5, 0, 15]) == (5,)

    def test_inversion_wraps(self):
        assert inversions([1, 3], [23, 21]) == (0,)

    def test_asymmetric_set_is_not_its_own_inversion(self):
        assert transpositions([0, 5, 14], [0, 5, 15]) == ()
        assert inversions([0, 5, 14], [5, 10, 19]) == ()

    def test_symmetric_set_has_several_operations(self):
        assert transpositions([1, 13], [4, 16]) == (3, 15)
        assert inversions([1, 13], [4, 16]) == (5, 17)

    def test_set_is_its_own_transposition(self):
        assert transpositions([0, 5, 14], [0, 5, 14]) == (0,)

    def test_unrelated_sets(self):
        assert transpositions([0, 5, 10], [0, 5, 14]) == ()
        assert inversions([0, 5, 10], [0, 5, 14]) == ()

    def test_different_cardinalities(self):
        assert transpositions([0, 5], [0, 5, 10]) == ()
        assert inversions([0, 5], [0, 5, 10]) == ()

    def test_no_pitch_classes(self):
        assert transpositions([], []) == ()
        assert inversions([], []) == ()
        assert transpositions([0], []) == ()
        assert inversions([], [0]) == ()

    def test_ignores_doublings_and_octaves(self):
        assert transpositions([0, 24, 5], [2, 7]) == (2,)
        assert inversions([0, 24, 5], [5, 0, 48]) == (5,)

    def test_in_semitones(self):
        assert transpositions([0, 4, 7], [7, 11, 2], SEMITONES) == (7,)
        assert inversions([0, 4, 7], [0, 3, 7], SEMITONES) == (7,)

    def test_found_for_every_operation(self):
        pcs = [0, 5, 14]
        for n in range(24):
            assert n in transpositions(pcs, [pc + n for pc in pcs])
            assert n in inversions(pcs, [n - pc for pc in pcs])

    def test_related_exactly_when_prime_forms_match(self):
        source = (0, 5, 14)
        for target in combinations(range(24), 3):
            related = transpositions(source, target) or inversions(source, target)
            assert bool(related) == (prime_form(source) == prime_form(target))
