import json
import logging
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

import tests.utils
import tilia.log
from tests.constants import EXAMPLE_MEDIA_DURATION, EXAMPLE_MEDIA_PATH
from tests.mock import (
    PatchPost,
    Serve,
    patch_file_dialog,
    patch_yes_no_or_cancel_mb,
    patch_yes_or_no_dialog,
)
from tests.utils import (
    EXAMPLE_YOUTUBE_URL,
    load_local_media,
    load_youtube_media,
    save_and_reopen,
    save_tilia_to_tmp_path,
)
from tilia.file.migration import find_unknown_timeline_kinds
from tilia.media.player import QtAudioPlayer, YouTubePlayer
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.slider.timeline import SliderTimeline
from tilia.ui import commands
from tilia.ui.windows import WindowKind


class TestLogger:
    def test_sentry_not_logging(self, use_test_logger):
        assert "tilia.log" in tilia.log.sentry_sdk.integrations.logging._IGNORED_LOGGERS

    def test_sentry_ignores_tilia_log_records(self):
        tilia.log.sentry_sdk.integrations.logging.ignore_logger(tilia.log.logger.name)
        record = logging.LogRecord(
            name=tilia.log.logger.name,
            level=logging.CRITICAL,
            pathname=__file__,
            lineno=0,
            msg="intentional test failure - must not reach Sentry",
            args=None,
            exc_info=None,
        )
        event_handler = tilia.log.sentry_sdk.integrations.logging.EventHandler()
        breadcrumb_handler = (
            tilia.log.sentry_sdk.integrations.logging.BreadcrumbHandler()
        )
        assert not event_handler._can_record(record)
        assert not breadcrumb_handler._can_record(record)

    def test_sentry_is_never_initialized_during_tests(self):
        client = tilia.log.sentry_sdk.get_client()
        assert not client.is_active()


class TestSaveFileOnClose:
    @staticmethod
    def _get_modified_file_state():
        return {
            "timelines": {},
            "media_path": "modified.ogg",
            "media_metadata": {},
            "file_path": "",
        }

    def test_no_changes(self):
        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        exit_mock.assert_called()
        save_mock.assert_not_called()

    def test_file_modified_and_user_chooses_to_save_changes(self, tmp_path):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, tmp_file)),
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_modified_and_user_chooses_to_save_changes_when_file_was_previously_saved(
        self, tmp_path
    ):
        tmp_file = tmp_path / "test_file_modified_and_user_chooses_to_save_changes.tla"
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, tmp_file)),
        ):
            commands.execute("file.save")

        with (
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        exit_mock.assert_called()
        assert tmp_file.exists()

    def test_file_is_modified_and_user_cancels_close_on_should_save_changes_dialog(
        self,
    ):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, True)),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        exit_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_file_is_modified_and_user_cancels_file_save_dialog(self):
        with (
            Serve(Get.APP_STATE, self._get_modified_file_state()),
            Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)),
            Serve(Get.FROM_USER_SAVE_PATH_TILIA, (False, "")),
            patch("tilia.file.file_manager.FileManager.save") as save_mock,
            PatchPost("tilia.app", Post.UI_EXIT) as exit_mock,
        ):
            commands.execute("tilia.close")

        exit_mock.assert_not_called()
        save_mock.assert_not_called()


