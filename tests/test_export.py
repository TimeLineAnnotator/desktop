import json

import pytest
from PIL import Image

from tests.conftest import parametrize_component
from tests.constants import EXAMPLE_MEDIA_PATH
from tests.mock import Serve
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.base.timeline import TimelineFlag
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.ui import commands
from tilia.ui.dialogs.resize_rect import ResizeRect


class TestExportJSON:
    def _trigger_export_action(self, path):
        commands.execute("file.export.json", path)

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return data

    def test_timelines_attributes_are_exported(
        self, tilia, marker_tlui, tmp_path, use_test_settings
    ):
        # Marker timeline is chosen as an example. Ideally this should be parametrized for all timelines kinds.
        tl_name = "my name"
        commands.execute("timeline.set_name", marker_tlui, name=tl_name)

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(tmp_file)

        timeline_data = data["timelines"][0]
        assert "hash" not in timeline_data
        assert timeline_data["ordinal"] == 1
        assert timeline_data["name"] == tl_name
        assert timeline_data["is_visible"] is True
        assert timeline_data["height"] == settings.get(
            "marker_timeline", "default_height"
        )
        assert timeline_data["kind"] == "Marker"
        assert timeline_data["components"] == []

    def test_timeline_not_exportable_attributes_are_not_exported(
        self, tilia, harmony_tlui, tmp_path
    ):
        # Harmony timeline is chosen as an example. Ideally this should be parametrized for all timelines kinds that have not exportable attributes.
        tmp_file = tmp_path / "test.json"
        data = self._trigger_export_action(tmp_file)

        timeline_data = data["timelines"][0]
        for attr in HarmonyTimeline.NOT_EXPORTABLE_ATTRS:
            assert attr not in timeline_data

    def test_not_exportble_timelines_are_not_exported(
        self, tilia, marker_tlui, audiowave_tlui, tmp_path
    ):
        # Audiowave timeline is chosen as an example. Ideally this should be parametrized for all non-exportable timeline types.
        tmp_file = tmp_path / "test.json"
        data = self._trigger_export_action(tmp_file)

        assert len(data["timelines"]) == 1

    def test_export_timelines(self, tilia, marker_tlui, harmony_tlui, tmp_path):
        for i in range(5):
            commands.execute("timeline.marker.add", time=i)

        harmony_tlui.create_harmony(0)
        harmony_tlui.create_mode(0)

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(tmp_file)

        assert len(data["timelines"]) == 2
        assert data["timelines"][0]["kind"] == "Marker"
        assert data["timelines"][1]["kind"] == "Harmony"

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

    def test_export_has_media_path(self, tilia, tmp_path):
        post(Post.APP_MEDIA_LOAD, EXAMPLE_MEDIA_PATH)

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(tmp_file)

        assert data["media_path"] == EXAMPLE_MEDIA_PATH

    def test_export_has_media_metadata(self, tilia, tmp_path):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", "Test Title")

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(tmp_file)

        assert data["media_metadata"]["title"] == "Test Title"

    def test_export_without_path(self, tilia, tmp_path):
        tmp_file = tmp_path / "test.json"

        with Serve(Get.FROM_USER_EXPORT_PATH, (True, tmp_file)):
            commands.execute("file.export.json")

        assert tmp_file.exists()

    @parametrize_component
    def test_exported_component_attributes_values_are_correct(
        self,
        tilia,
        comp,
        tmp_path,
        request,
        tluis,  # tluis ensures qtui is listening before getfixturevalue triggers timeline creation
    ):
        comp = request.getfixturevalue(comp)
        if TimelineFlag.NOT_EXPORTABLE in comp.timeline.FLAGS:
            return

        tmp_file = tmp_path / "test.json"

        data = self._trigger_export_action(tmp_file)

        exported_component = data["timelines"][0]["components"][0]

        for attr in comp.get_export_attributes():
            comp_value = getattr(comp, attr)
            if isinstance(comp_value, tuple):
                comp_value = list(comp_value)  # JSON converts tuples to lists
            assert comp_value == exported_component[attr]

    def test_hierarchy_export_has_neither_formal_type_nor_formal_function(
        self, tilia, hierarchy_tlui, tmp_path
    ):
        commands.execute(
            "timeline.hierarchy.add",
            start=0,
            end=1,
            level=1,
            label="exported",
            formal_type="sonata",
            formal_function="opening",
        )

        data = self._trigger_export_action(tmp_path / "test.json")

        exported_component = data["timelines"][0]["components"][0]
        assert exported_component["label"] == "exported"
        assert "formal_type" not in exported_component
        assert "formal_function" not in exported_component


