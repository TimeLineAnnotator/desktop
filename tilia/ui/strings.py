VALIDATE_BOUNDED_INTEGER = "{0} must be a value between {1} and {2}."
BEAT_PATTERN_DIALOG_TITLE = "Beat pattern"
BEAT_PATTERN_DIALOG_PROMPT = "Insert initial beat pattern (can be changed later):"
BEAT_PATTERN_DIALOG_TOOLTIP = """Empty spaces separate measures, line breaks are ignored.
Examples:
  - '5' = 5 beats per measure;
  - '4 3 3' = a cycle of 4, then 3, then 3 beats per measure."""
PROMPT_CREATE_LEVEL_BELOW_TITLE = "Create level below"
PROMPT_CREATE_LEVEL_BELOW_MESSAGE = (
    "Node is at already lowest level."
    "\nDo you want to create a new lowest level for the child?"
)
ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_TITLE = "No media loaded"
ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_PROMPT = (
    "Cannot create timeline with no media loaded. What would you like to do?"
)
ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_LOAD_MEDIA = (
    "Load a media file before adding the timeline."
)
ASK_ADD_TIMELINE_WITHOUT_MEDIA_DIALOG_SET_MEDIA_DURATION = (
    "Set the media duration manually."
)
BEAT_TIMELINE_FILL_TITLE = "Fill beat timeline"
BEAT_TIMELINE_FILL_PROMPT = "Fill this timeline:"
BEAT_TIMELINE_BY_AMOUNT_OPTION = "with"
BEAT_TIMELINE_BY_AMOUNT_SUFFIX = " beat(s)"
BEAT_TIMELINE_BY_INTERVAL_OPTION = "with beats spaced by"
BEAT_TIMELINE_BY_INTERVAL_SUFFIX = " second(s)"
BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT = (
    "This will delete existing beats. Continue?"
)
INSERT_MEASURE_ZERO_TITLE = "Insert measure zero"
INSERT_MEASURE_ZERO_PROMPT = "The selected score has a measure numbered 0, but there is no such measure at the selected beat timeline. Attempt to insert it? Measure 0 is usually a pickup measure."
INSERT_MEASURE_ZERO_FAILED = "Unable to insert measure at the start of the timeline. {}"
UTF8_DECODE_FAILED = "'{}' is not a valid UTF-8 encoded {} file."
