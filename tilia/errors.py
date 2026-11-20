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
METADATA_FIELD_INVALID = Error(
    "Invalid metadata field",
    "The following fields contain non-alphanumeric characters and will not be added:\n{}",
)
IMPORT_FAILED = Error("Import failed", "Import failed:\n{}")
IMPORT_SUCCESS_ERRORS = Error(
    "Import",
    "Import was successful, but some components may not have been imported.\nThe following errors occurred:\n{}",
)
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
ADD_MODE_FAILED = Error("Add key failed", "Adding key failed: {}.")
ADD_HARMONY_FAILED = Error("Add harmony failed", "{}")
# Typed in the Add harmony dialog, or in a row of a CSV import, after a mode whose
# tonic TiLiA can't read (TimeLineAnnotator/project-management#595, point 3): the
# time, then the roman numeral as given.
ROMAN_NUMERAL_KEY_UNREADABLE = Error(
    "Add harmony",
    "TiLiA can't read the key at {}, so the roman numeral '{}' can't be placed."
    " Set a mode TiLiA can read before it, or enter the chord by its letters.",
)
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
COMPONENTS_PASTE_ERROR = Error("Paste components error", "{}")
FILE_NOT_FOUND = Error(
    "File not found", "No such file or directory. '{}' could not be opened."
)
LOOP_DISJUNCT = Error("Loop Selection Error", "Selected Hierarchies are disjunct.")
PLAYER_TOOLBAR_ERROR = Error("Updating Player Toolbar", "{}")
YOUTUBE_PLAYER_ERROR = Error("YouTube Player Error", "{}")
METADATA_FIELD_NOT_FOUND = Error("Metadata field not found", "Field '{}' not found.")

CLI_METADATA_CANT_SET_MEDIA_LENGTH = Error(
    "Cannot set media length",
    "Cannot set media length with 'metadata set'. Use 'metadata set-media-length' instead.",
)
EMPTY_CLI_SCRIPT = Error("Script error", "Cannot run script: file '{}' is empty.")
CLI_CREATE_TIMELINE_WITHOUT_DURATION = Error(
    "Cannot create timeline",
    "No media loaded and no duration set. Load a media file with 'load-media' or set a duration with 'metadata set-media-length'.",
)
CLI_ADD_TIMELINE_ARG_NOT_APPLICABLE = Error(
    "Invalid argument",
    "'{}' is not valid for timeline kind '{}'.",
)
OPEN_FILE_NOT_FOUND = Error("File not found", "File '{}' not found.")
OPEN_FILE_INVALID_TLA = Error(
    "Invalid file type", "File '{}' is not a valid .tla file. {}"
)
OPEN_FILE_NEWER_FORMAT = Error(
    "Open file",
    "'{}' was written by a newer version of TiLiA (format {})."
    " Update TiLiA to open it.",
)
OPEN_FILE_DRAFT_FORMAT = Error(
    "Open file",
    "'{}' is in a draft of TiLiA's file format ({}), which this version can't"
    " open. Convert it again from its sources.",
)
OPEN_FILE_IN_QUARTERS = Error(
    "Open file",
    "'{}' measures its times in quarter notes, which this version of TiLiA"
    " can't show yet.",
)
# The warnings a file opens with (FR-061): not an error, so `display` doesn't show
# them. TiLiA's window and its command line show the message, then one line each.
OPEN_FILE_PROBLEMS = Error(
    "Problems in this file",
    "'{}' has {} problems. TiLiA keeps them as they are, and saves them unchanged"
    " until you fix them.",
)
# One: only the noun changes (TimeLineAnnotator/project-management#597, point 1).
OPEN_FILE_ONE_PROBLEM = Error(
    "Problems in this file",
    "'{}' has 1 problem. TiLiA keeps them as they are, and saves them unchanged"
    " until you fix them.",
)
LOAD_FILE_ERROR = Error("Load file error", "File '{}' could not be loaded. \n{}")
# A file that fails to load part-way, once the file open before is cleared, which
# can't be given back: its unsaved changes are in the autosave copy TiLiA wrote
# before clearing it. The file's name, then the copy's path.
OPEN_FILE_NOT_GIVEN_BACK = Error(
    "Open file",
    "'{}' could not be loaded, and the file open before could not be given back."
    " Its unsaved changes are in an autosave copy: '{}'.",
)
# An action the core's rules refuse (FR-062, FR-070): the message is the rule's
# reason, as the core gives it.
EDIT_REFUSED = Error("Can't make this change", "{}")
UNDO_FAILED = Error(
    "Undo failed",
    "Undo failed. TiLiA encountered an error while undoing the last command.\n{}",
)
COMMAND_FAILED = Error(
    "Command failed",
    "Something went wrong when executing the last command.\nCommand={}\n\n{}",
)
INVALID_RETURN_VALUES_FOR_COMMAND = Error(
    "Invalid return values for command",
    "Invalid return values for command: {}\nValues: {}",
)
SCORE_SVG_CREATE_ERROR = Error("Error creating SVG", "{}")
INVALID_MEASURE_FRACTION = Error(
    "Invalid measure fraction",
    "Measure fraction '{}' is not valid. Using closest valid value.",
)
SCORE_STAFF_ID_ERROR = Error(
    "Error creating score timeline",
    "Duplicate or missing staff numbers. Staff numbers found: {}.\nDeleting timeline.",
)
RANGE_DRAG_INVALID_HANDLE = Error(
    "Range drag error", "Could not start drag: unrecognized handle item."
)
RANGE_INVALID_ROW_COLOR = Error("Invalid row color", "'{}' is not a valid color.")
AMBIGUOUS_SHORTCUT = Error(
    "Ambiguous keyboard shortcut",
    "Two or more commands are bound to the same key combination. "
    "Qt could not decide which to fire. Please report this:\n\n{}",
)
VELOPACK_UPDATE_FAILED = Error("Update failed", "{}")
GIT_PULL_FAILED = Error("Pull failed", "{}")


def problems_message(name: str, count: int) -> str:
    """What TiLiA says of the `count` warnings the file `name` opened with."""
    if count == 1:
        return OPEN_FILE_ONE_PROBLEM.message.format(name)
    return OPEN_FILE_PROBLEMS.message.format(name, count)


def display(error: Error, *args):
    post(Post.DISPLAY_ERROR, error.title, error.message.format(*args))
