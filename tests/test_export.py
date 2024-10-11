import json

from tests.conftest import parametrize_tl, parametrize_component
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tilia.requests import post, Post, Get
from tilia.timelines.base.timeline import TimelineFlag
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.components import Harmony, Mode
from tilia.timelines.hierarchy.components import Hierarchy
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


def test_export_attributes_are_present(tilia, hierarchy_tl, tmp_path):
    hierarchy_tl.create_hierarchy(start=0, end=1, level=1)

    tmp_file = tmp_path / "test.json"

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    exported_attributes = data['timelines'][0]['component_attributes'][Hierarchy.KIND.name]
    expected = [
        'start',
        'pre_start',
        'end',
        'post_end',
        'level',
        'label',
        'comments',
        'start_metric_pos',
        'end_metric_pos',
        'length',
        'length_in_measures'
    ]
    not_expected = [
        'color'
    ]

    for attr in expected:
        assert attr in exported_attributes

    for attr in not_expected:
        assert attr not in exported_attributes


@parametrize_tl
def test_appropriate_attributes_are_exported(tl, tilia, request, tmp_path):
    tl = request.getfixturevalue(tl)
    tmp_file = tmp_path / "test.json"

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    if TimelineFlag.NOT_EXPORTABLE in tl.FLAGS:
        assert not data['timelines']
    else:
        for kind in tl.component_manager.component_kinds:
            exported_attributes = data['timelines'][0]['component_attributes'][kind.name]
            comp_cls = tl.component_manager._get_component_class_by_kind(kind)
            expected_attrs = comp_cls.get_export_attributes()
            assert set(exported_attributes) == set(expected_attrs)


@parametrize_component
def test_exported_component_attributes_values_are_correct(tilia, comp, tmp_path, request):
    comp = request.getfixturevalue(comp)
    if TimelineFlag.NOT_EXPORTABLE in comp.timeline.FLAGS:
        return

    tmp_file = tmp_path / "test.json"

    post(Post.FILE_EXPORT, tmp_file)

    with open(tmp_file, encoding='utf-8') as f:
        data = json.load(f)

    exported_values = data['timelines'][0]['components'][comp.KIND.name][0]
    for i, attr in enumerate(comp.get_export_attributes()):
        comp_value = getattr(comp, attr)
        if isinstance(comp_value, tuple):
            comp_value = list(comp_value)  # JSON converts tuples to lists
        assert comp_value == exported_values[i]