class TestFileLoad:
    def test_media_path_does_not_exist_and_media_length_available(
        self, tilia_state, qtui, tmp_path
    ):
        tilia_state.duration = 101

        # set media path to a non-existing file
        nonexisting_media = tmp_path / "nothere.mp3"
        load_local_media(nonexisting_media)

        # save tilia file
        tla_path = tmp_path / "test.tla"
        with patch_file_dialog(True, [str(tla_path)]):
            commands.execute("file.save_as")

        # open tilia file
        with (
            patch_file_dialog(True, [str(tla_path)]),
            patch_yes_no_or_cancel_mb(False),
        ):
            commands.execute("file.open")

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 101

    def test_media_path_does_not_exist_and_media_length_not_available(
        self, qtui, tilia_state, tmp_path
    ):
        tilia_state.duration = 0
        file_data = tests.utils.get_blank_file_data()
        file_data["media_path"] = "invalid.tla"
        tmp_file = tmp_path / "test_file_load.tla"
        tmp_file.write_text(json.dumps(file_data))
        with (
            patch_file_dialog(True, [str(tmp_file)]),
            patch_yes_or_no_dialog(False),  # do no try to load another media
        ):
            commands.execute("file.open")

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == ""
        assert tilia_state.duration == 0

    def test_media_path_exists(self, tilia, qtui, tilia_state, tmp_path, tls):
        tmp_file = tmp_path / "test_file_load.tla"
        load_local_media(EXAMPLE_MEDIA_PATH)

        with patch_file_dialog(True, [str(tmp_file)]):
            commands.execute("file.save_as")
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            commands.execute("file.open")

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH
        assert tilia_state.duration == EXAMPLE_MEDIA_DURATION

    def test_media_path_is_youtube_url(self, tilia_state, qtui, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        tmp_file = tmp_path / "test_file_load.tla"
        media_path = "https://www.youtube.com/watch?v=wBfVsucRe1w"
        file_data["media_path"] = media_path
        file_data["media_metadata"]["media length"] = 101
        tmp_file.write_text(json.dumps(file_data))
        with (
            Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)),
            Serve(Get.PLAYER_CLASS, YouTubePlayer),
        ):
            commands.execute("file.open")

        assert tilia_state.is_undo_manager_cleared
        assert tilia_state.media_path == media_path
        assert tilia_state.duration == 101

    def test_stale_youtube_duration_after_switching_video_is_ignored(
        self, tilia, tilia_state, qtui, tmp_path
    ):
        # Regression test: opening two YouTube-backed files in a row reuses
        # the same YouTubePlayer/QWebEngineView instance (media type doesn't
        # change, so _change_player_type never tears it down). A
        # getDuration() JS query issued for the first video can resolve
        # after the second video has already loaded -- on_media_duration_available
        # must ignore a result tagged with a video_id that's no longer the
        # one currently loaded, rather than silently overwriting the
        # duration of the (unrelated) now-open file.
        def make_file(tmp_name: str, media_path: str, media_length: float):
            file_data = tests.utils.get_blank_file_data()
            file_data["media_path"] = media_path
            file_data["media_metadata"]["media length"] = media_length
            path = tmp_path / tmp_name
            path.write_text(json.dumps(file_data))
            return path

        file_a = make_file(
            "file_a.tla", "https://www.youtube.com/watch?v=aaaaaaaaaaa", 100
        )
        file_b = make_file(
            "file_b.tla", "https://www.youtube.com/watch?v=bbbbbbbbbbb", 200
        )

        with (
            Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, file_a)),
            Serve(Get.PLAYER_CLASS, YouTubePlayer),
        ):
            commands.execute("file.open")
        video_id_a = tilia.player.video_id
        assert tilia_state.duration == 100

        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, file_b)):
            commands.execute("file.open")
        video_id_b = tilia.player.video_id
        assert video_id_b != video_id_a
        assert tilia_state.duration == 200

        # Simulate file A's getDuration() echo resolving late, after file B
        # has already loaded into the same, reused player instance.
        tilia.player.on_media_duration_available(999.0, requested_video_id=video_id_a)
        assert tilia_state.duration == 200

        # A report tagged with the currently-loaded video is still honored.
        tilia.player.on_media_duration_available(201.0, requested_video_id=video_id_b)
        assert tilia_state.duration == 201

    @pytest.mark.parametrize(
        "reported_duration",
        [EXAMPLE_MEDIA_DURATION - 1, EXAMPLE_MEDIA_DURATION + 1],
        ids=["shorter", "longer"],
    )
    def test_async_duration_after_open_does_not_prompt_or_change_timelines(
        self, tilia, tilia_state, marker_tlui, tls, tmp_path, reported_duration
    ):
        # Regression for #453. Opening a file loads its media with
        # scale_timelines="keep": the timelines were saved to match it, so a
        # slightly different duration later reported by the player (YouTube
        # returns it asynchronously, often off by a fraction of a second)
        # must neither prompt to scale nor scale/crop components -- whether
        # it comes back longer or shorter than the stored value. A shorter
        # value used to crop and silently delete end components.

        # Reference real media in the file, but without a live QMediaPlayer
        # load while building it: reopening performs the only real media
        # load, and a second Qt setSource in one process can deadlock
        # CoreAudio on macOS.
        tilia_state.media_path = EXAMPLE_MEDIA_PATH
        # "no" (not the prompting default) because the marker timeline
        # fixture already exists; it is still empty here, so nothing scales
        # or crops.
        tilia_state.set_duration(EXAMPLE_MEDIA_DURATION, scale_timelines="no")
        marker_time = EXAMPLE_MEDIA_DURATION - 0.5
        commands.execute("media.seek", marker_time)
        commands.execute("timeline.marker.add")

        # Stub the Qt engine load so reopening doesn't touch a real audio
        # device; the scale/crop path under test is driven by the
        # set_file_media_duration call below, not by the media load itself.
        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
            save_and_reopen(tmp_path)
            with Serve(Get.FROM_USER_YES_OR_NO, True) as scale_prompt:
                tilia.set_file_media_duration(reported_duration)

        marker_tl = tls.get_timelines_by_attr("KIND", TimelineKind.MARKER_TIMELINE)[0]
        assert not scale_prompt.called
        assert len(marker_tl) == 1
        assert marker_tl[0].get_data("time") == pytest.approx(marker_time)

    def test_large_async_duration_change_after_open_still_prompts(
        self, tilia, tilia_state, marker_tlui, tls, tmp_path
    ):
        # A duration change larger than DURATION_JITTER_TOLERANCE
        # (tilia/app.py) is not YouTube's async jitter -- even under "keep"
        # it must still be treated as a genuine media change and prompt to
        # scale, unlike the small-jitter case in the test above.
        tilia_state.media_path = EXAMPLE_MEDIA_PATH
        tilia_state.set_duration(EXAMPLE_MEDIA_DURATION, scale_timelines="no")
        marker_time = EXAMPLE_MEDIA_DURATION - 0.5
        commands.execute("media.seek", marker_time)
        commands.execute("timeline.marker.add")

        new_duration = EXAMPLE_MEDIA_DURATION + 100
        with patch.object(QtAudioPlayer, "_engine_load_media", return_value=True):
            save_and_reopen(tmp_path)
            with Serve(Get.FROM_USER_YES_OR_NO, True) as scale_prompt:
                tilia.set_file_media_duration(new_duration)

        marker_tl = tls.get_timelines_by_attr("KIND", TimelineKind.MARKER_TIMELINE)[0]
        assert scale_prompt.called
        assert marker_tl[0].get_data("time") == pytest.approx(
            marker_time * new_duration / EXAMPLE_MEDIA_DURATION
        )


