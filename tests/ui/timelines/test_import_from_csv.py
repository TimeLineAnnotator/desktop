from unittest.mock import patch

from tests.mock import Serve
from tilia.requests import Get
from tilia.ui import commands
from tilia.ui.dialogs.by_time_or_by_measure import ByTimeOrByMeasure


class TestImportFromCsv:
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
