from pathlib import Path

from tilia.boot import get_initial_file


class TestBoot:
    def test_get_initial_file_no_file(self):
        assert get_initial_file("") == ""

    def test_get_initial_file_path_does_not_exist(self):
        assert get_initial_file("inexistent.txt") == ""

    def test_get_initial_file_path_path_with_non_tla_extension(self):
        assert get_initial_file(str(Path(__file__))) == ""

    def test_get_initial_file_path_good_path(self):
        path = str(Path(__file__).parent / "test_file.tla")
        assert Path(get_initial_file(path)) == Path(path)
