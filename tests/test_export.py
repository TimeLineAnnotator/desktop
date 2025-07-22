import json
import pytest
from PIL import Image

from tests.conftest import parametrize_component
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve, patch_ask_for_string_dialog, patch_file_dialog
from tests.utils import get_tmp_file_with_dummy_timeline
from tilia.requests import post, Post, Get, get
from tilia.settings import settings
from tilia.timelines.base.timeline import TimelineFlag
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.dialogs.resize_rect import ResizeRect


class TestExportJSON:
    def _trigger_export_action(self, user_actions, path):
        with Serve(Get.FROM_USER_EXPORT_PATH, (True, path)):
            user_actions.trigger("file_export_json")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return data

    def test_timelines_attributes_are_exported(
        self, tilia, marker_tlui, user_actions, tmp_path, use_test_settings
    ):
        # Marker timeline is chosen as an example. Ideally this should be parametrized for all timelines kinds.
        tl_name = "my name"
        with patch_ask_for_string_dialog(True, tl_name):
            user_actions.trigger("timeline_name_set")

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(user_actions, tmp_file)

        timeline_data = data["timelines"][0]
        assert "hash" not in timeline_data
        assert timeline_data["ordinal"] == 1
        assert timeline_data["name"] == tl_name
        assert timeline_data["is_visible"] is True
        assert timeline_data["height"] == settings.get(
            "marker_timeline", "default_height"
        )
        assert timeline_data["kind"] == TimelineKind.MARKER_TIMELINE.name
        assert timeline_data["components"] == []

    def test_timeline_not_exportable_attributes_are_not_exported(
        self, tilia, harmony_tlui, user_actions, tmp_path
    ):
        # Harmony timeline is chosen as an example. Ideally this should be parametrized for all timelines kinds that have not exportable attributes.
        tmp_file = tmp_path / "test.json"
        data = self._trigger_export_action(user_actions, tmp_file)

        timeline_data = data["timelines"][0]
        for attr in HarmonyTimeline.NOT_EXPORTABLE_ATTRS:
            assert attr not in timeline_data

    def test_not_exportble_timelines_are_not_exported(
        self, tilia, marker_tlui, audiowave_tlui, user_actions, tmp_path
    ):
        # Audiowave timeline is chosen as an example. Ideally this should be parametrized for all non-exportable timeline types.
        tmp_file = tmp_path / "test.json"
        data = self._trigger_export_action(user_actions, tmp_file)

        assert len(data["timelines"]) == 1

    def test_export_timelines(
        self, tilia, marker_tlui, harmony_tlui, user_actions, tilia_state, tmp_path
    ):
        for i in range(5):
            tilia_state.current_time = i
            user_actions.trigger("marker_add")

        harmony_tlui.create_harmony(0)
        harmony_tlui.create_mode(0)

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(user_actions, tmp_file)

        assert len(data["timelines"]) == 2
        assert data["timelines"][0]["kind"] == "MARKER_TIMELINE"
        assert data["timelines"][1]["kind"] == "HARMONY_TIMELINE"

        # check marker timeline components
        components = data["timelines"][0]["components"]
        assert len(components) == 5
        assert [c["kind"] for c in components] == ["MARKER"] * 5
        assert [c["time"] for c in components] == [0, 1, 2, 3, 4]

        # check harmony timeline components
        components = data["timelines"][1]["components"]
        assert len(components) == 2
        assert [c["kind"] for c in components] == ["HARMONY", "MODE"]
        assert [c["time"] for c in components] == [0, 0]

    def test_export_has_media_path(self, tilia, user_actions, tmp_path):
        post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(user_actions, tmp_file)

        assert data["media_path"] == EXAMPLE_MEDIA_PATH

    def test_export_has_media_metadata(self, tilia, user_actions, tmp_path):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "Test Title")

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(user_actions, tmp_file)

        assert data["media_metadata"]["title"] == "Test Title"

    def test_export_without_path(self, tilia, user_actions, tmp_path):
        tmp_file = tmp_path / "test.json"

        with Serve(Get.FROM_USER_EXPORT_PATH, (True, tmp_file)):
            post(Post.FILE_EXPORT)

        assert tmp_file.exists()

    @parametrize_component
    def test_exported_component_attributes_values_are_correct(
        self, tilia, user_actions, comp, tmp_path, request
    ):
        comp = request.getfixturevalue(comp)
        if TimelineFlag.NOT_EXPORTABLE in comp.timeline.FLAGS:
            return

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(user_actions, tmp_file)

        exported_component = data["timelines"][0]["components"][0]

        for attr in comp.get_export_attributes():
            comp_value = getattr(comp, attr)
            if isinstance(comp_value, tuple):
                comp_value = list(comp_value)  # JSON converts tuples to lists
            assert comp_value == exported_component[attr]


class TestExportImage:
    def _get_sample_file(self, tmp_path):
        return get_tmp_file_with_dummy_timeline(tmp_path).__str__()

    @pytest.mark.parametrize("scale_factor", [1.0, 0.5, 2.0])
    def test_image_export(
        self, qtui, monkeypatch, tmp_path, user_actions, scale_factor
    ):
        image_path = tmp_path / "tl_image.jpg"
        with patch_file_dialog(True, [self._get_sample_file(tmp_path)]):
            user_actions.trigger("file_open")

        scene = get(Get.MAIN_WINDOW).centralWidget().scene()
        original_width = scene.sceneRect().width()
        original_height = scene.sceneRect().height()

        new_width = original_width * scale_factor

        monkeypatch.setattr(ResizeRect, "new_size", lambda *_: [True, new_width])

        with Serve(Get.FROM_USER_EXPORT_PATH, (True, image_path)):
            user_actions.trigger("file_export_img")

        with Image.open(image_path) as img:
            assert img.size[0] == new_width
            assert img.size[1] == original_height

        assert scene.sceneRect().width() == original_width
        assert scene.sceneRect().height() == original_height

    def test_image_export_resize_rejected(
        self, qtui, user_actions, monkeypatch, tmp_path
    ):
        image_path = tmp_path / "tl_image.jpg"
        with patch_file_dialog(True, [self._get_sample_file(tmp_path)]):
            user_actions.trigger("file_open")

        monkeypatch.setattr(ResizeRect, "new_size", lambda *_: [False, None])

        with Serve(Get.FROM_USER_EXPORT_PATH, (True, image_path)):
            user_actions.trigger("file_export_img")

        assert not image_path.exists()
