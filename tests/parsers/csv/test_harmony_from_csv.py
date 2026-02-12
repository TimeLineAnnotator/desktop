from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

import tilia.parsers.csv.harmony
from tests.parsers.csv.common import assert_in_errors
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.harmony.timeline import HarmonyTimeline


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
]

TEST_MODE_PARAMETERS = [
    ("C#", 0, 1, "major"),
    ("d", 1, 0, "minor"),
    ("Ebb", 2, -2, "major"),
]


class TestByTime:
    @pytest.mark.parametrize("symbol,step,accidental,quality", [("C#", 0, 1, "major")])
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
                "10,harmony,D,chord",
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