class TestMediaLoad:
    @staticmethod
    def _load_media(path, scale_timelines: Literal["yes", "no", "prompt"] = "prompt"):
        with Serve(Get.PLAYER_CLASS, QtAudioPlayer):
            post(Post.APP_MEDIA_LOAD, path, scale_timelines=scale_timelines)

    def test_load_local(self, tilia_state):
        self._load_media(EXAMPLE_MEDIA_PATH)
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH
        assert tilia_state.duration == EXAMPLE_MEDIA_DURATION

    def test_undo(self, tilia_state):
        self._load_media(EXAMPLE_MEDIA_PATH)
        commands.execute("edit.undo")
        assert not tilia_state.media_path

    def test_redo(self, tilia_state):
        self._load_media(EXAMPLE_MEDIA_PATH)
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH

    def test_load_invalid_extension(self, tilia_state, tilia_errors):
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert not tilia_state.media_path

    def test_load_invalid_extension_with_media_loaded(self, tilia_state, tilia_errors):
        self._load_media(EXAMPLE_MEDIA_PATH)
        self._load_media("invalid.xyz")
        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("xyz")
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH

    def test_load_media_after_loading_media_with_invalid_extension(self, tilia_state):
        self._load_media("invalid.xyz")
        self._load_media(EXAMPLE_MEDIA_PATH)
        assert tilia_state.media_path == EXAMPLE_MEDIA_PATH

    def test_scale_timelines_is_no(self, marker_tl):
        marker_tl.create_marker(5)
        marker_tl.create_marker(10)
        self._load_media(EXAMPLE_MEDIA_PATH, "no")
        assert len(marker_tl) == 1
        assert marker_tl[0].get_data("time") == 5

    def test_scale_timelines_is_yes(self, tilia_state, marker_tl):
        prev_duration = tilia_state.duration
        marker_tl.create_marker(50)
        self._load_media(EXAMPLE_MEDIA_PATH, "yes")
        assert (
            marker_tl[0].get_data("time") == 50 * EXAMPLE_MEDIA_DURATION / prev_duration
        )


class TestScaleCropTimeline:
    @pytest.mark.parametrize(
        "scale_timelines,scale_factor",
        [
            (("yes", "yes"), (2, 2)),
            (("yes", "no"), (2, 2)),
            (("no", "yes"), (2, 2)),
            (("no", "no"), (2, 2)),
        ],
    )
    def test_set_duration_twice_without_cropping(
        self, scale_timelines, scale_factor, tilia_state, marker_tlui
    ):
        marker_time = 50
        commands.execute("media.seek", marker_time)
        commands.execute("timeline.marker.add")
        displacement_factor = 1
        for factor, should_scale in zip(scale_factor, scale_timelines, strict=True):
            tilia_state.set_duration(
                tilia_state.duration * factor, scale_timelines=should_scale
            )
            if should_scale == "yes":
                displacement_factor *= factor
        assert marker_tlui[0].get_data("time") == marker_time * displacement_factor

    def test_scale_then_crop(self, marker_tlui, tilia_state):
        commands.execute("media.seek", 10)
        commands.execute("timeline.marker.add")
        commands.execute("media.seek", 50)
        commands.execute("timeline.marker.add")
        tilia_state.set_duration(200, scale_timelines="yes")
        tilia_state.set_duration(50, scale_timelines="no")
        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 20

    def test_crop_then_scale(self, marker_tlui, tilia_state):
        commands.execute("media.seek", 10)
        commands.execute("timeline.marker.add")
        commands.execute("media.seek", 50)
        commands.execute("timeline.marker.add")
        tilia_state.set_duration(40, scale_timelines="no")
        tilia_state.set_duration(80, scale_timelines="yes")
        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 20

    def test_crop_twice(self, marker_tlui, tilia_state):
        commands.execute("media.seek", 10)
        commands.execute("timeline.marker.add")
        commands.execute("media.seek", 50)
        commands.execute("timeline.marker.add")
        tilia_state.set_duration(80, scale_timelines="no")
        tilia_state.set_duration(40, scale_timelines="no")
        assert len(marker_tlui) == 1
        assert marker_tlui[0].get_data("time") == 10

    def test_crop_repositions_hierarchy_against_new_duration(
        self, hierarchy_tlui, tilia_state
    ):
        # Regression test for #496: when on_media_duration_changed
        # cropped components, FILE_MEDIA_DURATION_CHANGED was posted
        # afterwards, so update_position used the *old* media_duration
        # in time_x_converter. A hierarchy cropped to fill the new
        # (shorter) timeline ended up drawn against the old end-time
        # and stopped halfway across the visible area.
        from tilia.ui.coords import time_x_converter
        from tilia.ui.timelines.hierarchy.element import HierarchyUI

        tilia_state.set_duration(100)
        commands.execute("timeline.hierarchy.add", start=0, end=100, level=1)
        tilia_state.set_duration(50, scale_timelines="no")  # falls back to crop

        # After crop the component spans [0, 50]; the new media is 50s
        # long so the body's right edge must align with x(50) — minus
        # the small X_OFFSET the body adds — i.e. the timeline's right
        # margin under the *new* converter.
        body_right = hierarchy_tlui[0].body.rect().right()
        expected_right = time_x_converter.get_x_by_time(50) - HierarchyUI.X_OFFSET
        assert body_right == pytest.approx(expected_right)


