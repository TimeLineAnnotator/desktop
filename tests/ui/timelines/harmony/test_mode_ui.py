from unittest.mock import patch


class TestRightClick:
    def test_right_click(self, harmony_tlui):
        _, hui = harmony_tlui.create_mode()
        with patch('tilia.ui.timelines.harmony.context_menu.ModeContextMenu.exec') as exec_mock:
            hui.on_right_click(0, 0, None)

        exec_mock.assert_called_once()
