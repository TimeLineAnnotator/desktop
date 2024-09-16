from typing import NamedTuple

from tilia.requests import Post, post


class Error(NamedTuple):
    title: str
    message: str


FILE_SAVE_FAILED = Error("Save file", "Error when saving file.\n{}")
MEDIA_METADATA_IMPORT_JSON_FAILED = Error(
    "Import media metadata", "Error when parsing file {}:\n{}"
)
MEDIA_METADATA_IMPORT_FILE_FAILED = Error("Import media metadata", "File {} not found.")
MEDIA_METADATA_SET_DATA_FAILED = Error(
    "Set media metadata",
    "Cannot set media metadata to {}. Media length must be a positive number.",
)
CSV_IMPORT_FAILED = Error("CSV import failed", "{}")
CREATE_TIMELINE_WITHOUT_MEDIA = Error(
    "Create timeline error", "Cannot create timeline with no media loaded."
)
UNSUPPORTED_MEDIA_FORMAT = Error(
    "Media format not supported",
    "Media file of type '.{}' not supported. Try loading a supported file type.",
)
CHANGE_MEDIA_LENGTH_WITH_MEDIA_LOADED = Error(
    "Change media length",
    "Can't change media length when a media file is loaded.",
)
MEDIA_NOT_FOUND = Error(
    "Media load error", "No media available at '{}'. Try using another path."
)
MEDIA_LOAD_FAILED = Error(
    "Media load failed", "Could not load media at '{}'. Try loading another media."
)
YOUTUBE_URL_INVALID = Error("Invalid YouTube URL", "{} is not a valid URL.")
EXPORT_AUDIO_FAILED = Error("Export Audio", "{}")
INVALID_HARMONY_INVERSION = Error(
    "Invalid harmony inversion",
    "Can't set inversion '{}' on a chord of type '{}'. Please select a valid inversion for this chord type.",
)
ADD_MODE_FAILED = Error("Add key failed", "Adding key failed: {}.")
ADD_HARMONY_FAILED = Error("Add harmony failed", "{}")
ADD_PDF_MARKER_FAILED = Error("Add page marker failed", "Can't add page marker: {}")
INVALID_PDF = Error("PDF timeline error", "Invalid PDF path: '{}'")
AUDIOWAVE_INVALID_FILE = Error(
    "Invalid file type",
    "Cannot show AudioWave on selected file. Hiding AudioWave Timeline...",
)
BEAT_DISTRIBUTION_ERROR = Error(
    "Distribute measure", "Cannot distribute beats on last measure."
)
BEAT_PATTERN_ERROR = Error(
    "Insert beat pattern", "Beat pattern must be one or more numbers."
)
HIERARCHY_CREATE_CHILD_FAILED = Error(
    "Create child hierarchy", "Create child failed: {}"
)
HIERARCHY_CHANGE_LEVEL_FAILED = Error(
    "Change hierarchy level", "Change level failed: {}"
)
HIERARCHY_GROUP_FAILED = Error("Group hierarchies", "Grouping failed: {}")
HIERARCHY_MERGE_FAILED = Error("Merge hierarchies", "Merge failed: {}")
HIERARCHY_SPLIT_FAILED = Error("Split hierarchy", "Split failed: {}")
COMPONENTS_COPY_ERROR = Error("Copy components error", "{}")
COMPONENTS_LOAD_ERROR = Error(
    "Load components error",
    "Some components were not loaded. The following errors occured:\n{}",
)
COMPONENTS_PASTE_ERROR = Error("Paste components error", "{}")
FILE_NOT_FOUND = Error(
    "File not found", "No such file or directory. '{}' could not be opened."
)
LOOP_DISJUNCT = Error("Loop Selection Error", "Selected Hierarchies are disjunct.")
PLAYER_TOOLBAR_ERROR = Error("Updating Player Toolbar", "{}")
YOUTUBE_PLAYER_ERROR = Error("Youtube Player Error", "{}")
METADATA_FIELD_NOT_FOUND = Error("Metadata field not found", "Field '{}' not found.")

CLI_METADATA_CANT_SET_MEDIA_LENGTH = Error(
    "Cannot set media length",
    "Cannot set media length with 'metadata set'. Use 'metadata set-media-length' instead.",
)
EMPTY_CLI_SCRIPT = Error("Script error", "Cannot run script: file '{}' is empty.")
CLI_CREATE_TIMELINE_WITHOUT_DURATION = Error("Cannot create timeline", "No media loaded and no duration set. Load a media file with 'load-media' or set a duration with 'metadata set-media-length'.")


def display(error: Error, *args):
    post(Post.DISPLAY_ERROR, error.title, error.message.format(*args))