class TestFileSetup:
    def test_slider_timeline_is_created_when_loaded_file_does_not_have_one(
        self, tls, tmp_path
    ):
        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = {
            "1": {
                "name": "",
                "height": 40,
                "is_visible": True,
                "ordinal": 1,
                "components": {},
                "kind": "Hierarchy",
            }
        }  # empty hierarchy timeline
        tmp_file = tmp_path / "test_file_setup.tla"
        tmp_file.write_text(json.dumps(file_data))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            commands.execute("file.open")

        assert len(tls) == 2
        assert SliderTimeline in tls.timeline_types


def assert_open_failed(tilia, tilia_errors, opened_file_path, prev_file):
    tilia_errors.assert_error()
    assert settings.get_recent_files()[0] != opened_file_path
    assert tilia.file_manager.file == prev_file


UNKNOWN_TIMELINE_KIND = "SOME_FUTURE_TIMELINE_KIND"
UNKNOWN_TIMELINE_ID = "0"
KNOWN_TIMELINE_ID = "1"


def get_file_data_with_unknown_timeline_kind():
    file_data = tests.utils.get_blank_file_data()
    file_data["version"] = "99.0.0"
    file_data["timelines"] = {
        UNKNOWN_TIMELINE_ID: {
            "is_visible": True,
            "ordinal": 1,
            "height": 40,
            "kind": UNKNOWN_TIMELINE_KIND,
            "components": {},
        },
        KNOWN_TIMELINE_ID: {
            "is_visible": True,
            "ordinal": 2,
            "height": 40,
            "kind": "MARKER_TIMELINE",
            "components": {},
            "components_hash": "d41d8cd98f00b204e9800998ecf8427e",
        },
    }
    return file_data


