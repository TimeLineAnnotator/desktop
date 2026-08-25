from tests.constants import EXAMPLE_MEDIA_PATH, EXAMPLE_PDF_PATH
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.pdf.timeline import PdfTimeline


class TestTimelineAdd:
    def test_wrong_timeline_kind_raises_error(self, cli, tls, tilia_errors):
        cli.parse_and_run("timeline add wrong")

        tilia_errors.assert_error()

    def test_add_timeline_with_no_duration_fails(
        self, cli, tls, tilia_state, tilia_errors
    ):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 0
        tilia_errors.assert_error()

    def test_retry_add_timeline_after_loading_media(
        self, cli, tls, tilia_state, tilia_errors
    ):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")
        cli.parse_and_run("load-media " + EXAMPLE_MEDIA_PATH)
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 1

    def test_retry_add_timeline_after_setting_duration(
        self, cli, tls, tilia_state, tilia_errors
    ):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")
        cli.parse_and_run("metadata set-media-length 10")
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 1

    def test_add_hierarchy_timeline(self, cli, tls):
        cli.parse_and_run("timeline add hrc --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, HierarchyTimeline)
        assert tl.name == "test"

    def test_add_marker_timeline(self, cli, tls):
        cli.parse_and_run("timeline add mrk --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, MarkerTimeline)
        assert tl.name == "test"

    def test_add_beat_timeline(self, cli, tls):
        cli.parse_and_run("timeline add beat --name test --beat-pattern 1 2 3")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, BeatTimeline)
        assert tl.name == "test"
        assert tl.beat_pattern == [1, 2, 3]

    def test_add_beat_timeline_no_beat_pattern_provided(self, cli, tls):
        cli.parse_and_run("timeline add beat")

        tl = tls.get_timelines()[0]
        assert tl.beat_pattern == [4]

    def test_add_harmony_timeline(self, cli, tls):
        cli.parse_and_run("timeline add har --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, HarmonyTimeline)
        assert tl.name == "test"

    def test_add_harmony_timeline_full_name(self, cli, tls):
        cli.parse_and_run("timeline add harmony")

        assert isinstance(tls.get_timelines()[0], HarmonyTimeline)

    def test_add_audiowave_timeline(self, cli, tls, tilia_errors):
        cli.parse_and_run("load-media " + EXAMPLE_MEDIA_PATH)
        cli.parse_and_run("timeline add aud --name test")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, AudioWaveTimeline)
        assert tl.name == "test"
        # An audiowave timeline is only useful once refresh() has read the
        # media and filled it in. Without media, or without a server for
        # Get.PLAYBACK_AREA_WIDTH, it comes out empty and hidden instead.
        assert tl.get_data("is_visible")
        assert len(tl) > 0
        tilia_errors.assert_no_error()

    def test_add_audiowave_timeline_full_name(self, cli, tls, tilia_errors):
        cli.parse_and_run("load-media " + EXAMPLE_MEDIA_PATH)
        cli.parse_and_run("timeline add audiowave")

        assert isinstance(tls.get_timelines()[0], AudioWaveTimeline)
        tilia_errors.assert_no_error()

    def test_add_audiowave_timeline_without_media_fails(self, cli, tls, tilia_errors):
        cli.parse_and_run("timeline add audiowave")

        tilia_errors.assert_error()
        assert not tls.get_timelines()[0].get_data("is_visible")

    def test_add_pdf_timeline(self, cli, tls, tilia_errors):
        cli.parse_and_run(f"timeline add pdf --name test --path {EXAMPLE_PDF_PATH}")

        tl = tls.get_timelines()[0]
        assert isinstance(tl, PdfTimeline)
        assert tl.name == "test"
        assert tl.get_data("is_pdf_valid")
        tilia_errors.assert_no_error()

    def test_add_pdf_timeline_without_path_fails(self, cli, tls, tilia_errors):
        cli.parse_and_run("timeline add pdf --name test")

        assert len(tls) == 0
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("--path")
        tilia_errors.assert_in_error_message("pdf")

    def test_height_rejected_for_harmony_kind(self, cli, tls, tilia_errors):
        cli.parse_and_run("timelines add harmony --name H --height 50")

        assert len(tls) == 0
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("--height")
        tilia_errors.assert_in_error_message("harmony")

    def test_height_applied_to_audiowave_kind(self, cli, tls):
        cli.parse_and_run("load-media " + EXAMPLE_MEDIA_PATH)
        cli.parse_and_run("timelines add audiowave --name A --height 123")

        assert tls.get_timelines()[0].height == 123

    def test_path_rejected_for_non_pdf_kind(self, cli, tls, tilia_errors):
        cli.parse_and_run(f"timelines add marker --name M --path {EXAMPLE_PDF_PATH}")

        assert len(tls) == 0
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("--path")
        tilia_errors.assert_in_error_message("marker")

    def test_row_height_rejected_for_non_range_kind(self, cli, tls, tilia_errors):
        cli.parse_and_run("timelines add marker --name M --row-height 50")

        assert len(tls) == 0
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("--row-height")
        tilia_errors.assert_in_error_message("marker")

    def test_beat_pattern_rejected_for_non_beat_kind(self, cli, tls, tilia_errors):
        cli.parse_and_run("timelines add marker --name M --beat-pattern 3 4")

        assert len(tls) == 0
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("--beat-pattern")
        tilia_errors.assert_in_error_message("marker")
