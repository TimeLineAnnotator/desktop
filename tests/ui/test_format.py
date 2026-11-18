import pytest

from tilia.ui.format import format_media_time, parse_media_time


class TestFormatMediaTime:
    @pytest.mark.parametrize(
        "time, expected",
        [
            pytest.param(0, "00:00.0", id="zero"),
            pytest.param(0.5, "00:00.5", id="fraction"),
            pytest.param(61.25, "01:01.2", id="minutes"),
            pytest.param(3661.5, "1:01:01.5", id="hours"),
        ],
    )
    def test_a_time_not_before_zero(self, time, expected):
        assert format_media_time(time) == expected

    @pytest.mark.parametrize(
        "time, expected",
        [
            pytest.param(-0.04, "-00:00.0", id="rounds_to_zero"),
            pytest.param(-0.5, "-00:00.5", id="fraction"),
            pytest.param(-61.25, "-01:01.2", id="minutes"),
            pytest.param(-3661.5, "-1:01:01.5", id="hours"),
        ],
    )
    def test_a_time_before_zero_has_a_minus_sign(self, time, expected):
        assert format_media_time(time) == expected

    def test_a_time_before_zero_is_shown_as_the_same_time_after_zero(self):
        assert format_media_time(-61.25) == "-" + format_media_time(61.25)

    def test_negative_zero_has_no_minus_sign(self):
        assert format_media_time(-0.0) == "00:00.0"


class TestParseMediaTimeOfATimeBeforeZero:
    # No input for a time takes one before 0, and their validators refuse a
    # minus sign. A negative time shown by format_media_time is refused, not
    # read as another time.
    @pytest.mark.parametrize("time", [-0.5, -61.25, -3661.5])
    def test_is_refused(self, time):
        assert parse_media_time(format_media_time(time)) is None


class TestParseMediaTimeDigits:
    # As the inputs' validators: \d in Qt's regular expressions is an ASCII
    # digit only.
    @pytest.mark.parametrize("text", ["٣", "١:٣٠"])
    def test_a_digit_that_is_not_ascii_is_refused(self, text):
        assert parse_media_time(text) is None