class TestOpen:
    def test_open_with_timeline(self, tilia, tls, tmp_path):
        tl_data = tests.utils.get_dummy_timeline_data()
        tl_id = list(tl_data.keys())[0]

        for i, (start, end, level) in enumerate([(0, 1, 1), (1, 2, 1), (2, 3, 2)]):
            tl_data[tl_id]["components"][i] = {
                "start": start,
                "end": end,
                "level": level,
                "comments": "",
                "label": "Unit 1",
                "parent": None,
                "children": [],
                "kind": "HIERARCHY",
            }

        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = tl_data
        file_data["media_metadata"]["media length"] = 100

        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(file_data, indent=2))
        with Serve(Get.FROM_USER_TILIA_FILE_PATH, (True, tmp_file)):
            commands.execute("file.open")

        assert Path(settings.get_recent_files()[0]) == tmp_file
        assert len(tls) == 2  # Slider timeline is also created by default
        assert len(tls[0]) == 3

    def test_open_with_path(self, tilia, tls, tmp_path):
        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)
        commands.execute("file.open", tmp_file)

        assert Path(settings.get_recent_files()[0]) == tmp_file
        assert len(tls) == 2  # Slider timeline is also created by default

    def test_open_file_does_not_exist(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        commands.execute("file.open", tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_is_not_valid_json(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text("{")
        commands.execute("file.open", tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_is_not_valid_tla(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text('{"a": 1, "b": 2}')
        commands.execute("file.open", tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_file_with_bad_timeline_data(self, tilia, tmp_path, tilia_errors):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = {"nonsense": 404}
        tmp_file.write_text(json.dumps(file_data))
        commands.execute("file.open", tmp_file)

        assert_open_failed(tilia, tilia_errors, tmp_file, prev_file)

    def test_open_newer_file_with_unknown_timeline_kind_user_cancels(
        self, tilia, tmp_path, tilia_errors
    ):
        prev_file = tilia.file_manager.file
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(get_file_data_with_unknown_timeline_kind()))

        with (
            Serve(Get.FROM_USER_YES_OR_NO, True),
            Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (False, False)),
        ):
            commands.execute("file.open", tmp_file)

        tilia_errors.assert_no_error()
        assert settings.get_recent_files()[0] != tmp_file
        assert tilia.file_manager.file == prev_file

    def test_open_newer_file_with_unknown_timeline_kind_user_deletes(
        self, tilia, tmp_path, tilia_errors
    ):
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(get_file_data_with_unknown_timeline_kind()))

        with (
            Serve(Get.FROM_USER_YES_OR_NO, True),
            Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, True)),
        ):
            commands.execute("file.open", tmp_file)

        tilia_errors.assert_no_error()
        assert Path(settings.get_recent_files()[0]) == tmp_file
        assert UNKNOWN_TIMELINE_ID not in {tl.id for tl in tilia.timelines}
        assert tilia.file_manager.file.unknown_timelines == {}
        assert tilia.file_manager.file.timelines[UNKNOWN_TIMELINE_ID]["kind"] == (
            UNKNOWN_TIMELINE_KIND
        )
        assert tilia.is_file_modified()

        known = tilia.file_manager.file.timelines[KNOWN_TIMELINE_ID]
        assert known["kind"] == "MARKER_TIMELINE"
        assert known["ordinal"] == 1

    def test_open_newer_file_with_unknown_timeline_kind_user_ignores(
        self, tilia, tmp_path, tilia_errors
    ):
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(get_file_data_with_unknown_timeline_kind()))

        with (
            Serve(Get.FROM_USER_YES_OR_NO, True),
            Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
        ):
            commands.execute("file.open", tmp_file)

        tilia_errors.assert_no_error()
        assert UNKNOWN_TIMELINE_ID not in {tl.id for tl in tilia.timelines}
        assert tilia.file_manager.file.timelines[UNKNOWN_TIMELINE_ID]["kind"] == (
            UNKNOWN_TIMELINE_KIND
        )
        assert (
            tilia.file_manager.file.unknown_timelines[UNKNOWN_TIMELINE_ID]["kind"]
            == UNKNOWN_TIMELINE_KIND
        )

        live_hashes = {
            tl["components_hash"] for tl in tilia.get_app_state()["timelines"].values()
        }
        stored_hashes = {
            tl["components_hash"] for tl in tilia.file_manager.file.timelines.values()
        }
        assert live_hashes == stored_hashes

        known = tilia.file_manager.file.timelines[KNOWN_TIMELINE_ID]
        assert known["kind"] == "MARKER_TIMELINE"
        assert known["ordinal"] == 1
        ordinals = [tl["ordinal"] for tl in tilia.file_manager.file.timelines.values()]
        assert len(ordinals) == len(set(ordinals))
        assert UNKNOWN_TIMELINE_ID not in {tl.id for tl in tilia.timelines}

    def test_reserved_id_survives_a_lower_explicit_id_processed_after(
        self, tilia, tmp_path, tilia_errors
    ):
        file_data = tests.utils.get_blank_file_data()
        file_data["version"] = "99.0.0"
        file_data["timelines"] = {
            "1": {
                "is_visible": True,
                "ordinal": 1,
                "height": 40,
                "kind": UNKNOWN_TIMELINE_KIND,
                "components": {},
            },
            "0": {
                "is_visible": True,
                "ordinal": 2,
                "height": 40,
                "kind": "MARKER_TIMELINE",
                "components": {},
            },
        }
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(file_data))

        with (
            Serve(Get.FROM_USER_YES_OR_NO, True),
            Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
        ):
            commands.execute("file.open", tmp_file)

        tilia_errors.assert_no_error()
        live_ids = {tl.id for tl in tilia.timelines}
        assert "0" in live_ids  # the known timeline
        assert "1" not in live_ids  # reserved by the ignored timeline

    def test_ignored_unknown_timeline_survives_a_save(
        self, tilia, qtui, tmp_path, tilia_errors
    ):
        open_path = tmp_path / "test.tla"
        open_path.write_text(json.dumps(get_file_data_with_unknown_timeline_kind()))

        with (
            Serve(Get.FROM_USER_YES_OR_NO, True),
            Serve(Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, (True, False)),
        ):
            commands.execute("file.open", open_path)

        save_path = tmp_path / "resaved.tla"
        with patch_file_dialog(True, [str(save_path)]):
            commands.execute("file.save_as")

        saved_data = json.loads(save_path.read_text())
        assert saved_data["timelines"][UNKNOWN_TIMELINE_ID]["kind"] == (
            UNKNOWN_TIMELINE_KIND
        )
        assert "unknown_timelines" not in saved_data

        assert saved_data["timelines"][KNOWN_TIMELINE_ID]["ordinal"] == 1
        assert (
            saved_data["timelines"][UNKNOWN_TIMELINE_ID]["ordinal"] == 3
        )  # slider timeline is 2
        ordinals = [tl["ordinal"] for tl in saved_data["timelines"].values()]
        assert len(ordinals) == len(set(ordinals))

    def test_known_kind_is_loaded_normally_not_flagged_unknown(self):
        file_data = get_file_data_with_unknown_timeline_kind()
        file_data["timelines"][UNKNOWN_TIMELINE_ID]["kind"] = "MARKER_TIMELINE"
        assert find_unknown_timeline_kinds(file_data) == {}

    def test_file_not_modified_after_open(self, tilia, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        tl_data = tests.utils.get_dummy_timeline_data()
        file_data["timelines"] = tl_data
        file_path = tmp_path / "test.tla"
        file_path.write_text(json.dumps(file_data))

        tilia.on_clear()
        commands.execute("file.open", file_path)
        assert not tilia.file_manager.is_file_modified(tilia.file_manager.file.__dict__)

    def test_default_slider_timeline_reflected_in_baseline(self, tilia, tmp_path):
        file_data = tests.utils.get_blank_file_data()
        file_data["timelines"] = tests.utils.get_dummy_timeline_data()  # no slider
        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(json.dumps(file_data))

        commands.execute("file.open", tmp_file)

        assert not tilia.is_file_modified()

    def test_open_file_with_custom_metadata_fields(self, tilia, tmp_path):
        file_data = """{
  "file_path": "C:/Programa\u00e7\u00e3o/TiLiA/tests/test_metadata_custom_fields.tla",
  "media_path": "",
  "media_metadata": {
    "test_field1": "a",
    "test_field2": "b",
    "test_field3": "c"

  },
  "timelines": {
    "0": {
      "is_visible": true,
      "ordinal": 0,
      "height": 25,
      "kind": "Slider",
      "components": {}
    }
  },
  "app_name": "TiLiA",
  "version": "0.0.1"
}"""

        tmp_file = tmp_path / "test.tla"
        tmp_file.write_text(file_data, encoding="utf-8")
        commands.execute("file.open", tmp_file)

        assert list(tilia.file_manager.file.media_metadata.items()) == [
            ("test_field1", "a"),
            ("test_field2", "b"),
            ("test_field3", "c"),
        ]

    def test_open_saving_changes(self, tilia, tls, marker_tlui, tmp_path):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            commands.execute("file.save")

        # make change

        commands.execute("timeline.marker.add")
        prev_tl_id = marker_tlui.id
        prev_marker_id = marker_tlui[0].id

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, True)):
            commands.execute("file.open", tmp_file)

        with open(previous_path, "r", encoding="utf-8") as f:
            contents = json.load(f)  # read contents

        assert len(tls) == 2  # assert load was successful
        assert (
            contents["timelines"][str(prev_tl_id)]["components"][str(prev_marker_id)][
                "time"
            ]
            == 0
        )

    def test_open_without_saving_changes(self, tilia, tls, marker_tlui, tmp_path):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            commands.execute("file.save")

        # make change
        marker_tlui.create_marker(10)
        prev_tl_id = marker_tlui.id

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            commands.execute("file.open", tmp_file)

        with open(previous_path, "r", encoding="utf-8") as f:
            contents = json.load(f)  # read contents

        assert len(tls) == 2  # assert load was successful
        assert len(list(contents["timelines"][str(prev_tl_id)]["components"])) == 0

    def test_open_cancelling_should_save_changes_dialog(
        self, tilia, tls, marker_tlui, tmp_path
    ):
        previous_path = tmp_path / "previous.tla"
        with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, previous_path)):
            commands.execute("file.save")

        # make change
        marker_tlui.create_marker(10)

        prev_state = tilia.get_app_state()

        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (False, True)):
            commands.execute("file.open", tmp_file)

        assert len(tls) == 1  # assert file wasn't opened
        assert tilia.get_app_state() == prev_state

    def test_open_then_save(self, tmp_path, tilia_errors):
        tmp_file = tests.utils.get_tmp_file_with_dummy_timeline(tmp_path)
        commands.execute("file.open", tmp_file)
        commands.execute("file.save")
        tilia_errors.assert_no_error()


