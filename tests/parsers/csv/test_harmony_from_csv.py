from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

import tilia.parsers.csv.harmony
from tests.mock import patch_file_dialog
from tests.parsers.csv.common import assert_in_errors
from tests.utils import undoable
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.ui import commands


def call_patched_import_by_time_func(timeline: HarmonyTimeline, data: str):
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = tilia.parsers.csv.harmony.import_by_time(
            timeline,
            Path(),  # any path will do, as builtins.open is patched
        )
    return success, errors


def call_patched_import_by_measure_func(
    harmony_tl: HarmonyTimeline, beat_tl: BeatTimeline, data: str
):
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = tilia.parsers.csv.harmony.import_by_measure(
            harmony_tl,
            beat_tl,
            Path(),  # any path will do, as builtins.open is patched
        )
    return success, errors


TEST_HARMONY_PARAMETERS = [
    ("C#", 0, 1, "major"),
    ("Dm", 1, 0, "minor"),
    ("Ebo7", 2, -1, "diminished-seventh"),
    ("Bb7b9", 6, -1, "dominant-seventh-flat-ninth"),
]

TEST_MODE_PARAMETERS = [
    ("C#", 0, 1, "major"),
    ("d", 1, 0, "minor"),
    ("Ebb", 2, -2, "major"),
]


