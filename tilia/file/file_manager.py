from __future__ import annotations

import json
from pathlib import Path

import tilia.constants
import tilia.errors
from tilia.exceptions import (
    MediaMetadataFieldAlreadyExists,
    MediaMetadataFieldNotFound,
    NoReplyToRequest,
)
from tilia.file.common import are_tilia_data_equal, write_tilia_file_to_disk
from tilia.file.media_metadata import MediaMetadata
from tilia.file.migration import (
    find_unknown_timeline_kinds,
    is_from_newer_version,
    migrate,
)
from tilia.file.tilia_file import TiliaFile, validate_tla_data
from tilia.requests import Get, Post, get, listen, post, serve
from tilia.settings import settings
from tilia.timelines.hash_timelines import hash_function
from tilia.ui import commands

OPEN_FILE_NEWER_VERSION_TITLE = "Open file from a newer version?"
OPEN_FILE_NEWER_VERSION_PROMPT = (
    "This file was created with TiLiA {} but you are running {}.\n"
    "Errors may occur, and saving could permanently discard data that this "
    "version doesn't understand.\n\n"
    "Open it anyway?"
)


def _pop_unknown_timelines(data: dict, unknown_kinds: dict) -> dict:
    return {id: data["timelines"].pop(id) for id in unknown_kinds}


def _ensure_components_hash(timelines: dict) -> dict:
    """Fills in a ``"components_hash"`` for any entry missing one, mutating
    and returning ``timelines``.

    A raw timeline entry that was popped and kept as unknown never goes
    through ``Timeline.get_state()`` (it's never turned into a live
    component tree), so it lacks the ``"components_hash"`` key every other
    entry in ``file.timelines`` has. ``are_tilia_data_equal`` reads that key
    unconditionally when checking "is the file modified", so a missing one
    would raise ``KeyError`` the moment an ignored timeline is present.
    """
    for timeline in timelines.values():
        if "components_hash" not in timeline:
            timeline["components_hash"] = hash_function(
                json.dumps(timeline.get("components", {}), sort_keys=True)
            )
    return timelines


def _compact_ordinals(timelines: dict) -> None:
    """Renumbers ``"ordinal"`` to a dense ``1..N`` sequence in place,
    preserving relative order.

    Needed after popping unknown-kind timelines: leaving a gap (e.g. 1, 3
    after removing ordinal 2) means the next auto-assigned ordinal
    (``len(timelines) + 1``) can land back on an ordinal that's still in
    use, since that count no longer matches the highest ordinal in play.
    """
    ordered = sorted(timelines.items(), key=lambda item: item[1].get("ordinal", 0))
    for new_ordinal, (_, timeline) in enumerate(ordered, start=1):
        timeline["ordinal"] = new_ordinal


def open_tla(file_path: str | Path) -> tuple[bool, TiliaFile | None, Path | None]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        tilia.errors.display(tilia.errors.OPEN_FILE_NOT_FOUND, file_path)
        return False, None, None
    except json.decoder.JSONDecodeError:
        tilia.errors.display(
            tilia.errors.OPEN_FILE_INVALID_TLA,
            file_path,
            "File is not valid JSON.",
        )
        return False, None, None

    valid, reason = validate_tla_data(data)
    if not valid:
        tilia.errors.display(tilia.errors.OPEN_FILE_INVALID_TLA, file_path, reason)
        return False, None, None

    if is_from_newer_version(data):
        proceed = get(
            Get.FROM_USER_YES_OR_NO,
            OPEN_FILE_NEWER_VERSION_TITLE,
            OPEN_FILE_NEWER_VERSION_PROMPT.format(
                data.get("version", "?"), tilia.constants.VERSION
            ),
        )
        if not proceed:
            return False, None, None

    data, _ = migrate(data)

    unknown_kinds = find_unknown_timeline_kinds(data)
    ignored_timelines = {}
    deleted_timelines = {}
    if unknown_kinds:
        proceed, delete = get(
            Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION, list(unknown_kinds.values())
        )
        if not proceed:
            return False, None, None
        popped = _ensure_components_hash(_pop_unknown_timelines(data, unknown_kinds))
        _compact_ordinals(data["timelines"])
        if delete:
            deleted_timelines = popped
        else:
            ignored_timelines = popped

    old_path = Path(data["file_path"])

    data["file_path"] = (
        file_path if isinstance(file_path, str) else str(file_path.resolve())
    )
    return (
        True,
        (
            TiliaFile(
                **data,
                unknown_timelines=ignored_timelines,
                deleted_timelines=deleted_timelines,
            )
        ),
        old_path,
    )