class TestUndoRedo:
    def test_undo_fails(self, tilia, qtui, tluis, tilia_errors):
        with Serve(Get.FROM_USER_STRING, (True, "test")):
            commands.execute("timelines.add.marker")

        # this will record an invalid state that will raise an exception when
        # we try to restore it
        with patch.object(tilia, "get_app_state", return_value={}):
            commands.execute("timeline.marker.add")

        # executing another command so the following redo
        # will try to restore the previous, faulty state
        # Note: this could be improved by providing a state that is actually
        # similar to a healthy state
        commands.execute("media.seek", 10)
        commands.execute("timeline.marker.add")

        commands.execute("edit.undo")

        # as the undo failed, the current state (with both markers)
        # should be recovered
        assert len(tluis[0]) == 2
        tilia_errors.assert_error()

    def test_redo_fails(self, tilia, qtui, tluis, tilia_state, tilia_errors):
        with Serve(Get.FROM_USER_STRING, (True, "test")):
            commands.execute("timelines.add.marker")

        # this will record an invalid state that will raise an exception when
        # we try to restore it
        # Note: this could be improved by providing a state that is actually
        # similar to a healthy state
        with patch.object(tilia, "get_app_state", return_value={}):
            commands.execute("timeline.marker.add")

        # going back to previous state
        commands.execute("edit.undo")

        # restoring state (this will fail)
        commands.execute("edit.redo")

        # as the redo failed, the current state (with no markers) should be recovered
        assert tluis[0].is_empty
        tilia_errors.assert_error()