class TestByTime:
    @pytest.mark.parametrize(
        "symbol,step,accidental,quality",
        [
            ("C#", 0, 1, "major"),
            ("C7b9", 0, 0, "dominant-seventh-flat-ninth"),
            ("V7b9", 4, 0, "dominant-seventh-flat-ninth"),
        ],
    )
    def test_harmony_by_time(self, symbol, step, accidental, quality, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", f"0,harmony,{symbol}"])

        success, errors = call_patched_import_by_time_func(harmony_tl, data)

        assert not errors
        assert len(harmony_tl) == 1
        assert isinstance(harmony_tl[0], Harmony)
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("quality") == quality

    @pytest.mark.parametrize("symbol,step,accidental,type", TEST_MODE_PARAMETERS)
    def test_mode_by_time(self, symbol, step, accidental, type, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", f"0,key,{symbol}"])

        success, errors = call_patched_import_by_time_func(harmony_tl, data)

        assert not errors
        assert len(harmony_tl) == 1
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("type") == type

    @pytest.mark.parametrize("required_attr", ["time", "symbol", "harmony_or_key"])
    def test_fails_without_a_required_column(self, required_attr, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol,",
            ]
        )
        data = data.replace(f"{required_attr},", "")
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors(required_attr, errors)

    def test_returns_error_for_invalid_rows_and_processes_valid_rows(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,C",
                "10,nonsense,X",
                "20,harmony,D",
            ]
        )

        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert len(harmony_tl) == 2
        assert_in_errors("nonsense", errors)

    def test_returns_reason_for_invalid_component(self, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", "0,harmony,C", "0,harmony,D"])
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("harmony", errors)

    @pytest.mark.parametrize("invalid_row_index", [0, 1, 2])
    def test_fails_if_invalid_attr_value(self, invalid_row_index, harmony_tl):
        row_data = ["0", "harmony", "C"]
        row_data[invalid_row_index] = "cursed input"
        data = "\n".join(
            (
                [
                    "time,harmony_or_key,symbol",
                    ",".join(row_data),
                ]
            )
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("cursed", errors)
        assert harmony_tl.is_empty

    def test_row_fails_if_missing_required_value(self, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", "0,harmony", "0,harmony,D"])
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("symbol", errors)
        assert len(harmony_tl) == 1

    def test_row_does_not_fail_if_missing_non_required_value(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol,display_mode",
                "0,harmony,C",
                "10,harmony,D,letter",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("display_mode", errors)
        assert len(harmony_tl) == 2

    def test_text_appended_to_error_is_displayed(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,nonsense,C",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("Must be", errors)

    def test_added_tone_in_the_bass_is_reported(self, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", "0,harmony,C7b9/Db"])

        success, errors = call_patched_import_by_time_func(harmony_tl, data)

        assert_in_errors("C7b9/Db", errors)
        assert len(harmony_tl) == 0

    def test_harmony_considers_existing_key(self, harmony_tl):
        harmony_tl.create_mode(step=2)
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,IV",
            ]
        )
        call_patched_import_by_time_func(harmony_tl, data)
        assert harmony_tl.harmonies()[0].get_data("step") == 5

    def test_harmony_considers_key_created_on_previous_row(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,key,E",
                "0,harmony,IV",
            ]
        )
        call_patched_import_by_time_func(harmony_tl, data)
        assert harmony_tl.harmonies()[0].get_data("step") == 5


class TestByMeasure:
    @pytest.mark.parametrize("symbol,step,accidental,quality", TEST_HARMONY_PARAMETERS)
    def test_harmony_by_measure(
        self, symbol, step, accidental, quality, harmony_tl, beat_tl
    ):
        beat_tl.set_data("beat_pattern", [2])
        for i in range(6):
            beat_tl.create_beat(i * 10)

        data = "\n".join(
            [
                "harmony_or_key,measure,fraction,symbol",
                f"harmony,1,0,{symbol}",
                f"harmony,2,0,{symbol}",
                f"harmony,3,0,{symbol}",
            ]
        )

        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)

        assert not errors
        assert len(harmony_tl) == 3
        assert isinstance(harmony_tl[0], Harmony)
        assert harmony_tl[0].get_data("time") == 0
        assert harmony_tl[1].get_data("time") == 20
        assert harmony_tl[2].get_data("time") == 40
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("quality") == quality

    @pytest.mark.parametrize("symbol,step,accidental,type", TEST_MODE_PARAMETERS)
    def test_mode_by_measure(self, symbol, step, accidental, type, harmony_tl, beat_tl):
        beat_tl.set_data("beat_pattern", [2])
        for i in range(6):
            beat_tl.create_beat(i * 10)

        data = "\n".join(
            [
                "harmony_or_key,measure,fraction,symbol",
                f"key,1,0,{symbol}",
                f"key,2,0,{symbol}",
                f"key,3,0,{symbol}",
            ]
        )

        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)

        assert not errors
        assert len(harmony_tl) == 3
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("time") == 0
        assert harmony_tl[1].get_data("time") == 20
        assert harmony_tl[2].get_data("time") == 40
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("type") == type


OPTIONAL_HARMONY_VALUES = {
    "comments": "a comment",
    "display_mode": "roman",
    "custom_text": "my text",
    "custom_text_font_type": "normal",
}
OPTIONAL_HEADER = "comments,display_mode,custom_text,custom_text_font_type"
OPTIONAL_ROW = "a comment,roman,my text,normal"


def make_beats(beat_tl):
    beat_tl.set_data("beat_pattern", [2])
    for i in range(6):
        beat_tl.create_beat(i * 10)


class TestOptionalColumns:
    def test_harmony_by_time(self, harmony_tl):
        data = "\n".join(
            [
                f"time,harmony_or_key,symbol,{OPTIONAL_HEADER}",
                f"0,harmony,C,{OPTIONAL_ROW}",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert not errors
        for attr, value in OPTIONAL_HARMONY_VALUES.items():
            assert harmony_tl[0].get_data(attr) == value

    def test_harmony_by_measure(self, harmony_tl, beat_tl):
        make_beats(beat_tl)
        data = "\n".join(
            [
                f"harmony_or_key,measure,fraction,symbol,{OPTIONAL_HEADER}",
                f"harmony,2,0,C,{OPTIONAL_ROW}",
            ]
        )
        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)
        assert not errors
        assert harmony_tl[0].get_data("time") == 20
        for attr, value in OPTIONAL_HARMONY_VALUES.items():
            assert harmony_tl[0].get_data(attr) == value

    def test_key_by_time(self, harmony_tl):
        data = "\n".join(
            [
                f"time,harmony_or_key,symbol,{OPTIONAL_HEADER}",
                f"0,key,C,{OPTIONAL_ROW}",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert not errors
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("comments") == "a comment"

    def test_key_by_measure(self, harmony_tl, beat_tl):
        make_beats(beat_tl)
        data = "\n".join(
            [
                f"harmony_or_key,measure,fraction,symbol,{OPTIONAL_HEADER}",
                f"key,2,0,C,{OPTIONAL_ROW}",
            ]
        )
        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)
        assert not errors
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("comments") == "a comment"

    def test_absent_columns_keep_defaults_by_time(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,C",
                "10,key,D",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert not errors
        harmony = harmony_tl.harmonies()[0]
        assert harmony.get_data("comments") == ""
        assert harmony.get_data("display_mode") == "letter"
        assert harmony.get_data("custom_text") == ""
        assert harmony.get_data("custom_text_font_type") == "analytic"
        assert harmony_tl.modes()[0].get_data("comments") == ""

    def test_absent_columns_keep_defaults_by_measure(self, harmony_tl, beat_tl):
        make_beats(beat_tl)
        data = "\n".join(
            [
                "harmony_or_key,measure,fraction,symbol",
                "harmony,1,0,C",
            ]
        )
        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)
        assert not errors
        assert harmony_tl[0].get_data("display_mode") == "letter"
        assert harmony_tl[0].get_data("custom_text_font_type") == "analytic"

    def test_invalid_value_is_reported_and_default_kept(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol,display_mode,comments",
                "0,harmony,C,nonsense,hello",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert_in_errors("nonsense", errors)
        assert harmony_tl[0].get_data("display_mode") == "letter"
        assert harmony_tl[0].get_data("comments") == "hello"


class TestSymbolsThatRaise:
    def test_key_symbol_without_note_name_is_reported(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,key,X",
                "10,key,D",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert success
        assert_in_errors("X", errors)
        assert len(harmony_tl.modes()) == 1

    def test_by_time(self, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,key,C",
                "10,key,F:min",
                "20,harmony,V42/bVII",
                "30,harmony,D",
            ]
        )
        success, errors = call_patched_import_by_time_func(harmony_tl, data)
        assert success
        assert_in_errors("F:min", errors)
        assert_in_errors("V42/bVII", errors)
        assert len(harmony_tl.modes()) == 1
        assert len(harmony_tl.harmonies()) == 1

    def test_by_measure(self, harmony_tl, beat_tl):
        make_beats(beat_tl)
        data = "\n".join(
            [
                "harmony_or_key,measure,fraction,symbol",
                "key,1,0,C",
                "key,2,0,F:min",
                "harmony,2,0,V42/bVII",
                "harmony,3,0,D",
            ]
        )
        success, errors = call_patched_import_by_measure_func(harmony_tl, beat_tl, data)
        assert success
        assert_in_errors("F:min", errors)
        assert_in_errors("V42/bVII", errors)
        assert len(harmony_tl.modes()) == 1
        assert len(harmony_tl.harmonies()) == 1


class TestImportCommand:
    def test_import_with_symbols_that_raise_is_one_undo_step(
        self, harmony_tlui, tmp_path
    ):
        path = tmp_path / "harmonies.csv"
        path.write_text(
            "\n".join(
                [
                    "time,harmony_or_key,symbol,comments",
                    "0,key,C,home key",
                    "10,key,F:min,",
                    "20,harmony,V42/bVII,",
                    "30,harmony,D,a comment",
                ]
            )
        )

        with (
            patch(
                "tilia.ui.timelines.collection.import_._get_by_time_or_by_measure_from_user",
                return_value=(True, "time"),
            ),
            patch_file_dialog(True, [str(path)]),
            undoable(),
        ):
            commands.execute("timelines.import.harmony")

        harmony_tl = harmony_tlui.timeline
        assert len(harmony_tl.modes()) == 1
        assert len(harmony_tl.harmonies()) == 1
        assert harmony_tl.harmonies()[0].get_data("comments") == "a comment"
