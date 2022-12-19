import pytest

from tilia import events
from tilia.events import Event, unsubscribe_from_all
from tilia.files import TiliaFile
from tilia.globals_ import UserInterfaceKind, NATIVE_VIDEO_FORMATS, NATIVE_AUDIO_FORMATS
from tilia.main import TiLiA
from tilia.file_manager import FileManager
from tilia.player import player
from tilia.timelines.timeline_kinds import TimelineKind


# noinspection PyProtectedMember
@pytest.fixture
def tilia_mock():
    tilia_mock_ = TiLiA(ui_kind=UserInterfaceKind.MOCK)
    yield tilia_mock_
    unsubscribe_from_all(tilia_mock_._undo_manager)
    unsubscribe_from_all(tilia_mock_._player)
    tilia_mock_._player.destroy()


@pytest.fixture
def file_manager(tilia_mock):
    return FileManager(tilia_mock)


@pytest.fixture
def tlwui_builder(tilia_mock):
    # noinspection PyProtectedMember
    return tilia_mock._timeline_with_ui_builder

class TestTilia:
    def test_change_player_according_to_extension(self, tilia_mock):
        tilia_mock._change_player_according_to_extension(NATIVE_VIDEO_FORMATS[0])
        assert isinstance(tilia_mock._player, player.VlcPlayer)

        tilia_mock._change_player_according_to_extension(NATIVE_AUDIO_FORMATS[0])
        assert isinstance(tilia_mock._player, player.PygamePlayer)

        tilia_mock._change_player_according_to_extension(NATIVE_VIDEO_FORMATS[0])
        assert isinstance(tilia_mock._player, player.VlcPlayer)

        tilia_mock._change_player_according_to_extension(NATIVE_AUDIO_FORMATS[0])
        assert isinstance(tilia_mock._player, player.PygamePlayer)



class TestFileManager:
    def test_constructor(self, tilia_mock):
        FileManager(tilia_mock)

    def test_open(self, file_manager):

        file_manager._app.ui.get_file_open_path = lambda: "test_file.tla"
        file_manager.ask_save_if_necessary = lambda: True

        file_manager.open()

    def test_on_metadata_new_fields(self, tilia_mock):
        new_metadata_fields = ['test_field1', 'test_field2']
        events.post(Event.METADATA_NEW_FIELDS, new_metadata_fields)

        assert list(tilia_mock.media_metadata) == new_metadata_fields

    def test_on_metadata_field_edited(self, tilia_mock):
        edited_field = 'title'
        new_value = 'test title'
        events.post(Event.METADATA_FIELD_EDITED, edited_field, new_value)

        assert tilia_mock.media_metadata[edited_field] == new_value

    def test_load_custom_metadata_fields(self, tilia_mock, file_manager):
        file_manager._open_file_by_path("test_metadata_custom_fields.tla")

        assert list(file_manager._file.media_metadata.items()) == [
            ('test_field1', 'a'),
            ('test_field2', 'b'),
            ('test_field3', 'c')
        ]

    def test_is_file_modified(self, tilia_mock, file_manager):

        empty_file = TiliaFile()
        empty_file_save_params = {}
        for attr in FileManager.FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION:
            empty_file_save_params[attr] = getattr(empty_file, attr)
        file_manager._get_save_parameters = lambda: empty_file_save_params

        assert not file_manager.is_file_modified


        file_manager._get_save_parameters = lambda: modified_save_params

        import copy
        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params['timelines'] = {
            '0': {'kind': 'SLIDER_TIMELINE', 'display_position': 0, 'is_visible': True, 'height': 10},
            '1': {
                'kind': 'HIERARCHY_TIMELINE',
                'display_position': 0,
                'height': 10,
                'is_visible': True,
                'name': 'test',
                'components': {}
            }
        }

        assert file_manager.is_file_modified

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params['media_metadata']['title'] = 'modified title'
        assert file_manager.is_file_modified

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params['media_metadata'].pop('title')
        assert file_manager.is_file_modified

        modified_save_params = copy.deepcopy(empty_file_save_params)
        modified_save_params['media_path'] = 'modified path'
        assert file_manager.is_file_modified


class TestTimelineWithUIBuilder:
    def test_create_slider_timeline_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.SLIDER_TIMELINE, name="test")

    def test_create_hierarchy_timelin_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test")