class TestFileNew:
    def test_media_is_unloaded(self, tilia, qtui):
        with Serve(Get.FROM_USER_MEDIA_PATH, (True, EXAMPLE_MEDIA_PATH)):
            commands.execute("media.load.local")

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            commands.execute("file.new")

        assert get(Get.MEDIA_DURATION) == 0
        assert not tilia.player.media_path

    def test_player_toolbar_is_disabled(self, tilia, qtui):
        with Serve(Get.FROM_USER_MEDIA_PATH, (True, EXAMPLE_MEDIA_PATH)):
            commands.execute("media.load.local")

        assert qtui.player_toolbar.isEnabled()

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            commands.execute("file.new")

        assert not qtui.player_toolbar.isEnabled()

    def test_all_windows_are_closed(self, tilia, qtui):
        for kind in WindowKind:
            post(Post.WINDOW_OPEN, kind)

        with Serve(Get.FROM_USER_SHOULD_SAVE_CHANGES, (True, False)):
            commands.execute("file.new")

        # this doesn't actually check if windows are closed
        # it checks if app._windows[kind] is None.
        # Those should be equivalent, if everything is working as it should
        assert not any(qtui.is_window_open(k) for k in WindowKind)


class TestRelativePaths:
    def test_path_exists(self, tmp_path):
        existing_path = tmp_path / "previous.file"
        existing_path.mkdir()
        assert get(Get.VERIFIED_PATH, str(existing_path)) == str(existing_path)

    def test_path_nonexistent(self, tilia, tmp_path):
        tilia.old_file_path = Path()
        tilia.cur_file_path = tmp_path
        not_a_path = tmp_path / "nonexistent.file"
        assert get(Get.VERIFIED_PATH, str(not_a_path)) == ""

    @pytest.mark.parametrize(
        "tla,media",
        [
            ("tilia.tla", "music.mp3"),
            ("folderName/tilia.tla", "music.mp3"),
            ("folderName/tilia.tla", "folderName/music.mp3"),
            ("folderName/tilia.tla", "folderName/media/music.mp3"),
            ("folderName/files/tilia.tla", "music.mp3"),
            ("folderName/files/tilia.tla", "folderName/music.mp3"),
            ("folderName/files/tilia.tla", "folderName/media/music.mp3"),
            ("folderName/files/tilia.tla", "folderName/files/media/music.mp3"),
            ("folderName/files/tilia.tla", "folderName/files/media/audio/music.mp3"),
        ],
    )
    def test_moving_files(self, tla, media, tilia, qtui, tmp_path):
        # create tla and media in old folder
        old_folder = tmp_path / "old" / "folder"
        old_tla = old_folder / tla
        old_tla.parent.mkdir(parents=True, exist_ok=True)
        old_media = old_folder / media
        old_media.parent.mkdir(parents=True, exist_ok=True)
        old_media.write_bytes(
            Path(EXAMPLE_MEDIA_PATH).read_bytes()
        )  # copy example media

        # load media
        load_local_media(old_media.resolve())

        # save tla
        with patch_file_dialog(True, [str(old_tla.resolve())]):
            commands.execute("file.save_as")

        tilia.on_clear()  # unload media

        # move tla and media to new folder
        new_folder = tmp_path / "the" / "new" / "one"
        (new_folder / tla).parent.mkdir(parents=True, exist_ok=True)
        (new_folder / media).parent.mkdir(parents=True, exist_ok=True)
        new_tla = old_tla.rename(new_folder / tla)
        new_media = old_media.rename(new_folder / media)

        # open file at new folder
        with patch_file_dialog(True, [str(new_tla)]):
            commands.execute("file.open")

        assert tilia.player.media_path == str(new_media)


class TestSave:
    def test_youtube_url_is_preserved(self, tilia_state, qtui, tmp_path):
        url = EXAMPLE_YOUTUBE_URL
        load_youtube_media(url)

        assert get(Get.MEDIA_PATH) == url

        save_path = tmp_path / "test.tla"
        with patch_file_dialog(True, [str(save_path.resolve())]):
            commands.execute("file.save_as")

        with open(save_path) as f:
            contents = json.load(f)

        assert contents["media_path"] == url

    # TODO: add tests for saving paths as Posix paths