class TestExportedPositions:
    """A component's measure and beat are the core's position on the time map, as
    TiLiA shows them (FR-009, FR-044)."""

    @staticmethod
    def export(tmp_path):
        path = tmp_path / "test.json"
        commands.execute("file.export.json", path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            timeline["kind"]: timeline["components"] for timeline in data["timelines"]
        }

    @staticmethod
    def add_beats(beat_tl, times):
        for time in times:
            beat_tl.create_component(ComponentKind.BEAT, float(time))

    def test_a_marker(self, tilia, beat_tl, marker_tl, tmp_path):
        self.add_beats(beat_tl, range(20))
        marker_tl.create_component(ComponentKind.MARKER, 12.5)
        marker_tl.create_component(ComponentKind.MARKER, 13.0)

        markers = self.export(tmp_path)["Marker"]

        assert [(m["measure"], m["beat"]) for m in markers] == [(4, 1.5), (4, 2)]

    def test_a_hierarchy(self, tilia, beat_tl, hierarchy_tl, tmp_path):
        self.add_beats(beat_tl, range(20))
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 12.5, 18.0, 1)

        (hierarchy,) = self.export(tmp_path)["Hierarchy"]

        assert (hierarchy["start_measure"], hierarchy["start_beat"]) == (4, 1.5)
        assert (hierarchy["end_measure"], hierarchy["end_beat"]) == (5, 3)
        assert hierarchy["length_in_measures"] == [1, 1.5]

    def test_an_end_off_the_map(self, tilia, beat_tl, hierarchy_tl, tmp_path):
        self.add_beats(beat_tl, range(20))
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 12.5, 30.0, 1)

        (hierarchy,) = self.export(tmp_path)["Hierarchy"]

        assert (hierarchy["start_measure"], hierarchy["start_beat"]) == (4, 1.5)
        assert (hierarchy["end_measure"], hierarchy["end_beat"]) == (None, None)
        assert hierarchy["length_in_measures"] is None

    def test_an_end_on_the_closing_barline(
        self, tilia, beat_tl, hierarchy_tl, tmp_path
    ):
        # The closing barline is at 20: the end of measure 5, counted on from its
        # four beats (TimeLineAnnotator/project-management#649).
        self.add_beats(beat_tl, range(20))
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 0.0, 20.0, 1)

        (hierarchy,) = self.export(tmp_path)["Hierarchy"]

        assert (hierarchy["start_measure"], hierarchy["start_beat"]) == (1, 1)
        assert (hierarchy["end_measure"], hierarchy["end_beat"]) == (5, 5.0)
        assert isinstance(hierarchy["end_beat"], float)
        assert hierarchy["length_in_measures"] == [4, 4.0]

    def test_a_start_off_the_map(self, tilia, beat_tl, hierarchy_tl, tmp_path):
        self.add_beats(beat_tl, range(5, 20))
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 1.0, 10.0, 1)

        (hierarchy,) = self.export(tmp_path)["Hierarchy"]

        assert (hierarchy["start_measure"], hierarchy["start_beat"]) == (None, None)
        assert (hierarchy["end_measure"], hierarchy["end_beat"]) == (2, 2)
        assert hierarchy["length_in_measures"] is None

    def test_without_a_beat_timeline(self, tilia, marker_tl, tmp_path):
        marker_tl.create_component(ComponentKind.MARKER, 12.5)

        (marker,) = self.export(tmp_path)["Marker"]

        assert (marker["measure"], marker["beat"]) == (None, None)

    def test_the_beat_timeline_whose_role_is_time_map(
        self, tilia, tls, marker_tl, tmp_path
    ):
        first = tls.create_timeline(BeatTimeline, [], beat_pattern=[4])
        second = tls.create_timeline(
            BeatTimeline, [], beat_pattern=[2], fields={"role": "time_map"}
        )
        self.add_beats(first, range(20))
        self.add_beats(second, range(20))
        marker_tl.create_component(ComponentKind.MARKER, 12.5)

        (marker,) = self.export(tmp_path)["Marker"]

        assert (marker["measure"], marker["beat"]) == (7, 1.5)

    def test_a_beat_to_a_millionth(self, tilia, beat_tl, marker_tl, tmp_path):
        # A beat every 0.6 s: 7.5 s lies half-way between the beats at 7.2 and 7.8,
        # which the arithmetic gives as 1.5000000000000009.
        self.add_beats(beat_tl, [place * 0.6 for place in range(40)])
        for time in (7.5, 12.3, 3.3, 9.9):
            marker_tl.create_component(ComponentKind.MARKER, time)

        markers = self.export(tmp_path)["Marker"]

        assert [(m["time"], m["measure"], m["beat"]) for m in markers] == [
            (3.3, 2, 2.5),
            (7.5, 4, 1.5),
            (9.9, 5, 1.5),
            (12.3, 6, 1.5),
        ]

    def test_a_length_in_measures_to_a_millionth(
        self, tilia, beat_tl, hierarchy_tl, tmp_path
    ):
        self.add_beats(beat_tl, [place * 0.6 for place in range(40)])
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 3.3, 12.3, 1)
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 7.5, 12.3, 2)

        hierarchies = self.export(tmp_path)["Hierarchy"]

        assert [
            (
                h["start_measure"],
                h["start_beat"],
                h["end_measure"],
                h["end_beat"],
                h["length_in_measures"],
            )
            for h in sorted(hierarchies, key=lambda h: h["start"])
        ] == [(2, 2.5, 6, 1.5, [3, 3.0]), (4, 1.5, 6, 1.5, [2, 0.0])]

    @pytest.mark.parametrize(
        "start, end, exported",
        [
            (0.9, 8.1, (1, 2.5, 4, 2.5, [3, 0.0])),
            (2.7, 5.1, (2, 1.5, 3, 1.5, [1, 0.0])),
            (2.1, 11.7, (1, 4.5, 5, 4.5, [4, 0.0])),
        ],
    )
    def test_a_length_in_measures_agrees_with_the_beats_exported(
        self, tilia, beat_tl, hierarchy_tl, tmp_path, start, end, exported
    ):
        # The arithmetic puts the end's beat a hair below the start's: the length
        # is taken from the beats as exported, so it borrows no measure.
        self.add_beats(beat_tl, [place * 0.6 for place in range(40)])
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, start, end, 1)

        (h,) = self.export(tmp_path)["Hierarchy"]

        assert (
            h["start_measure"],
            h["start_beat"],
            h["end_measure"],
            h["end_beat"],
            h["length_in_measures"],
        ) == exported

    def test_a_length_in_measures_of_exported_beats_to_a_millionth(
        self, tilia, beat_tl, hierarchy_tl, tmp_path
    ):
        # A beat every 10 s: 1 s and 3 s are beats 1.1 and 1.3, and 1.3 less 1.1
        # is 0.20000000000000018 in floating point.
        self.add_beats(beat_tl, range(0, 100, 10))
        hierarchy_tl.create_component(ComponentKind.HIERARCHY, 1.0, 3.0, 1)

        (h,) = self.export(tmp_path)["Hierarchy"]

        assert (h["start_beat"], h["end_beat"]) == (1.1, 1.3)
        assert h["length_in_measures"] == [0, 0.2]


class TestExportImage:
    @staticmethod
    def _add_timeline():
        commands.execute("timelines.add.hierarchy", name="test")

    @pytest.mark.parametrize("scale_factor", [1.0, 0.5, 2.0])
    def test_image_export(self, qtui, monkeypatch, tmp_path, scale_factor):
        image_path = tmp_path / "tl_image.jpg"
        self._add_timeline()

        scene = get(Get.MAIN_WINDOW).centralWidget().scene()
        original_width = scene.sceneRect().width()
        original_height = scene.sceneRect().height()

        new_width = original_width * scale_factor

        monkeypatch.setattr(ResizeRect, "new_size", lambda *_: [True, new_width])

        commands.execute("file.export.img", image_path)

        with Image.open(image_path) as img:
            assert img.size[0] == new_width
            assert img.size[1] == original_height

        assert scene.sceneRect().width() == original_width
        assert scene.sceneRect().height() == original_height

    def test_image_export_resize_rejected(self, qtui, monkeypatch, tmp_path):
        image_path = tmp_path / "tl_image.jpg"
        self._add_timeline()

        monkeypatch.setattr(ResizeRect, "new_size", lambda *_: [False, None])

        commands.execute("file.export.img", image_path)

        assert not image_path.exists()
