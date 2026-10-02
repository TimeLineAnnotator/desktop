import pytest

from tilia.timelines.beat.pattern import (
    MAX_BARS,
    BarRun,
    ParseStatus,
    group_runs,
    parse,
)


class TestComplete:
    @pytest.mark.parametrize(
        "text, bars",
        [
            ("4", [4]),
            ("4 4 3", [4, 4, 3]),
            ("  4\t4\n3  ", [4, 4, 3]),
            ("10[4] 3 15[4]", [4] * 10 + [3] + [4] * 15),
            ("2[4 3[3]]", [4, 3, 3, 3, 4, 3, 3, 3]),
            ("2[[4] 3[3]]", [4, 3, 3, 3, 4, 3, 3, 3]),
            ("[4 3]", [4, 3]),
            ("1[4]", [4]),
            ("3 [2]", [2, 2, 2]),
            ("2[3]4", [3, 3, 4]),
            ("12", [12]),
            ("007", [7]),
        ],
    )
    def test_expands(self, text, bars):
        result = parse(text)
        assert result.status == ParseStatus.COMPLETE
        assert result.is_complete
        assert result.bars == bars
        assert result.error == ""

    def test_max_bars_is_allowed(self):
        assert parse(f"{MAX_BARS}[1]").bars == [1] * MAX_BARS


class TestIncomplete:
    @pytest.mark.parametrize(
        "text, position",
        [
            ("", 0),
            ("   ", 0),
            ("10[", 2),
            ("2[4 3", 1),
            ("2[4 3[3]", 1),
            ("2[4 3[3", 5),
        ],
    )
    def test_incomplete(self, text, position):
        result = parse(text)
        assert result.status == ParseStatus.INCOMPLETE
        assert not result.is_complete
        assert result.bars == []
        assert result.error
        assert result.position == position


class TestInvalid:
    @pytest.mark.parametrize(
        "text, position, message",
        [
            ("4 ]", 2, "Unmatched ']'."),
            ("2[4]]", 4, "Unmatched ']'."),
            ("4 a", 2, "Unexpected 'a'."),
            ("4, 4", 1, "Unexpected ','."),
            ("-4", 0, "Unexpected '-'."),
            ("0", 0, "Bar lengths must be at least 1."),
            ("4 0", 2, "Bar lengths must be at least 1."),
            ("0[4]", 0, "Repeat count must be at least 1."),
            ("2[]", 1, "Empty group '[]'."),
            ("2[ ]", 1, "Empty group '[]'."),
        ],
    )
    def test_invalid(self, text, position, message):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert result.bars == []
        assert result.error == message
        assert result.position == position

    @pytest.mark.parametrize(
        "text",
        [f"{MAX_BARS + 1}[1]", "999999999[999999999[4]]", f"{MAX_BARS}[1] 1"],
    )
    def test_too_many_bars(self, text):
        result = parse(text)
        assert result.status == ParseStatus.INVALID
        assert "more than" in result.error


class TestGroupRuns:
    def test_empty(self):
        assert group_runs([]) == []

    def test_groups_consecutive_equal_bars(self):
        assert group_runs([4] * 10 + [3] + [4] * 15) == [
            BarRun(0, 10, 4),
            BarRun(10, 1, 3),
            BarRun(11, 15, 4),
        ]

    def test_does_not_merge_non_consecutive_bars(self):
        assert group_runs([4, 3, 4]) == [
            BarRun(0, 1, 4),
            BarRun(1, 1, 3),
            BarRun(2, 1, 4),
        ]
