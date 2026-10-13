import pytest

from tilia_core import rules

OK = (True, "")
MEDIA = 60.0


class TestPoint:
    @pytest.mark.parametrize("time", [0.0, 30.0, MEDIA])
    def test_a_time_from_0_to_the_media_length(self, time):
        assert rules.point(time, MEDIA, set(), kind="marker") == OK

    def test_a_time_beyond_the_media_length(self):
        assert rules.point(60.5, MEDIA, set(), kind="marker") == (
            False,
            "Time '01:00.5' is bigger than media time '01:00.0'",
        )

    def test_times_of_an_hour_or_more_show_hours(self):
        assert rules.point(3725.0, 3600.0, set(), kind="marker") == (
            False,
            "Time '1:02:05.0' is bigger than media time '1:00:00.0'",
        )

    def test_a_negative_time(self):
        # TiLiA's format_media_time, as it is, shows -1 second as 59:59.0.
        assert rules.point(-1.0, MEDIA, set(), kind="marker") == (
            False,
            "Time can't be negative. Got '59:59.0'",
        )

    @pytest.mark.parametrize(
        "kind, name",
        [
            ("marker", "marker"),
            ("harmony", "harmony"),
            ("mode", "mode"),
            ("beat", "beat"),
            ("pdf_marker", "PDF page marker"),
        ],
    )
    def test_a_time_another_component_has(self, kind, name):
        assert rules.point(1.0, MEDIA, {0.0, 1.0}, kind=kind) == (
            False,
            f"There is already a {name} component at the selected position.",
        )

    @pytest.mark.parametrize("time", [0.0, MEDIA])
    def test_a_time_another_component_has_at_the_edges(self, time):
        assert rules.point(time, MEDIA, {time}, kind="marker")[0] is False

    def test_bounds_are_checked_before_other_components(self):
        assert rules.point(61.0, MEDIA, {61.0}, kind="marker") == (
            False,
            "Time '01:01.0' is bigger than media time '01:00.0'",
        )

    def test_media_length_given_as_an_integer(self):
        assert rules.point(61.0, 60, set(), kind="marker") == (
            False,
            "Time '01:01.0' is bigger than media time '01:00.0'",
        )


class TestSegment:
    @pytest.mark.parametrize("start, end", [(0.0, 1.0), (1.0, MEDIA), (0.0, MEDIA)])
    def test_within_the_media_length(self, start, end):
        assert rules.segment(start, end, (start, end, 1), set(), MEDIA) == OK

    def test_a_start_beyond_the_media_length(self):
        assert rules.segment(61.0, 62.0, (61.0, 62.0, 1), set(), MEDIA) == (
            False,
            "Start time '61.0' is bigger than media time '60.0'",
        )

    def test_an_end_beyond_the_media_length(self):
        assert rules.segment(1.0, 61.0, (1.0, 61.0, 1), set(), MEDIA) == (
            False,
            "End time '61.0' is bigger than media time '60.0'",
        )

    @pytest.mark.parametrize("end", [2.0, 1.0])
    def test_an_end_not_after_its_start(self, end):
        assert rules.segment(2.0, end, (2.0, end, 1), set(), MEDIA) == (
            False,
            f"End time '{end}' should be bigger than start time '2.0'",
        )

    def test_the_position_of_another_component(self):
        existing = {(0.0, 1.0, 1), (1.0, 2.0, 1)}

        assert rules.segment(1.0, 2.0, (1.0, 2.0, 1), existing, MEDIA) == (
            False,
            "There is already a hierarchy component at the selected position.",
        )

    def test_the_same_times_at_another_level(self):
        assert rules.segment(1.0, 2.0, (1.0, 2.0, 2), {(1.0, 2.0, 1)}, MEDIA) == OK

    def test_times_are_checked_before_other_components(self):
        position = (2.0, 1.0, 1)

        assert rules.segment(2.0, 1.0, position, {position}, MEDIA) == (
            False,
            "End time '1.0' should be bigger than start time '2.0'",
        )

    def test_numbers_given_as_integers_read_as_tilias_floats(self):
        assert rules.segment(61, 62, (61, 62, 1), set(), 60) == (
            False,
            "Start time '61.0' is bigger than media time '60.0'",
        )


class TestRange:
    ROWS = ["Ab12Cd", "Ef34Gh"]

    def check(self, start=1.0, end=2.0, row_id="Ab12Cd", pre_start=None, post_end=None):
        return rules.range_(start, end, row_id, self.ROWS, pre_start, post_end, MEDIA)

    def test_a_range_in_a_row(self):
        assert self.check() == OK

    @pytest.mark.parametrize(
        "start, end, pre_start, post_end",
        [(0.0, MEDIA, None, None), (1.0, 2.0, 0.0, MEDIA), (0.0, MEDIA, 0.0, MEDIA)],
    )
    def test_the_edges(self, start, end, pre_start, post_end):
        assert self.check(start, end, pre_start=pre_start, post_end=post_end) == OK

    @pytest.mark.parametrize("row_id", ["", None, "Zz99Zz"])
    def test_a_row_the_timeline_doesnt_have(self, row_id):
        assert self.check(row_id=row_id) == (False, "Invalid row ID.")

    @pytest.mark.parametrize("end", [1.0, 0.5])
    def test_an_end_not_after_its_start(self, end):
        assert self.check(1.0, end) == (False, "Start time must be before end time.")

    @pytest.mark.parametrize("start, end", [(-0.5, 2.0), (1.0, 60.5)])
    def test_outside_the_media(self, start, end):
        assert self.check(start, end) == (False, "Range is outside media bounds.")

    def test_a_pre_start_below_0(self):
        assert self.check(pre_start=-0.5) == (
            False,
            "pre_start is outside media bounds.",
        )

    def test_a_post_end_beyond_the_media_length(self):
        assert self.check(post_end=60.5) == (
            False,
            "post_end is outside media bounds.",
        )

    def test_the_row_is_checked_first(self):
        assert self.check(2.0, 1.0, row_id="Zz99Zz") == (False, "Invalid row ID.")


class TestPage:
    @pytest.mark.parametrize("page_number", [1, 2, 3])
    def test_a_page_the_pdf_has(self, page_number):
        assert rules.page(page_number, 3) == OK

    @pytest.mark.parametrize(
        "page_number, page_total", [(0, 3), (4, 3), (-1, 3), (1, 0)]
    )
    def test_a_page_the_pdf_doesnt_have(self, page_number, page_total):
        assert rules.page(page_number, page_total) == (
            False,
            "The PDF has no page with that number.",
        )
