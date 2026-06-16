import json
from pathlib import Path

from tests.mock import Serve, patch_yes_or_no_dialog
from tests.ui.timelines.marker.interact import click_marker_ui
from tests.utils import save_and_reopen, save_tilia_to_tmp_path, undoable
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.serialize import serialize_components
from tilia.ui import commands


def _read_tla(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TestSerializeComponentsSorting:
    def test_sorts_by_integer_id_not_lexicographic(self, marker_tl):
        # Force ids that sort differently as strings vs integers.
        marker_tl.create_component(ComponentKind.MARKER, time=0, id=10)
        marker_tl.create_component(ComponentKind.MARKER, time=1, id=2)
        marker_tl.create_component(ComponentKind.MARKER, time=2, id=11)

        result = serialize_components(marker_tl.components)

        assert list(result.keys()) == ["2", "10", "11"]

    def test_preserves_ids_in_dict(self, marker_tl):
        m1, _ = marker_tl.create_component(ComponentKind.MARKER, time=0)
        m2, _ = marker_tl.create_component(ComponentKind.MARKER, time=1)

        result = serialize_components(marker_tl.components)

        assert set(result.keys()) == {m1.id, m2.id}


class TestSerializeDeserializeRoundTrip:
    def test_serialize_then_deserialize_preserves_ids(self, marker_tl):
        # Use ids the system happens to assign; the assertion still checks
        # that whatever they were comes back unchanged.
        m1, _ = marker_tl.create_component(ComponentKind.MARKER, time=0)
        m2, _ = marker_tl.create_component(ComponentKind.MARKER, time=10)
        m3, _ = marker_tl.create_component(ComponentKind.MARKER, time=20)
        original_ids = [m1.id, m2.id, m3.id]

        serialized = marker_tl.component_manager.serialize_components()
        marker_tl.component_manager.clear()
        marker_tl.component_manager.deserialize_components(serialized)

        assert {c.id for c in marker_tl.components} == set(original_ids)

    def test_round_trip_serialize_is_byte_identical(self, marker_tl):
        marker_tl.create_component(ComponentKind.MARKER, time=0)
        marker_tl.create_component(ComponentKind.MARKER, time=10)
        marker_tl.create_component(ComponentKind.MARKER, time=20)

        serialized = marker_tl.component_manager.serialize_components()
        marker_tl.component_manager.clear()
        marker_tl.component_manager.deserialize_components(serialized)
        re_serialized = marker_tl.component_manager.serialize_components()

        assert re_serialized == serialized
        assert list(re_serialized.keys()) == list(serialized.keys())

    def test_deserialize_with_non_sequential_ids_preserves_them(self, marker_tl):
        # Mimic a JSON file with arbitrary string keys.
        serialized = {
            "42": {
                "time": 0,
                "comments": "",
                "label": "",
                "color": None,
                "kind": "MARKER",
                "hash": "irrelevant",
            },
            "7": {
                "time": 10,
                "comments": "",
                "label": "",
                "color": None,
                "kind": "MARKER",
                "hash": "irrelevant",
            },
        }

        marker_tl.component_manager.deserialize_components(serialized)

        ids = {c.id for c in marker_tl.components}
        assert ids == {"42", "7"}


class TestRoundTripDesktopFileDesktop:
    def test_marker_ids_preserved_after_save_open(self, tilia, marker_tlui, tmp_path):
        for time in [0, 10, 20, 30]:
            commands.execute("timeline.marker.add", time=time)

        original_tl_id = marker_tlui.id
        original_marker_ids = [m.id for m in marker_tlui.timeline.components]

        save_and_reopen(tmp_path, "round_trip")

        reloaded_tl = tilia.timelines.get_timeline(original_tl_id)
        reloaded_marker_ids = [m.id for m in reloaded_tl.components]
        assert reloaded_marker_ids == original_marker_ids

    def test_saved_components_dict_is_sorted_by_integer_id(self, marker_tlui, tmp_path):
        for time in [0, 10, 20]:
            commands.execute("timeline.marker.add", time=time)

        save_path = save_tilia_to_tmp_path(tmp_path, "sorted")

        contents = _read_tla(save_path)
        components = contents["timelines"][str(marker_tlui.id)]["components"]
        keys_as_ints = [int(k) for k in components.keys()]
        assert keys_as_ints == sorted(keys_as_ints)

    def test_save_open_save_preserves_components_per_timeline(
        self, slider_tlui, marker_tlui, beat_tlui, tmp_path
    ):
        # slider_tlui is requested so the first save already includes a
        # slider timeline. Otherwise, on_open's setup_file would auto-add
        # one (it creates a slider when the loaded file has none) and the
        # second save would gain a new timeline id absent from the first.
        for time in [0, 10, 20]:
            commands.execute("timeline.marker.add", time=time)
        for time in [5, 15, 25]:
            commands.execute("timeline.beat.add", time=time)

        save_and_reopen(tmp_path, "first")
        first_contents = _read_tla(tmp_path / "first.tla")

        second_path = save_tilia_to_tmp_path(tmp_path, "second")
        second_contents = _read_tla(second_path)

        assert second_contents["timelines"] == first_contents["timelines"]


def _save_open_save(tmp_path) -> tuple[dict, dict]:
    """Save → reopen → save again. Returns (first_contents, second_contents)
    so callers can assert byte-identity of the timelines dict."""
    save_and_reopen(tmp_path, "first")
    first = _read_tla(tmp_path / "first.tla")
    second_path = save_tilia_to_tmp_path(tmp_path, "second")
    second = _read_tla(second_path)
    return first, second


class TestRoundTripPerTimelineKind:
    """Save-open-save preserves the timelines dict for every kind that has
    persistent components. slider_tlui is requested everywhere so on_open
    won't add a fresh slider after reload (see the test in
    TestRoundTripDesktopFileDesktop for the same workaround)."""

    def test_harmony_round_trip(self, slider_tlui, harmony_tlui, tmp_path):
        harmony_params = {
            "step": 0,
            "accidental": 0,
            "inversion": 0,
            "quality": "major",
            "applied_to": 0,
            "display_mode": "roman",
            "level": 1,
        }
        mode_params = {
            "step": 0,
            "accidental": 0,
            "type": "major",
            "level": 2,
        }
        with Serve(Get.FROM_USER_HARMONY_PARAMS, (True, harmony_params)):
            for time in [0, 10, 20]:
                commands.execute("timeline.harmony.add_harmony", time=time)
        with Serve(Get.FROM_USER_MODE_PARAMS, (True, mode_params)):
            commands.execute("timeline.harmony.add_mode", time=5)

        first, second = _save_open_save(tmp_path)
        assert second["timelines"] == first["timelines"]

    def test_pdf_round_trip(self, slider_tlui, pdf_tlui, tmp_path):
        for time in [0, 10, 20]:
            commands.execute("timeline.pdf.add", time=time)

        first, second = _save_open_save(tmp_path)
        assert second["timelines"] == first["timelines"]

    def test_audiowave_round_trip(self, slider_tlui, audiowave_tlui, tmp_path):
        # No add command for audiowave; create amplitudebars via the
        # timeline API the fixture exposes.
        for start, end, amplitude in [
            (0.0, 1.0, 0.1),
            (1.0, 2.0, 0.5),
            (2.0, 3.0, 0.3),
        ]:
            audiowave_tlui.create_amplitudebar(start, end, amplitude)

        first, second = _save_open_save(tmp_path)
        assert second["timelines"] == first["timelines"]


class TestScoreTimelineRoundTrip:
    """Score has had past round-trip issues: cross-component references
    via staff_index, score-specific deserialization that rebuilds caches,
    and a wider variety of component kinds than the other timelines.
    Cover each in turn."""

    @staticmethod
    def _populate_two_staff_score(score_tl):
        """Build a small two-staff score covering every score component
        kind. The order matters: staffs first, then symbols and notes
        that reference them via staff_index."""
        score_tl.create_component(ComponentKind.STAFF, 0, 5)
        score_tl.create_component(ComponentKind.STAFF, 1, 5)

        for staff_index in (0, 1):
            score_tl.create_component(
                ComponentKind.CLEF,
                staff_index,
                0,
                shorthand=Clef.Shorthand.TREBLE,
            )
            score_tl.create_component(ComponentKind.KEY_SIGNATURE, staff_index, 0, 2)
            score_tl.create_component(
                ComponentKind.TIME_SIGNATURE, staff_index, 0, 4, 4
            )

        for time in (0.0, 5.0, 10.0):
            score_tl.create_component(ComponentKind.BAR_LINE, time)

        score_tl.create_component(ComponentKind.NOTE, 0.0, 5.0, 0, 0, 4, 0)
        score_tl.create_component(ComponentKind.NOTE, 5.0, 10.0, 2, 0, 4, 0)
        score_tl.create_component(ComponentKind.NOTE, 0.0, 5.0, 4, 0, 3, 1)

        score_tl.create_component(
            ComponentKind.SCORE_ANNOTATION,
            x=10.0,
            y=20.0,
            viewer_id=0,
            text="annotation",
            font_size=14,
        )

    def test_full_score_round_trips_byte_identical(
        self, slider_tlui, score_tlui, tmp_path
    ):
        self._populate_two_staff_score(score_tlui.timeline)

        first, second = _save_open_save(tmp_path)
        assert second["timelines"] == first["timelines"]

    def test_score_components_dict_sorted_by_int_id(
        self, slider_tlui, score_tlui, tmp_path
    ):
        self._populate_two_staff_score(score_tlui.timeline)

        save_path = save_tilia_to_tmp_path(tmp_path, "score_sorted")
        contents = _read_tla(save_path)

        score_components = contents["timelines"][str(score_tlui.id)]["components"]
        keys_as_ints = [int(k) for k in score_components.keys()]
        assert keys_as_ints == sorted(keys_as_ints)

    def test_score_with_arbitrary_non_sequential_ids_round_trips(
        self, slider_tlui, score_tlui, tilia, tmp_path
    ):
        # Inject explicit non-sequential ids — which could come from previous TiLiA versions
        score_tl = score_tlui.timeline
        score_tl.create_component(ComponentKind.STAFF, 0, 5, id=100)
        score_tl.create_component(
            ComponentKind.CLEF, 0, 0, shorthand=Clef.Shorthand.TREBLE, id=5
        )
        score_tl.create_component(ComponentKind.NOTE, 0.0, 5.0, 0, 0, 4, 0, id=50)
        score_tl.create_component(ComponentKind.NOTE, 5.0, 10.0, 2, 0, 4, 0, id=3)
        score_tl.create_component(ComponentKind.BAR_LINE, 0.0, id=200)

        original_tl_id = score_tlui.id
        original_components = score_tl.component_manager.serialize_components()

        save_and_reopen(tmp_path, "arbitrary_ids")

        reloaded = tilia.timelines.get_timeline(original_tl_id)
        reloaded_components = reloaded.component_manager.serialize_components()
        assert reloaded_components == original_components
        assert list(reloaded_components.keys()) == sorted(
            reloaded_components.keys(), key=int
        )

    def test_staff_index_references_survive_round_trip(
        self, slider_tlui, score_tlui, tilia, tmp_path
    ):
        # Notes/clefs/etc. reference a staff via staff_index. Confirm
        # those references match exactly after a round trip — a regression
        # here would silently disconnect notes from their staffs.
        self._populate_two_staff_score(score_tlui.timeline)
        original_tl_id = score_tlui.id

        def _by_staff_index(score_tl):
            grouped = {0: [], 1: []}
            for component in score_tl.components:
                if not hasattr(component, "staff_index"):
                    continue
                grouped[component.staff_index].append(
                    (component.KIND.name, component.id)
                )
            for items in grouped.values():
                items.sort()
            return grouped

        original = _by_staff_index(score_tlui.timeline)

        save_and_reopen(tmp_path, "staff_refs")

        reloaded = tilia.timelines.get_timeline(original_tl_id)
        assert _by_staff_index(reloaded) == original


class TestUndoRedoIdTransmission:
    def test_undo_delete_restores_original_id(self, marker_tlui, tluis):
        commands.execute("timeline.marker.add")
        original_id = marker_tlui[0].id

        click_marker_ui(marker_tlui[0])
        commands.execute("timeline.component.delete")
        assert marker_tlui.is_empty

        commands.execute("edit.undo")
        assert marker_tlui[0].id == original_id

    def test_undo_clear_restores_all_ids(self, marker_tlui, tluis):
        for time in [0, 10, 20]:
            commands.execute("timeline.marker.add", time=time)
        original_ids = [m.id for m in marker_tlui]

        with patch_yes_or_no_dialog(True):
            commands.execute("timeline.clear", marker_tlui)
        assert marker_tlui.is_empty

        commands.execute("edit.undo")
        assert sorted([m.id for m in marker_tlui], key=int) == sorted(
            original_ids, key=int
        )

    def test_app_state_round_trip_via_undo_redo(self, marker_tlui):
        with undoable():
            commands.execute("timeline.marker.add", time=5)
