from unittest.mock import patch

import pytest

from tests.mock import Serve
from tilia.requests import Get
from tilia.ui import commands
from tilia.ui.dialogs.by_time_or_by_measure import ByTimeOrByMeasure

# The command that adds a component to each kind of timeline CSV import supports.
ADD_COMPONENT = {
    "beat": ("timeline.beat.add", {"time": 10}),
    "harmony": ("timeline.harmony.add_harmony", {"time": 10}),
    "hierarchy": ("timeline.hierarchy.add", {"start": 10, "end": 20, "level": 1}),
    "marker": ("timeline.marker.add", {"time": 10}),
    "pdf": ("timeline.pdf.add", {"time": 10}),
    "range": ("timeline.range.add_range", {"start": 10, "end": 20}),
}


class TestImportFromCsv:
    @pytest.mark.parametrize("kind", ADD_COMPONENT)
    def test_declining_overwrite_cancels_import_into_non_empty_timeline(
        self, kind, request, qtui  # qtui must exist before the timeline is created
    ):
        tlui = request.getfixturevalue(f"{kind}_tlui")
        command, kwargs = ADD_COMPONENT[kind]
        # add_harmony takes no argument for the chord, so answer its dialog.
        harmony_params = {"step": 0, "accidental": 0, "quality": "major"}
        with Serve(Get.FROM_USER_HARMONY_PARAMS, (True, harmony_params)):
            commands.execute(command, **kwargs)
        assert len(tlui) == 1
        components = tlui.timeline.get_state()["components"]

        with (
            patch.object(ByTimeOrByMeasure, "exec", return_value=True),
            Serve(Get.FROM_USER_YES_OR_NO, False) as confirmation,  # decline overwrite
            Serve(Get.FROM_USER_FILE_PATH, (False, None)) as file_dialog,
        ):
            success = commands.execute(f"timelines.import.{kind}")

        assert confirmation.called
        assert not success
        assert not file_dialog.called
        # Import was cancelled: the existing components are untouched.
        assert tlui.timeline.get_state()["components"] == components

    def test_cancelling_file_dialog_cancels_import_into_non_empty_timeline(
        self, marker_tlui
    ):
        commands.execute("timeline.marker.add")
        assert len(marker_tlui) == 1
        marker_time = marker_tlui[0].get_data("time")

        with (
            patch.object(ByTimeOrByMeasure, "exec", return_value=True),
            Serve(Get.FROM_USER_YES_OR_NO, True),  # confirm overwrite of non-empty tl
            Serve(Get.FROM_USER_FILE_PATH, (False, None)),  # cancel file-open dialog
        ):
            success = commands.execute("timelines.import.marker")

        assert not success
        # Import was cancelled: the existing marker is untouched.
        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == marker_time
