import json

from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tilia.requests import post, Post, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.marker.components import Marker
from tilia.ui.actions import TiliaAction


def test_export_timelines(tilia, marker_tlui, harmony_tlui, actions, tilia_state, tmp_path):
    for i in range(5):
        tilia_state.current_time = i
        actions.trigger(TiliaAction.MARKER_ADD)

    harmony_tlui.create_harmony(0)
    harmony_tlui.create_mode(0)

    tmp_file = tmp_path / 'test.json'

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    assert len(data['timelines']) == 2
    assert data['timelines'][0]['kind'] == 'MARKER_TIMELINE'
    assert data['timelines'][1]['kind'] == 'HARMONY_TIMELINE'

    # check marker timeline components
    assert data['timelines'][0]['component_kinds'] == [Marker.KIND.name]
    assert data['timelines'][0]['component_attributes'][ComponentKind.MARKER.name] == Marker.SERIALIZABLE_BY_VALUE
    assert len(data['timelines'][0]['components'][ComponentKind.MARKER.name]) == 5

    # check harmony timeline components
    assert Harmony.KIND.name in data['timelines'][1]['component_kinds']
    assert Mode.KIND.name in data['timelines'][1]['component_kinds']
    assert data['timelines'][1]['component_attributes'] == {
        'HARMONY': Harmony.SERIALIZABLE_BY_VALUE,
        'MODE': Mode.SERIALIZABLE_BY_VALUE
    }
    assert len(data['timelines'][1]['components'][ComponentKind.HARMONY.name]) == 1
    assert len(data['timelines'][1]['components'][ComponentKind.MODE.name]) == 1


def test_export_has_media_path(tilia, tmp_path):
    post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)

    tmp_file = tmp_path / 'test.json'

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    assert data['media_path'] == EXAMPLE_MEDIA_PATH


def test_export_has_media_metadata(tilia, tmp_path):
    post(Post.MEDIA_METADATA_FIELD_SET, 'title', 'Test Title')

    tmp_file = tmp_path / 'test.json'

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    assert data['media_metadata']['title'] == 'Test Title'


def test_export_without_path(tilia, tmp_path):
    tmp_file = tmp_path / 'test.json'

    with Serve(Get.FROM_USER_EXPORT_PATH, (True, tmp_file)):
        post(Post.FILE_EXPORT)

    assert tmp_file.exists()
