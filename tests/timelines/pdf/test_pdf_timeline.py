from tilia.ui import commands


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
    def test_marker_page_number_default_is_next_page(self, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        commands.execute("media.seek", 10)
        commands.execute("timeline.pdf.add")
        assert pdf_tl[1].get_data("page_number") == 2

    def test_first_marker_page_number_is_one(self, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 1
        commands.execute("timeline.pdf.add")
        assert pdf_tl[0].get_data("page_number") == 1

    def test_correct_page_is_displayed(self, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        commands.execute("media.seek", 10)
        commands.execute("timeline.pdf.add")
        commands.execute("media.seek", 11)
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_created(self, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add")
        commands.execute("media.seek", 10)
        commands.execute("timeline.pdf.add")
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_deleted(self, pdf_tl, pdf_tlui):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add", time=0, page_number=1)
        commands.execute("timeline.pdf.add", time=10, page_number=2)
        commands.execute("media.seek", time=10)
        assert pdf_tlui.current_page == 2
        pdf_tl.delete_components([pdf_tl[1]])
        assert pdf_tlui.current_page == 1

    def test_correct_page_is_displayed_when_current_time_is_same_as_marker(
        self, pdf_tlui, pdf_tl
    ):
        pdf_tl.page_total = 2
        commands.execute("timeline.pdf.add", time=0)
        commands.execute("timeline.pdf.add", time=10)
        commands.execute("timeline.pdf.add", time=20)
        commands.execute("media.seek", 10)
        assert pdf_tlui.current_page == 2

    def test_page_number_for_new_marker_is_capped_at_page_total(self, pdf_tl, pdf_tlui):
        pdf_tl.page_total = 2
        for time in range(10):
            commands.execute("timeline.pdf.add", time=time)
        assert pdf_tl[-1].get_data("page_number") == 2