class FileManager:
    FILE_ATTRIBUTES_TO_CHECK_FOR_MODIFICATION = [
        "media_metadata",
        "timelines",
        "media_path",
        "timelines_hash",
    ]

    def __init__(self):
        # _saved_metadata is a snapshot of media_metadata at the last
        # save/load. It is needed because self.file.media_metadata is
        # mutated in place by on_set_media_metadata_field (#377), so
        # comparing it to the current state — which is also the same
        # mutated object — never reports any change. The snapshot is
        # refreshed by the file setter below and by save().
        self._saved_metadata: dict = {}
        self._setup_requests()
        self._setup_commands()
        self._setup_file()

    @property
    def file(self) -> TiliaFile:
        return self._file

    @file.setter
    def file(self, value: TiliaFile) -> None:
        self._file = value
        self.resync_saved_metadata()

    def _setup_requests(self):
        LISTENS = {
            (Post.PLAYER_URL_CHANGED, self.on_player_url_changed),
            (Post.FILE_MEDIA_DURATION_CHANGED, self.on_player_duration_changed),
            (Post.REQUEST_SAVE_TO_PATH, self.on_save_to_path_request),
            (
                Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH,
                self.on_import_media_metadata_request,
            ),
            (Post.MEDIA_METADATA_FIELD_SET, self.on_set_media_metadata_field),
            (Post.MEDIA_METADATA_FIELD_ADD, self.on_add_media_metadata_field),
            (Post.METADATA_UPDATE_FIELDS, self.on_update_media_metadata_fields),
        }

        SERVES = {
            (Get.MEDIA_METADATA, lambda: self.file.media_metadata),
            (
                Get.MEDIA_METADATA_REQUIRED_FIELDS,
                self.get_media_metadata_required_fields,
            ),
            (Get.MEDIA_TITLE, lambda: self.file.media_metadata.get("title", "")),
            (Get.FILE_PATH, lambda: self.file.file_path),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

        for request, callback in SERVES:
            serve(self, request, callback)

    def _setup_commands(self):

        commands.register(
            "file.new",
            self.on_request_new_file,
            "&New...",
            "Ctrl+N",
        )

        commands.register(
            "file.save",
            self.on_save_request,
            "&Save",
            "Ctrl+S",
        )

        commands.register(
            "file.save_as",
            self.on_save_as_request,
            "Save &As...",
            "Ctrl+Shift+S",
        )

    def _setup_file(self):
        self.file = TiliaFile()

    def on_save_request(self):
        """Saves tilia file to current file path."""
        app_state = get(Get.APP_STATE)
        if not app_state.get("file_path"):
            # in case file has not been saved before
            return self.on_save_as_request()

        path = app_state.get("file_path")
        if not path:
            tilia.errors.display(
                tilia.errors.FILE_SAVE_FAILED, "Could not get file path."
            )
            return False

        try:
            self.save(app_state, path)
        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))
            return False

        post(Post.FILE_SAVED, path)
        return True

    def on_save_as_request(self, path: str | None = None):
        """Prompts user for a path, and saves tilia file to it."""
        old_title = get(Get.MEDIA_TITLE)
        if path is None:
            accepted, path = get(Get.FROM_USER_SAVE_PATH_TILIA, old_title + ".tla")
            if not accepted:
                return False

        save_title = Path(path).stem
        try:
            if old_title == MediaMetadata.REQUIRED_FIELDS.get("title"):
                self.on_set_media_metadata_field("title", save_title)

            self.save(get(Get.APP_STATE), path)

        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))

            if save_title != old_title:
                self.on_set_media_metadata_field("title", old_title)
            return False

        post(Post.FILE_SAVED, path)
        return True

    def on_save_to_path_request(self, path: Path):
        """Saves tilia file to specified path."""
        try:
            self.save(get(Get.APP_STATE), path)
        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))

        post(Post.FILE_SAVED, path)

    def on_close_modified_file(self):
        success, should_save = self.ask_save_changes_if_modified()
        if not success:
            return False
        if should_save:
            was_saved = self.on_save_request()
            if not was_saved:  # user might cancel save dialog
                return False  # we shouldn't proceed in that case

        return True

    def on_request_new_file(self):
        if not self.on_close_modified_file():
            return

        post(Post.APP_CLEAR)
        post(Post.APP_SETUP_FILE)

    def on_set_media_metadata_field(self, field_name: str, value: str) -> None:
        """Sets the value of a single media metadata field."""
        if field_name not in self.file.media_metadata:
            raise MediaMetadataFieldNotFound(f"Field {field_name} not found.")

        self.file.media_metadata[field_name] = value
        if field_name == "title":
            post(Post.MEDIA_METADATA_TITLE_UPDATED, value)

    def on_add_media_metadata_field(self, field_name: str) -> None:
        """Adds a new media metadata field."""
        if field_name in self.file.media_metadata:
            raise MediaMetadataFieldAlreadyExists(f"Field {field_name} already exists.")
        self.file.media_metadata[field_name] = ""

    def on_update_media_metadata_fields(self, fields: list) -> None:
        new_metadata = {}
        for field in fields:
            value = self.file.media_metadata.get(
                field, self.file.media_metadata.get(field.lower(), "")
            )
            new_metadata[field] = value

        self.set_media_metadata(MediaMetadata.from_dict(new_metadata))

    def on_import_media_metadata_request(self, path: Path | str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.decoder.JSONDecodeError as err:
            tilia.errors.display(
                tilia.errors.MEDIA_METADATA_IMPORT_JSON_FAILED, path, repr(err)
            )
            return
        except FileNotFoundError:
            tilia.errors.display(tilia.errors.MEDIA_METADATA_IMPORT_FILE_FAILED, path)
            return

        self.set_media_metadata(MediaMetadata.from_dict(data))

    @staticmethod
    def get_media_metadata_required_fields():
        return list(MediaMetadata.REQUIRED_FIELDS)  # REQUIRED_FIELDS is a dict

    def save(self, data: dict, path: Path | str):
        data["file_path"] = str(path.resolve()) if isinstance(path, Path) else path
        # Going through the setter refreshes _saved_metadata.
        self.file = TiliaFile(**data, unknown_timelines=self.file.unknown_timelines)
        write_tilia_file_to_disk(self.file, str(path))

        try:
            geometry, window_state = get(Get.WINDOW_GEOMETRY), get(Get.WINDOW_STATE)
            zoom = get(Get.CURRENT_ZOOM)
        except NoReplyToRequest:
            geometry, window_state, zoom = None, None, None
        settings.update_recent_files(path, geometry, window_state, zoom)

    def new(self):
        self._setup_file()

    def resync_saved_metadata(self) -> None:
        self._saved_metadata = dict(self.file.media_metadata)

    def is_file_modified(self, current_data: dict) -> bool:
        # are_tilia_data_equal can't detect media_metadata changes
        # because the live and "saved" metadata are the same mutated
        # object on self.file (#377). Use the snapshot taken on the
        # last save/load instead.
        if dict(current_data["media_metadata"]) != self._saved_metadata:
            return True
        return not are_tilia_data_equal(current_data, self.file.__dict__)

    def on_player_url_changed(self, path: str | Path) -> None:
        self.file.media_path = str(path)

    def on_player_duration_changed(
        self, duration: float, is_confirmation: bool = False
    ) -> None:
        self.file.media_metadata["media length"] = duration
        if is_confirmation:
            # The player is confirming the duration of media that already
            # belongs to the current file (App posts this while
            # should_scale_timelines == "keep", e.g. right after opening a
            # file — see #453) rather than reporting a user-driven change.
            # Keep the snapshot in sync so it isn't flagged as an edit.
            self._saved_metadata["media length"] = duration

    def set_media_metadata(self, value: MediaMetadata):
        self.file.media_metadata = value

    def set_media_duration(self, value: float):
        self.file.media_metadata["media length"] = value

    def set_timelines(self, state: dict, hash: str):
        self.file.timelines = state
        self.file.timelines_hash = hash

    def update_file(self, data: dict):
        """Directly updates the file manager's file, bypassing opening."""
        self.file = TiliaFile(**data)

    def get_file_path(self):
        return self.file.file_path

    def ask_save_changes_if_modified(self):
        if not self.is_file_modified(get(Get.APP_STATE)):
            return True, False

        return get(Get.FROM_USER_SHOULD_SAVE_CHANGES)
