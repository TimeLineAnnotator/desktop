from unittest.mock import patch
from tests.mock import PatchGet
from tilia.file.media_metadata import MediaMetadata
from tilia.requests.get import Get

from tilia.ui.cli.metadata.show import show


class TestShowMetadata:
    def test_show_metadata_empty_metadata(self):
        with patch("tilia.ui.cli.io.print") as print_mock:
            with PatchGet(
                "tilia.ui.cli.metadata.show", Get.MEDIA_METADATA, MediaMetadata()
            ):
                show(None)
                output = print_mock.call_args[0][0]

        assert "Title" in output
        assert "Untitled" in output

    def test_show_metadata(self):
        metadata = MediaMetadata.from_dict(
            {
                "title": "Test no.1 in Py Minor",
                "artist": "T.L.A",
                "year": 2023,
            }
        )

        with patch("tilia.ui.cli.io.print") as print_mock:
            with PatchGet("tilia.ui.cli.metadata.show", Get.MEDIA_METADATA, metadata):
                show(None)
                output = print_mock.call_args[0][0]

        assert "Title" in output
        assert "Artist" in output
        assert "Year" in output
        assert "Test no.1 in Py Minor" in output
        assert "T.L.A" in output
        assert "2023" in output