class TestIDs:
    @staticmethod
    def assert_ids_are_unique(tls, expected_id_count: int):
        timeline_ids = {tl.id for tl in tls}
        component_ids = set()
        for tl in tls:
            for component in tl:
                component_ids.add(component.id)

        assert len(timeline_ids.union(component_ids)) == expected_id_count

    @staticmethod
    def create_timelines_and_components(timeline_count: int, component_count: int):
        """Helper function to create timelines and components in loops."""
        for _ in range(timeline_count):
            commands.execute("timelines.add.marker", name="")
            for j in range(component_count):
                commands.execute("timeline.marker.add", time=j)

    def test_timeline_ids_are_unique(self, tls, tluis):
        timeline_count = 100
        self.create_timelines_and_components(timeline_count, 0)
        self.assert_ids_are_unique(tls, timeline_count)

    def test_timeline_component_ids_are_unique(self, tls, tluis):
        component_count = 100
        self.create_timelines_and_components(1, component_count)
        assert len({c.id for c in tls[0]}) == component_count

    def test_ids_are_unique_between_timeline_and_components(self, tls, tluis):
        timeline_count = 10
        component_count = 10
        self.create_timelines_and_components(timeline_count, component_count)

        self.assert_ids_are_unique(
            tls, (timeline_count * component_count) + timeline_count
        )

    def test_are_unique_between_files_only_timelines(self, tls, tluis, tmp_path):
        self.create_timelines_and_components(10, 0)
        save_and_reopen(tmp_path)
        self.create_timelines_and_components(10, 0)
        self.assert_ids_are_unique(tls, 21)  # 20 marker timelines + 1 slider timeline

    def test_are_unique_between_files_timelines_and_components(
        self, tls, tluis, tmp_path
    ):
        self.create_timelines_and_components(5, 5)
        save_and_reopen(tmp_path)
        self.create_timelines_and_components(5, 5)
        self.assert_ids_are_unique(
            tls, 61
        )  # 10 marker timelines + 1 slider timeline + 50 components

    def test_create_component_with_higher_id_before_lower_id(self, marker_tl):
        marker_tl.create_component(ComponentKind.MARKER, time=0, id=10)
        marker_tl.create_component(ComponentKind.MARKER, time=1, id=1)
        marker_tl.create_component(ComponentKind.MARKER, time=2)

        assert [c.id for c in marker_tl.components] == ["10", "1", "11"]

    def test_create_component_with_duplicate_ids(self, marker_tl):
        marker_tl.create_component(ComponentKind.MARKER, time=0)  # id=1; tl has id=0
        marker_tl.create_component(ComponentKind.MARKER, time=1, id=1)
        marker_tl.create_component(ComponentKind.MARKER, time=2, id=1)

        assert [c.id for c in marker_tl.components] == ["1", "2", "3"]

    @pytest.mark.parametrize("id", ["not an int", 3.1415, False])
    def test_invalid_id(self, marker_tl, id):
        with PatchPost("tilia.errors", Post.DISPLAY_ERROR) as error:
            marker_tl.create_component(ComponentKind.MARKER, time=1, id=id)
        error.assert_called()
        assert marker_tl.components[0].id == "1"


class TestWindowTitle:
    @staticmethod
    def assert_window_title(qtui, title: str):
        assert qtui.window_title == f"{title} - {tilia.constants.APP_NAME}"

    @staticmethod
    def assert_window_title_is_default(qtui):
        assert qtui.window_title == qtui.DEFAULT_WINDOW_TITLE

    @staticmethod
    def set_media_title(value: str):
        post(Post.MEDIA_METADATA_FIELD_SET, "title", value)

    def test_is_default_by_default(self, qtui):
        self.assert_window_title_is_default(qtui)

    def test_is_file_title_after_file_save_if_title(self, qtui, tmp_path, tilia_state):
        file_title = "My Test Song"
        self.set_media_title(file_title)
        save_tilia_to_tmp_path(tmp_path, "test_window_title.tla")
        self.assert_window_title(qtui, file_title)

    def test_is_title_after_title_is_set(self, qtui, tilia_state):
        file_title = "My Title"
        self.set_media_title(file_title)
        self.assert_window_title(qtui, file_title)

    def test_reverts_to_default_if_title_becomes_empty(self, qtui, tilia_state):
        file_title = "Temporary Title"
        self.set_media_title(file_title)
        self.assert_window_title(qtui, file_title)

        self.set_media_title("")
        self.assert_window_title_is_default(qtui)

    def test_is_filename_after_file_save_if_no_title(self, qtui, tmp_path):
        save_tilia_to_tmp_path(tmp_path, "test_window_title.tla")
        self.assert_window_title(qtui, "test_window_title.tla")

    def test_is_title_after_file_save_if_title(self, qtui, tmp_path):
        file_title = "Should Be This"
        self.set_media_title(file_title)
        save_tilia_to_tmp_path(tmp_path, "Should Not Be This.tla")
        self.assert_window_title(qtui, file_title)

    def test_is_default_after_new_file(self, qtui, tmp_path):
        save_tilia_to_tmp_path(tmp_path, "test_window_title.tla")
        commands.execute("file.new")
        self.assert_window_title_is_default(qtui)

    def test_reopening_file_updates_title(self, qtui, tmp_path):
        file_title = "A TiLiA File Title"
        self.set_media_title(file_title)
        path = save_tilia_to_tmp_path(tmp_path)

        commands.execute("file.new")
        self.assert_window_title_is_default(qtui)

        commands.execute("file.open", path)
        self.assert_window_title(qtui, file_title)

    def test_is_filename_after_file_load_if_no_title(self, qtui, tmp_path):
        save_tilia_to_tmp_path(tmp_path, "test_window_title.tla")
        self.assert_window_title(qtui, "test_window_title.tla")

    def test_is__title_after_load_if_title(self, qtui, tmp_path, tilia_state):
        file_title = "Loaded Song Title"
        self.set_media_title(file_title)
        save_tilia_to_tmp_path(tmp_path)
        self.assert_window_title(qtui, file_title)

    def test_is_filename_if_title_is_set_to_empty_but_file_has_been_saved(
        self, qtui, tmp_path
    ):
        file_title = "Yet Another Title"
        file_name = "should_revert_to_this.tla"

        self.set_media_title(file_title)
        save_tilia_to_tmp_path(tmp_path, file_name)

        self.set_media_title("")
        self.assert_window_title(qtui, file_name)
