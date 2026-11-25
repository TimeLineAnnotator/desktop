"""The modes only a file can hold: of a type TiLiA doesn't offer, read or not. Each
test opens a file through the core, as no action makes such a mode."""

import pytest

from tests.file.test_open_through_core import (
    HARMONIES,
    a_file,
    a_harmony,
    a_harmony_timeline,
    a_mode,
    open_file,
    together,
    with_media_length,
)
from tests.ui.timelines.harmony.test_harmony_timeline_ui import (
    add_mode,
    typing_in_the_add_harmony_dialog,
)
from tilia.errors import ROMAN_NUMERAL_KEY_UNREADABLE
from tilia.ui import commands


@pytest.fixture
def open_a_file_with(qtui, tilia_state, tmp_path):
    """Opens a file with these components in its harmony timeline, and gives that
    timeline's UI."""

    def open_(*components):
        change = together(a_harmony_timeline(*components), with_media_length(100.0))
        assert open_file(a_file(tmp_path, change))
        tilia_state.current_time = 10
        return qtui.timeline_uis.get_timeline_ui(HARMONIES)

    return open_


def type_in_the_add_harmony_dialog(*texts):
    with typing_in_the_add_harmony_dialog(*texts) as labels:
        commands.execute("timeline.harmony.add_harmony")
    return labels


class TestATypeTiLiACantRead:
    """Up to the next mode, harmonies show the mark as roman numerals, a roman numeral
    typed is refused, and letters work as before (Anne, 2026-11-19,
    TimeLineAnnotator/project-management#605, a)."""

    @pytest.fixture
    def after_it(self, open_a_file_with):
        return open_a_file_with(
            a_mode(type="some-future-type"), a_harmony(time=20.0, display_mode="letter")
        )

    def test_a_roman_numeral_typed_is_refused_and_letters_are_taken(
        self, after_it, tilia_errors
    ):
        labels = type_in_the_add_harmony_dialog("V", "Bb7")

        assert "Current key: ?" in labels
        assert tilia_errors.errors == [
            {
                "title": ROMAN_NUMERAL_KEY_UNREADABLE.title,
                "message": ROMAN_NUMERAL_KEY_UNREADABLE.message.format("00:10.0", "V"),
            }
        ]
        added = min(
            after_it.timeline.harmonies(), key=lambda harmony: harmony.get_data("time")
        )
        assert added.get_data("time") == 10
        assert (added.get_data("step"), added.get_data("accidental")) == (6, -1)
        assert added.get_data("quality") == "dominant-seventh"

    def test_display_as_roman_numeral_shows_the_mark(self, after_it, tilia_errors):
        (harmony,) = after_it.harmonies()
        after_it.select_element(harmony)

        commands.execute("timeline.harmony.component.display_as_roman")

        assert harmony.get_data("display_mode") == "roman"
        assert harmony.body.toPlainText() == "?"
        assert harmony.letter_symbol_label == "G"
        tilia_errors.assert_no_error()

    def test_the_next_mode_gives_roman_numerals_its_key(self, after_it, tilia_errors):
        add_mode(time=5, step=1)  # D major
        labels = type_in_the_add_harmony_dialog("V")

        tilia_errors.assert_no_error()
        assert "Current key: D major" in labels
        added = min(
            after_it.timeline.harmonies(), key=lambda harmony: harmony.get_data("time")
        )
        assert added.get_data("step") == 5  # A, D major's dominant

    @pytest.mark.parametrize(
        "mode", [{"step": 9}, {"type": "some-future-type"}], ids=["tonic", "type"]
    )
    def test_its_element_s_key_is_c_major(self, open_a_file_with, mode):
        (element,) = open_a_file_with(a_mode(**mode)).modes()

        assert (element.key.tonic.name, element.key.mode) == ("C", "major")
