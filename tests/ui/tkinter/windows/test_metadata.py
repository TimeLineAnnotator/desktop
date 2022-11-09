import pytest


from unittest.mock import MagicMock, patch
from collections import OrderedDict
import tkinter as tk

from tilia.ui.tkinter.windows.metadata import MetadataWindow, EditMetadataFieldsWindow, PERMANENT_FIELDS


class TestMetadataWindow:

    @patch('tkinter.Toplevel')
    @patch('tkinter.StringVar')
    @pytest.fixture
    def metadata_window(self):
        mediametadata_mock = OrderedDict(
            {
                'field1': 'a',
                'field2': 'b',
                'field3': 'c'
            }
        )
        _metadata_window = MetadataWindow(app_ui=None, media_metadata=mediametadata_mock, non_editable_fields=OrderedDict())
        yield _metadata_window
        _metadata_window.destroy()


    @patch('tkinter.Toplevel')
    @patch('tkinter.StringVar')
    @patch('tkinter.Label')
    @patch('tkinter.Text')
    def test_constructor(self, *_):
        mediametadata_mock = OrderedDict(
            {
                'field1': 'a',
                'field2': 'b',
                'field3': 'c'
            }
        )

        non_editable_fields_mock = OrderedDict(
            {
                'noedit1': 'a',
                'noedit2': 'b',
            }
        )
        metadata_window = MetadataWindow(app_ui=None, media_metadata=mediametadata_mock, non_editable_fields=non_editable_fields_mock)

        assert list(metadata_window.fieldnames_to_widgets.keys()) == list(mediametadata_mock.keys()) + list(non_editable_fields_mock.keys())

        metadata_window.destroy()

    def test_update_values(self, metadata_window):
        test_value1 = ['new_field']
        test_value2 = ['field1', 'field3']

        metadata_window.update_metadata_fields(test_value1)
        assert list(metadata_window._metadata) == test_value1

        metadata_window.update_metadata_fields(test_value2)
        assert list(metadata_window._metadata) == test_value2

    def test_refresh_fields(self, metadata_window):
        test_value1 = ['new_field']
        test_value2 = ['field1', 'field3']

        metadata_window.update_metadata_fields(test_value1)
        metadata_window.refresh_fields()
        assert list(metadata_window.fieldnames_to_widgets) == test_value1

        metadata_window.update_metadata_fields(test_value2)
        metadata_window.refresh_fields()
        assert list(metadata_window.fieldnames_to_widgets) == test_value2


class TestEditMetadataFieldsWindow:
    def test_get_metadata_fields_as_str(self):
        metadata_mock = {
            'field1': 'a',
            'field2': 'b',
            'field3': 'c'
        }

        assert EditMetadataFieldsWindow.get_metadata_fields_as_str(list(metadata_mock)) == 'field1\nfield2\nfield3'



    def test_get_metadata_fields_from_widget(self):
        window_mock = MagicMock()
        test_str = """
        field1
        field2
        field3
        """
        window_mock.scrolled_text.get = lambda *_: test_str

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(window_mock)

        assert metadata_fields == ['field1', 'field2', 'field3'] + PERMANENT_FIELDS

        test_str = """
        field1
                
                
        field2
        """

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(window_mock)

        assert metadata_fields == ['field1', 'field2'] + PERMANENT_FIELDS

        test_str = """
        field1          
        !@#$%¨&*()\/{}[]         
        field2
        """

        metadata_fields = EditMetadataFieldsWindow.get_metadata_fields_from_widget(window_mock)

        assert metadata_fields == ['field1', '!@#$%¨&*()\/{}[]', 'field2'] + PERMANENT_FIELDS
