from pathlib import Path
from typing import Literal, Tuple, cast

from tilia.parsers.csv import beat, hierarchy, marker
from tilia.parsers.score import musicxml
from tilia.requests import Get, Post, get, post
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.score.timeline import ScoreTimeline


def setup_parser(subparsers):
    # Import command
    import_parser = subparsers.add_parser(
        "import", help="Import data from a file into a timeline"
    )

    import_parser.set_defaults(func=import_timeline)

    import_subparsers = import_parser.add_subparsers(dest="tl_type")
    setup_import_marker_and_hierarchy_parser(import_subparsers)
    setup_import_score_parser(import_subparsers)
    setup_import_beat_parser(import_subparsers)


def setup_import_beat_parser(subparser):
    parser = subparser.add_parser(
        "beat",
        help="Import beat timelines",
        aliases=["b"],
    )
    setup_import_file_and_target_args(parser)


def setup_import_marker_and_hierarchy_parser(subparser):
    component_info = [
        ("marker", "markers", ["mrk"]),
        ("hierarchy", "hierarchies", ["hrc"]),
    ]
    for kind, plural, aliases in component_info:
        parser = subparser.add_parser(
            kind,
            help=f"Import {plural} data",
            aliases=aliases,
        )
        subparsers = parser.add_subparsers(dest="measure_or_time")
        setup_import_by_time(subparsers)
        setup_import_by_measure(subparsers)


def setup_import_score_parser(subparser):
    parser = subparser.add_parser(
        "score", help="Import score (.mxl, .musicxml) data", aliases=["sco"]
    )
    named_args = setup_import_file_and_target_args(parser)

    ref_group = named_args.add_mutually_exclusive_group(required=True)

    ref_group.add_argument(
        "--reference-tl-ordinal", type=int, help="Reference beat timeline ordinal"
    )
    ref_group.add_argument(
        "--reference-tl-name", type=str, help="Reference beat timeline name"
    )


def setup_import_by_time(subparser):
    import_time_parser = subparser.add_parser(
        "by-time",
        help="Import components by time",
        aliases=["t"],
    )
    setup_import_file_and_target_args(import_time_parser)


def setup_import_by_measure(subparser):
    parser = subparser.add_parser(
        "by-measure",
        help="Import components by measure and fraction",
        aliases=["m"],
    )
    named_args = setup_import_file_and_target_args(parser)

    ref_group = named_args.add_mutually_exclusive_group(required=True)

    ref_group.add_argument(
        "--reference-tl-ordinal", type=int, help="Reference beat timeline ordinal"
    )
    ref_group.add_argument(
        "--reference-tl-name", type=str, help="Reference beat timeline name"
    )


def setup_import_file_and_target_args(subparser):
    named_args = subparser.add_argument_group("required named arguments")

    named_args.add_argument(
        "--file", "-f", required=True, help="File to import data from"
    )

    target_group = named_args.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--target-ordinal", "-o", type=int, help="Target timeline ordinal"
    )
    target_group.add_argument(
        "--target-name", "-n", type=str, help="Target timeline name"
    )

    return named_args


def validate_timelines_for_import(
    tl: Timeline,
    ref_tl: Timeline | None,
    kind_str: Literal["beat", "hierarchy", "marker", "score"],
    by: Literal["by-measure", "by-time"] | None,
) -> Tuple[bool, str]:
    success = True
    error_message = ""

    if not isinstance(tl, Timeline.get_class_by_name(kind_str)):
        error_message = f"{tl} is not a {kind_str} timeline"
        success = False

    if ref_tl and not isinstance(ref_tl, BeatTimeline):
        error_message = f"{ref_tl} is not a beat timeline"
        success = False

    if by == "by-measure" and not ref_tl:
        error_message = "Reference beat timeline is required for importing by measure"
        success = False

    return success, error_message


def import_timeline(namespace):
    if "reference_tl_ordinal" not in namespace and "reference_tl_name" not in namespace:
        # importing by time, reference timeline was not passed
        namespace.reference_tl_ordinal = None
        namespace.reference_tl_name = None

    tl_type = namespace.tl_type

    if tl_type == "beat":
        measure_or_time = None
    elif tl_type == "score":
        # must set to get a beat timeline
        # from get_timelines_for_import
        measure_or_time = "by-measure"
    else:
        measure_or_time = namespace.measure_or_time

    tl, ref_tl = get_timelines_for_import(
        namespace.target_ordinal,
        namespace.target_name,
        namespace.reference_tl_ordinal,
        namespace.reference_tl_name,
        measure_or_time,
    )

    file = Path(namespace.file)

    success, error_message = validate_timelines_for_import(
        tl, ref_tl, tl_type, measure_or_time
    )
    if not success:
        post(
            Post.DISPLAY_ERROR, "Import error", "Timeline type error: " + error_message
        )
        return

    if measure_or_time and measure_or_time not in ["by-measure", "by-time"]:
        raise ValueError(
            f"Unknown value: {measure_or_time}. Should be 'by-measure' or 'by-time'"
        )

    prev_state = get(Get.APP_STATE)

    tl.clear()

    errors = None
    if tl_type == "marker":
        tl = cast(MarkerTimeline, tl)
        if measure_or_time == "by-measure":
            success, errors = marker.import_by_measure(tl, ref_tl, file)
        else:
            success, errors = marker.import_by_time(tl, file)
    elif tl_type == "hierarchy":
        tl = cast(HierarchyTimeline, tl)
        if measure_or_time == "by-measure":
            success, errors = hierarchy.import_by_measure(tl, ref_tl, file)
        else:
            success, errors = hierarchy.import_by_time(tl, file)
    elif tl_type == "beat":
        tl = cast(BeatTimeline, tl)
        success, errors = beat.beats_from_csv(tl, file)

    elif tl_type == "score":
        tl = cast(ScoreTimeline, tl)
        success, errors = musicxml.notes_from_musicXML(tl, ref_tl, str(file.resolve()))
    else:
        raise ValueError(f"Unknown timeline kind: {tl_type}")

    if errors:
        post(Post.DISPLAY_ERROR, "Import error", f"Errors: {errors}")

    if not success:
        post(Post.APP_STATE_RESTORE, prev_state)
        return


def get_timelines_for_import(
    target_ordinal: int,
    target_name: str,
    reference_ordinal: int | None,
    reference_name: str | None,
    measure_or_time: Literal["by-measure", "by-time"] | None,
) -> Tuple[Timeline, BeatTimeline | None]:
    target_tl = get_timeline_for_import(target_ordinal, target_name)

    if measure_or_time == "by-measure":
        reference_tl = cast(
            BeatTimeline, get_timeline_for_import(reference_ordinal, reference_name)
        )
        return target_tl, reference_tl
    else:
        return target_tl, None


def get_timeline_for_import(ordinal: int | None, name: str | None) -> Timeline:
    if ordinal is not None:
        tl = get(Get.TIMELINE_BY_ATTR, "ordinal", ordinal)
        if not tl:
            raise ValueError(f"No timeline found with {ordinal=}")
    else:
        tl = get(Get.TIMELINE_BY_ATTR, "name", name)
        if not tl:
            raise ValueError(f"No timeline found with {name=}")

    return tl
