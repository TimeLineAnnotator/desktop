from tilia.ui.windows.beat_pattern import AskBeatPattern


class TestMetadataWindow:
    def test_ask_beat_pattern_window_cancel(self, tk_session):
        window = AskBeatPattern(parent=tk_session)
        window.cancel()
        assert window.is_cancel
        assert window.input_string == ""

    def test_ask_beat_pattern_window_confirm(self, tk_session):
        window = AskBeatPattern(parent=tk_session)
        window.text.insert(1.0, "some pattern")
        window.confirm()
        assert window.input_string == "some pattern"
