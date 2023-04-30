from tilia.ui.windows.choose import ChooseWindow


class TestChooseWindow:

    options = [
        (1, "first"),
        (2, "second"),
        (3, "third"),
        (4, "fourth"),
    ]

    def test_cancel(self):
        window = ChooseWindow("", "", [])
        window.on_cancel()
        assert window.return_value is False

    def test_destroy(self):
        window = ChooseWindow("", "", [])
        window.destroy()

        assert window.return_value is None

    def test_choose_first(self):
        window = ChooseWindow("", "", self.options)
        window.get_selected_index = lambda: 0
        window.on_ok()

        assert window.return_value == 1

    def test_choose_last(self):
        window = ChooseWindow("", "", self.options)
        window.get_selected_index = lambda: 3
        window.on_ok()

        assert window.return_value == 4
