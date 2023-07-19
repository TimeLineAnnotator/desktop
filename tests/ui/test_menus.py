from pathlib import Path
from unittest.mock import patch

import pytest

from tests.mock import PatchGet
from tilia import settings
from tilia.requests import Get


class TestFileMenu:
    @pytest.fixture
    def file_menu(self, tilia, tkui):
        return tkui._menus.file_menu

    def test_file_menu_new(self, tilia, file_menu):
        file_menu.invoke(0)
        tilia.clear_app()

    def test_file_menu_open(self, tilia, file_menu):
        test_file_path = Path(__file__).parents[1] / "file" / "test_file.tla"
        with patch("tkinter.filedialog.askopenfilename", return_value=test_file_path):
            file_menu.invoke(1)
        tilia.clear_app()  # tilia fixture will only call cleanup after module is done

    def test_file_menu_save(self, file_menu, tmp_path):
        with PatchGet(
            "tilia.file.file_manager",
            Get.APP_STATE,
            {"file_path": str(tmp_path / "test_file.tla")},
        ):
            file_menu.invoke(2)

    def test_file_menu_save_as(self, file_menu, tmp_path):
        with patch(
            "tkinter.filedialog.asksaveasfilename",
            return_value=str(tmp_path / "test_file.tla"),
        ):
            file_menu.invoke(3)

    def test_file_menu_load_audio_file(self, file_menu):
        test_file_path = Path(__file__).parents[1] / "player" / "test.ogg"
        with patch("tkinter.filedialog.askopenfilename", return_value=test_file_path):
            file_menu.invoke(4)

    def test_file_menu_load_video_file(self, file_menu):
        test_file_path = Path(__file__).parents[1] / "player" / "test.mp4"
        with patch("tkinter.filedialog.askopenfilename", return_value=test_file_path):
            file_menu.invoke(4)

    def test_file_menu_media_metadata(self, file_menu):
        file_menu.invoke(5)

    def test_file_menu_settings(self, file_menu):
        with patch("tilia.settings.open_with_os") as open_with_os_mock:
            file_menu.invoke(6)
            assert open_with_os_mock.called_with(settings._settings_path)
