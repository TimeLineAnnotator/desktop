from pathlib import Path
from tilia.dirs import clear_tmp_path
from tilia.ui import commands
from tilia.timelines.timeline_kinds import TimelineKind
from unittest.mock import patch


class TestValidateComponentCreation:
    def test_marker_at_same_time_fails(self, pdf_tlui):
        commands.execute("timeline.pdf.add")
        commands.execute("timeline.pdf.add")
        assert len(pdf_tlui) == 1


class TestPageTotal:
    def test_page_total_is_zero_with_invalid_pdf(self, pdf_tl):
        pdf_tl.path = "invalid_path"
        assert pdf_tl.get_data("page_total") == 0


class TestPageNumber:
    def test_marker_page_number_default_is_next_page(self, tilia_state, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        assert pdf_tl[1].get_data("page_number") == 2

    def test_first_marker_page_number_is_one(self, pdf_tl):
        pdf_tl.page_total = 1
        commands.execute("timeline.pdf.add")
        assert pdf_tl[0].get_data("page_number") == 1

    def test_correct_page_is_displayed(self, tilia_state, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 11
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_created(
        self, tilia_state, pdf_tlui, pdf_tl
    ):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_deleted(
        self, tilia_state, pdf_tl, pdf_tlui
    ):
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        pdf_tl.delete_components([pdf_tl[1]])
        assert pdf_tlui.current_page == 1

    def test_correct_page_is_displayed_when_current_time_is_same_as_marker(
        self, tilia_state, pdf_tlui, pdf_tl
    ):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 20
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        assert pdf_tlui.current_page == 2

    def test_page_number_is_limited_by_page_total(self, tilia_state, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 10
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 20
        commands.execute("timeline.pdf.add")
        tilia_state.current_time = 30
        commands.execute("timeline.pdf.add")
        assert pdf_tl[-1].get_data("page_number") == 2


class TestLoadPdf:
    @patch("tilia.dirs.tmp_path", Path("tmp_path"))
    def test_online_pdf(self, tls):
        tls.create_timeline(
            TimelineKind.PDF_TIMELINE,
            path="https://s9.imslp.org/files/imglnks/usimg/0/04/IMSLP228371-WIMA.53e2-W.A.Moz.Ah_vous_dirai-je-Maman.pdf",
        )

        assert tls[0].is_pdf_valid
        assert tls[0].page_total == 19
        assert not tls[0].is_local

        clear_tmp_path()

    def test_local_pdf(self, tls, resources):
        tls.create_timeline(
            TimelineKind.PDF_TIMELINE,
            path=(resources / "example_multistaff.pdf").as_posix(),
        )

        assert tls[0].is_pdf_valid
        assert tls[0].page_total == 1
        assert tls[0].is_local

    def test_non_pdf(self, tls, resources):
        tls.create_timeline(TimelineKind.PDF_TIMELINE, path="nonexistent.pdf")

        assert not tls[0].is_pdf_valid
