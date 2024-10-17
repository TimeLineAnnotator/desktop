from tilia.ui.actions import TiliaAction


class TestValidateComponentCreation:
    def test_marker_at_same_time_fails(self, user_actions, pdf_tl):
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        assert len(pdf_tl) == 1


class TestPageTotal:
    def test_page_total_is_zero_with_invalid_pdf(self, pdf_tl):
        assert pdf_tl.get_data('page_total') == 0


class TestPageNumber:
    def test_marker_page_number_default_is_next_page(self, user_actions, tilia_state, pdf_tl):
        pdf_tl.page_total = 2
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        assert pdf_tl[1].get_data('page_number') == 2

    def test_first_marker_page_number_is_one(self, user_actions, pdf_tl):
        pdf_tl.page_total = 1
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        assert pdf_tl[0].get_data('page_number') == 1

    def test_correct_page_is_displayed(self, user_actions, tilia_state, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 11
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_created(self, user_actions, tilia_state, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        assert pdf_tlui.current_page == 2

    def test_correct_page_is_displayed_when_marker_is_deleted(self, user_actions, tilia_state, pdf_tl, pdf_tlui):
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        pdf_tl.delete_components([pdf_tl[1]])
        assert pdf_tlui.current_page == 1

    def test_correct_page_is_displayed_when_current_time_is_same_as_marker(self, user_actions, tilia_state, pdf_tlui, pdf_tl):
        pdf_tl.page_total = 2
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 20
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        assert pdf_tlui.current_page == 2

    def test_page_number_is_limited_by_page_total(self, user_actions, tilia_state, pdf_tl):
        pdf_tl.page_total = 2
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 10
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 20
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        tilia_state.current_time = 30
        user_actions.trigger(TiliaAction.PDF_MARKER_ADD)
        assert pdf_tl[-1].get_data('page_number') == 2
