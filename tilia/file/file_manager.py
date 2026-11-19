from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import tilia.errors
from tilia.exceptions import (
    MediaMetadataFieldAlreadyExists,
    MediaMetadataFieldNotFound,
    NoReplyToRequest,
)
from tilia.file.common import are_tilia_data_equal
from tilia.file.media_metadata import MediaMetadata
from tilia.file.open_document import OpenDocument
from tilia.file.tla_bridge import TIMELINE_KINDS
from tilia.requests import Get, Post, get, listen, post, serve
from tilia.settings import settings
from tilia.ui import commands
from tilia_core import tla

_MEDIA_LENGTH = "media length"


def read_file(path: Path) -> OpenDocument | None:
    """The file at `path`, read through the core. None when it isn't opened: the
    core or the system refused it, and TiLiA has said why, or the user cancelled.
    Nothing is changed then."""
    name = path.name
    try:
        document = tla.read(path)
    except FileNotFoundError:
        tilia.errors.display(tilia.errors.OPEN_FILE_NOT_FOUND, path)
        return None
    except OSError as error:
        tilia.errors.display(
            tilia.errors.LOAD_FILE_ERROR, path, error.strerror or error
        )
        return None
    except tla.NewerFormat as error:
        tilia.errors.display(tilia.errors.OPEN_FILE_NEWER_FORMAT, name, error.version)
        return None
    except tla.DraftFormat as error:
        tilia.errors.display(tilia.errors.OPEN_FILE_DRAFT_FORMAT, name, error.version)
        return None
    except tla.UnreadableFile as error:
        tilia.errors.display(tilia.errors.OPEN_FILE_INVALID_TLA, name, _reason(error))
        return None

    if document.time_unit == "quarters":
        tilia.errors.display(tilia.errors.OPEN_FILE_IN_QUARTERS, name)
        return None

    discarded = False
    unknown = [
        timeline
        for timeline in document.timelines.values()
        if timeline.kind not in TIMELINE_KINDS.values()
    ]
    if unknown:
        proceed, discarded = get(
            Get.FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION,
            [_kind_name(timeline.kind) for timeline in unknown],
        )
        if not proceed:
            return None
        if discarded:
            for timeline in unknown:
                del document.timelines[timeline.id]

    fields = {
        **copy.deepcopy(document.metadata),
        "media length": document.media_length or 0,
    }
    return OpenDocument(
        document=document,
        file_path=str(path.resolve()),
        media_metadata=MediaMetadata.from_dict(fields),
        unknown_discarded=discarded,
    )


def _reason(error: tla.UnreadableFile) -> str:
    """The core's reason, without the file's name, which the message gives."""
    if error.line is None:
        return error.message
    return f"line {error.line}: {error.message}"


