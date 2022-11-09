import pytest

from tilia import events
from tilia.events import EventName
from tilia.globals_ import UserInterfaceKind, NATIVE_VIDEO_FORMATS, NATIVE_AUDIO_FORMATS
from tilia.main import TiLiA, FileManager
from tilia.player import player
from tilia.timelines.timeline_kinds import TimelineKind


# noinspection PyProtectedMember
@pytest.fixture
def tilia_mock():
    tilia_mock_ = TiLiA(ui_kind=UserInterfaceKind.MOCK)
    yield tilia_mock_
    tilia_mock_._undo_manager.unsubscribe_from_all()
    tilia_mock_._player.unsubscribe_from_all()


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

    def test_open(self, monkeypatch, file_manager):

        file_manager._app.ui.get_file_open_path.return_value = (
            "test_file.tla"
        )
        file_manager.open()

    def test_on_metadata_new_fields(self, tilia_mock):
        new_metadata_fields = ['test_field1', 'test_field2']
        events.post(EventName.METADATA_NEW_FIELDS, new_metadata_fields)

        assert list(tilia_mock.media_metadata) == new_metadata_fields

    def test_on_metadata_field_edited(self, tilia_mock):
        edited_field = 'title'
        new_value = 'test title'
        events.post(EventName.METADATA_FIELD_EDITED, edited_field, new_value)

        assert tilia_mock.media_metadata[edited_field] == new_value

    def test_load_custom_metadata_fields(self, tilia_mock, file_manager):
        file_manager._open_file_by_path("test_metadata_custom_fields.tla")

        assert list(file_manager._file.media_metadata.items()) == [
            ('test_field1', 'a'),
            ('test_field2', 'b'),
            ('test_field3', 'c')
        ]



class TestTimelineWithUIBuilder:
    def test_create_slider_timeline_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.SLIDER_TIMELINE, name="test")

    def test_create_hierarchy_timelin_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test")

