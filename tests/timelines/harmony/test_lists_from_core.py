import pytest

from tilia.parsers.csv import harmony as csv_harmony
from tilia.timelines.harmony import constants, validators
from tilia.timelines.harmony.components import harmony as component
from tilia.ui.dialogs import harmony_params
from tilia.ui.timelines.harmony import utils
from tilia.ui.timelines.harmony.elements import harmony as element
from tilia.ui.timelines.harmony.elements import harmony_attrs
from tilia.ui.windows import settings
from tilia_core import rules

SHARED = [
    (validators, "HARMONY_ACCIDENTALS"),
    (validators, "HARMONY_DISPLAY_MODES"),
    (validators, "FONT_TYPES"),
    (validators, "get_inversion_amount"),
    (harmony_attrs, "HARMONY_DISPLAY_MODES"),
    (harmony_attrs, "FONT_TYPES"),
    (harmony_attrs, "get_inversion_amount"),
    (harmony_params, "HARMONY_DISPLAY_MODES"),
    (harmony_params, "get_inversion_amount"),
    (settings, "HARMONY_DISPLAY_MODES"),
    (component, "ADDED_TONE_QUALITIES"),
    (component, "get_inversion_amount"),
    (utils, "split_added_tone"),
    (element, "split_added_tone"),
]


@pytest.mark.parametrize("module, name", SHARED)
def test_each_list_is_the_cores_object(module, name):
    assert getattr(module, name) is getattr(rules, name)


@pytest.mark.parametrize(
    "name",
    [
        "HARMONY_ACCIDENTALS",
        "HARMONY_DISPLAY_MODES",
        "FONT_TYPES",
        "ADDED_TONE_QUALITIES",
        "split_added_tone",
        "get_inversion_amount",
        "NO_INVERSION_QUALITIES",
        "_NO_INVERSION_QUALITIES",
        "CADENTIAL_SIX_FOUR",
    ],
)
def test_the_app_keeps_no_copy(name):
    assert not hasattr(constants, name)


def test_each_added_tone_quality_comes_right_after_its_base_quality():
    qualities = constants.HARMONY_QUALITIES
    for quality, (base, _) in rules.ADDED_TONE_QUALITIES.items():
        assert quality in qualities
        assert qualities.index(base) < qualities.index(quality)


def test_qualities_without_inversions_have_none():
    for quality in rules.NO_INVERSION_QUALITIES:
        assert quality in constants.HARMONY_QUALITIES
        assert rules.get_inversion_amount(quality) == 0


def test_the_csv_reader_names_the_valid_modes_as_a_list():
    with pytest.raises(ValueError, match=r"\['letter', 'roman', 'custom'\]"):
        csv_harmony._parse_display_mode("nope")
    with pytest.raises(ValueError, match=r"\['analytic', 'normal'\]"):
        csv_harmony._parse_custom_text_font_type("nope")


def test_the_cadential_six_four_tone_is_the_one_the_core_gives():
    assert constants.CADENTIAL_SIX_FOUR_TONE == (
        rules.ADDED_TONE_QUALITIES["cadential-six-four"][1]
    )