def _kind_name(kind: tla.UnknownKind | str) -> str:
    """As the file spells it."""
    return kind.spelling if isinstance(kind, tla.UnknownKind) else kind


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
    def file(self) -> OpenDocument:
        return self._file

    @file.setter
    def file(self, value: OpenDocument) -> None:
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
        self.file = OpenDocument()

    def on_save_request(self):
        """Saves tilia file to current file path."""
        path = self.file.file_path
        if not path:
            # in case file has not been saved before
            return self.on_save_as_request()

        try:
            self.save(path)
        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))
            return False

        post(Post.FILE_SAVED, path)
        return True

    def on_save_as_request(self, path: str | None = None):
        """Prompts user for a path, and saves tilia file to it. The file's title stays
        as it is: one opened without a title gets none (FR-008)."""
        if path is None:
            accepted, path = get(
                Get.FROM_USER_SAVE_PATH_TILIA, get(Get.MEDIA_TITLE) + ".tla"
            )
            if not accepted:
                return False

        try:
            self.save(path)
        except Exception as exc:
            tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, repr(exc))
            return False

        post(Post.FILE_SAVED, path)
        return True

    def on_save_to_path_request(self, path: Path):
        """Saves tilia file to specified path."""
        try:
            self.save(path)
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
        self.sync_document()

    def on_add_media_metadata_field(self, field_name: str) -> None:
        """Adds a new media metadata field."""
        if field_name in self.file.media_metadata:
            raise MediaMetadataFieldAlreadyExists(f"Field {field_name} already exists.")
        self.file.media_metadata[field_name] = ""
        self.sync_document()

    def on_update_media_metadata_fields(
        self, fields: list, renamed_fields: dict[str, str] | None = None
    ) -> None:
        """`renamed_fields` maps old field name -> new field name, for fields
        that were renamed rather than removed/added (see MediaMetadataWindow.
        update_metadata_fields, the only place both the old and new field
        lists are available to tell the two cases apart)."""
        new_name_to_old_name = {new: old for old, new in (renamed_fields or {}).items()}
        new_metadata = {}
        for field in fields:
            lookup_name = new_name_to_old_name.get(field, field)
            value = self.file.media_metadata.get(
                lookup_name, self.file.media_metadata.get(lookup_name.lower(), "")
            )
            new_metadata[field] = value

        self.set_media_metadata(MediaMetadata.from_dict(new_metadata))
        self.sync_document()

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

        fields = MediaMetadata.from_dict(data)
        if _MEDIA_LENGTH not in data:
            # The media length isn't a field (FR-035): an import never resets it.
            fields[_MEDIA_LENGTH] = self.file.media_metadata.get(_MEDIA_LENGTH, 0)
        self.set_media_metadata(fields)
        self.sync_document()

    def sync_document(self) -> None:
        """Makes the document follow an edit of the file's fields, a person's edit
        that records nothing for undo, so that an autosave in between writes it."""
        self.file.sync(get(Get.APP_STATE))

    @staticmethod
    def get_media_metadata_required_fields():
        return list(MediaMetadata.REQUIRED_FIELDS)  # REQUIRED_FIELDS is a dict

    def save(self, path: Path | str) -> None:
        """Writes the document open to `path` through the core, once it follows
        TiLiA's state. Raises what the core raises, having written nothing: the
        document then still follows TiLiA's state, and the file reads as modified."""
        state = get(Get.APP_STATE)
        self.file.sync(state)
        # The document read, or the new one: never one built again from the state,
        # which would have no fingerprint for the check before saving.
        self.file.write(path)
        # The file open is now the one written, and the document follows it.
        self.file.file_path = Path(
            path.resolve() if isinstance(path, Path) else path
        ).as_posix()
        self.file.media_path = state["media_path"]
        self.file.timelines = state["timelines"]
        self.file.timelines_hash = state["timelines_hash"]
        self.file.unknown_discarded = False
        self.resync_saved_metadata()
        self._remember_media_place(state["media_path"])

        try:
            geometry, window_state = get(Get.WINDOW_GEOMETRY), get(Get.WINDOW_STATE)
            zoom = get(Get.CURRENT_ZOOM)
        except NoReplyToRequest:
            # No UI is listening (e.g. CLI usage or tests without a full
            # Qt UI set up), so there's nothing to persist here.
            geometry, window_state, zoom = None, None, None
        try:
            current_time = get(Get.MEDIA_CURRENT_TIME)
        except NoReplyToRequest:
            current_time = None
        settings.update_recent_files(
            path, geometry, window_state, zoom, time=current_time
        )

    def _remember_media_place(self, media_path: str) -> None:
        """At a save, remembers `media_path`, the media TiLiA has loaded, when it is
        a local file, as where this document, storing the media path it now does,
        found its media (FR-031; TimeLineAnnotator/project-management#627). So a
        change of media that isn't saved, or is undone before saving, doesn't move
        the place."""
        if media_path and os.path.isfile(media_path):
            document = self.file.document
            settings.set_media_place(
                document.document_id,
                document.media_path,
                Path(os.path.abspath(media_path)).as_posix(),
            )

    def new(self):
        self._setup_file()

    def keep_file(self) -> tuple[OpenDocument, dict]:
        """The file open, with what tells whether it is modified, for
        `give_back_file`."""
        return self._file, dict(self._saved_metadata)

    def give_back_file(self, kept: tuple[OpenDocument, dict]) -> None:
        """Makes the file `keep_file` gave the one open again, modified as it was."""
        self._file, self._saved_metadata = kept

    def resync_saved_metadata(self) -> None:
        self._saved_metadata = dict(self.file.media_metadata)

    def is_file_modified(self, current_data: dict) -> bool:
        if self.file.unknown_discarded:
            return True
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
            # Keep the snapshot in sync so it isn't flagged as an edit, and the
            # document's stored length as it is (FR-034).
            self._saved_metadata["media length"] = duration
            self.file.note_media_length(duration)

    def set_media_metadata(self, value: MediaMetadata):
        self.file.media_metadata = value

    def set_media_duration(self, value: float):
        self.file.media_metadata["media length"] = value

    def set_timelines(self, state: dict, hash: str):
        self.file.timelines = state
        self.file.timelines_hash = hash

    def update_file(self, data: dict):
        """Directly updates the file manager's file, bypassing opening."""
        self.file = OpenDocument(**data)

    def get_file_path(self):
        return self.file.file_path

    def ask_save_changes_if_modified(self):
        if not self.is_file_modified(get(Get.APP_STATE)):
            return True, False

        return get(Get.FROM_USER_SHOULD_SAVE_CHANGES)
