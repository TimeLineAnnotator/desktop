import pytest


from unittest.mock import MagicMock, patch
from collections import OrderedDict

from tests.mock import PatchGetMultiple
from tilia.requests import Get
from tilia.ui.windows.metadata import (
    MediaMetadataWindow,
    EditMetadataFieldsWindow,
    PERMANENT_FIELDS,
)


class TestMetadataWindow:
    @patch("tkinter.Toplevel")
    @patch("tkinter.StringVar")
    @pytest.fixture
    def metadata_window(self, tk_session):
        mediametadata_mock = OrderedDict({"field1": "a", "field2": "b", "field3": "c"})
        with PatchGetMultiple(
            "tilia.ui.windows.metadata",
            {Get.MEDIA_DURATION: 100, Get.MEDIA_PATH: ""},
        ):
            window = MediaMetadataWindow(
                parent=tk_session,
                media_metadata=mediametadata_mock,
            )

        yield window

        window.destroy()

    @patch("tkinter.Toplevel")
    @patch("tkinter.StringVar")
    @patch("tkinter.Label")
    @patch("tkinter.Text")
    def test_constructor(self, tk_session, *_):
        dummy_metadata = OrderedDict({"field1": "a", "field2": "b", "field3": "c"})

        non_editable_fields_mock = OrderedDict(
            {
                "media length": 100,
                "media path": "",
            }
        )
        with PatchGetMultiple(
            "tilia.ui.windows.metadata",
            {Get.MEDIA_DURATION: 100, Get.MEDIA_PATH: ""},
        ):
            window = MediaMetadataWindow(
                parent=tk_session,
                media_metadata=dummy_metadata,
            )

        assert list(window.fieldnames_to_widgets.keys()) == list(
            dummy_metadata.keys()
        ) + list(non_editable_fields_mock.keys())

        window.destroy()

    def test_insert_single_field(self, metadata_window):
        metadata_window.update_metadata_fields(
            ["field1", "field2", "field3", "new_field"]
        )
        metadata_window.refresh_fields()
        assert list(metadata_window.fieldnames_to_widgets) == [
            "field1",
            "field2",
            "field3",
            "new_field",
            "media length",
            "media path",
        ]

    def test_insert_multiple_fields(self, metadata_window):
        metadata_window.update_metadata_fields(
            ["field1", "field2", "field3", "field4", "field5"]
        )
        metadata_window.refresh_fields()
        assert list(metadata_window.fieldnames_to_widgets) == [
            "field1",
            "field2",
            "field3",
            "field4",
            "field5",
            "media length",
            "media path",
        ]


class TestEditMetadataFieldsWindow:
    def test_get_metadata_fields_as_str(self):
        metadata_mock = {"field1": "a", "field2": "b", "field3": "c"}

        assert (
            EditMetadataFieldsWindow.get_metadata_fields_as_str(list(metadata_mock))
            == "field1\nfield2\nfield3"
        )

    def test_get_metadata_fields_from_widget(self):
        window_mock = MagicMock()
        test_str = """
        field1
        field2
        field3
        """
        window_mock.scrolled_text.get = lambda *_: test_str

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(
            window_mock
        )

        assert metadata_fields == ["field1", "field2", "field3"] + PERMANENT_FIELDS

        test_str = """
        field1


        field2
        """

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(
            window_mock
        )

        assert metadata_fields == ["field1", "field2"] + PERMANENT_FIELDS

        test_str = r"""
        field1
        !@#$%¨&*()\/{}[]
        field2
        """

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(
            window_mock
        )

        assert (
            metadata_fields
            == ["field1", r"!@#$%¨&*()\/{}[]", "field2"] + PERMANENT_FIELDS
        )
