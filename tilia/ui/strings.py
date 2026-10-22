VALIDATE_BOUNDED_INTEGER = "{0} must be a value between {1} and {2}."
BEAT_PATTERN_DIALOG_TITLE = "Beat pattern"
BEAT_PATTERN_DIALOG_PROMPT = (
    "Beats per bar, separated by spaces. The pattern repeats after its last bar."
)
BEAT_PATTERN_DIALOG_TOOLTIP = """Examples:
  - '4' = 4 beats in every bar;
  - '4 3 3' = a cycle of 4, then 3, then 3 beats per bar;
  - '10[4] 3 15[4]' = 10 bars of 4, a bar of 3, then 15 bars of 4;
  - '2[4 3[3]]' = 4 3 3 3 4 3 3 3."""
BEAT_PATTERN_OVERWRITE_TITLE = "Overwrite bars set by hand"
BEAT_PATTERN_OVERWRITE_PROMPT = (
    "This pattern will overwrite bars set by hand (bars {})."
    "\nDo you want to continue?"
)
BEAT_UNIT_DIALOG_TITLE = "Beat unit"
BEAT_UNIT_DENOMINATOR_LABEL = "Denominator:"
BEAT_UNIT_UNITS_LABEL = "Units per tap:"
BEAT_UNIT_UNITS_TOOLTIP = """How many denominator units each tapped beat is worth.
Separate taps in a measure with '+'. Examples:
  - '1' = one unit per tap (4/4 tapped in 4);
  - '3' = three units per tap (6/8 tapped in 2);
  - '1/2' = half a unit per tap (2/2 tapped in 4);
  - '2+3' = two units, then three (5/4 tapped as 2+3)."""
BEAT_UNIT_SCOPE_ONWARD = "From this measure until the next change"
BEAT_UNIT_SCOPE_MEASURE = "This measure only"
BEAT_UNIT_SCOPE_PROMPT = "Where should this change apply?"
BEAT_UNIT_CONFLICT_TOOLTIP = (
    "This measure has more than one beat unit. The first one applies."
)
BEAT_UNIT_AMBIGUOUS_TOOLTIP = "{} taps under {}: treated as {}."
BEAT_UNIT_ASSUMED_TOOLTIP = (
    "Assumed from the tapped beats. Set the beat unit to confirm."
)
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
SCALE_TIMELINE_PROMPT = "Would you like to scale existing timelines to new media length?\nPrevious duration: {}\nNew duration: {}"
