import pytest

import tilia.parsers.csv.harmony
from tests.parsers.csv.common import assert_in_errors, write_csv
from tests.utils import long_operation_spy
from tilia.requests import LongOperation
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.harmony.timeline import HarmonyTimeline


def call_patched_import_by_time_func(tmp_path, timeline: HarmonyTimeline, data: str):
    return tilia.parsers.csv.harmony.import_by_time(timeline, write_csv(tmp_path, data))


def call_patched_import_by_measure_func(
    tmp_path, harmony_tl: HarmonyTimeline, beat_tl: BeatTimeline, data: str
):
    return tilia.parsers.csv.harmony.import_by_measure(
        harmony_tl, beat_tl, write_csv(tmp_path, data)
    )


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
    def test_harmony_by_time(
        self, tmp_path, symbol, step, accidental, quality, harmony_tl
    ):
        data = "\n".join(["time,harmony_or_key,symbol", f"0,harmony,{symbol}"])

        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)

        assert not errors
        assert len(harmony_tl) == 1
        assert isinstance(harmony_tl[0], Harmony)
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("quality") == quality

    @pytest.mark.parametrize("symbol,step,accidental,type", TEST_MODE_PARAMETERS)
    def test_mode_by_time(self, tmp_path, symbol, step, accidental, type, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", f"0,key,{symbol}"])

        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)

        assert not errors
        assert len(harmony_tl) == 1
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("type") == type

    def test_reports_progress(self, tmp_path, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,C#",
                "1,harmony,Dm",
                "2,harmony,Ebo7",
            ]
        )

        with long_operation_spy() as calls:
            call_patched_import_by_time_func(tmp_path, harmony_tl, data)

        progress_calls = [
            args for phase, args in calls if phase == LongOperation.PROGRESS
        ]
        assert progress_calls
        assert progress_calls[-1] == (3, 3)

    @pytest.mark.parametrize("required_attr", ["time", "symbol", "harmony_or_key"])
    def test_fails_without_a_required_column(self, tmp_path, required_attr, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol,",
            ]
        )
        data = data.replace(f"{required_attr},", "")
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors(required_attr, errors)

    def test_returns_error_for_invalid_rows_and_processes_valid_rows(
        self, tmp_path, harmony_tl
    ):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,C",
                "10,nonsense,X",
                "20,harmony,D",
            ]
        )

        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert len(harmony_tl) == 2
        assert_in_errors("nonsense", errors)

    def test_returns_reason_for_invalid_component(self, tmp_path, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", "0,harmony,C", "0,harmony,D"])
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors("harmony", errors)

    @pytest.mark.parametrize("invalid_row_index", [0, 1, 2])
    def test_fails_if_invalid_attr_value(self, tmp_path, invalid_row_index, harmony_tl):
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
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors("cursed", errors)
        assert harmony_tl.is_empty

    def test_row_fails_if_missing_required_value(self, tmp_path, harmony_tl):
        data = "\n".join(["time,harmony_or_key,symbol", "0,harmony", "0,harmony,D"])
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors("symbol", errors)
        assert len(harmony_tl) == 1

    def test_row_does_not_fail_if_missing_non_required_value(
        self, tmp_path, harmony_tl
    ):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol,display_mode",
                "0,harmony,C",
                "10,harmony,D,letter",
            ]
        )
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors("display_mode", errors)
        assert len(harmony_tl) == 2

    def test_text_appended_to_error_is_displayed(self, tmp_path, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,nonsense,C",
            ]
        )
        success, errors = call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert_in_errors("Must be", errors)

    def test_harmony_considers_existing_key(self, tmp_path, harmony_tl):
        harmony_tl.create_mode(step=2)
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,harmony,IV",
            ]
        )
        call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert harmony_tl.harmonies()[0].get_data("step") == 5

    def test_harmony_considers_key_created_on_previous_row(self, tmp_path, harmony_tl):
        data = "\n".join(
            [
                "time,harmony_or_key,symbol",
                "0,key,E",
                "0,harmony,IV",
            ]
        )
        call_patched_import_by_time_func(tmp_path, harmony_tl, data)
        assert harmony_tl.harmonies()[0].get_data("step") == 5


class TestByMeasure:
    @pytest.mark.parametrize("symbol,step,accidental,quality", TEST_HARMONY_PARAMETERS)
    def test_harmony_by_measure(
        self, tmp_path, symbol, step, accidental, quality, harmony_tl, beat_tl
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

        success, errors = call_patched_import_by_measure_func(
            tmp_path, harmony_tl, beat_tl, data
        )

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
    def test_mode_by_measure(
        self, tmp_path, symbol, step, accidental, type, harmony_tl, beat_tl
    ):
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

        success, errors = call_patched_import_by_measure_func(
            tmp_path, harmony_tl, beat_tl, data
        )

        assert not errors
        assert len(harmony_tl) == 3
        assert isinstance(harmony_tl[0], Mode)
        assert harmony_tl[0].get_data("time") == 0
        assert harmony_tl[1].get_data("time") == 20
        assert harmony_tl[2].get_data("time") == 40
        assert harmony_tl[0].get_data("step") == step
        assert harmony_tl[0].get_data("accidental") == accidental
        assert harmony_tl[0].get_data("type") == type
