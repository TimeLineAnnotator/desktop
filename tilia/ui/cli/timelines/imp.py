from argparse import _SubParsersAction
from typing import Optional, Tuple, Literal

from tilia.parsers import csv
from tilia.exceptions import WrongTimelineForImport
from tilia.requests import get, Get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.timeline_kinds import TimelineKind


def setup_parser(subparsers: _SubParsersAction):
    # Import command
    import_parser = subparsers.add_parser(
        "import", help="Import data from a file into a " "timeline"
    )
    import_parser.add_argument(
        "format",
        choices=["csv"],
        help="Input file format (only csv is currently supported)",
    )
    import_parser.set_defaults(func=import_timeline)

    import_subparsers = import_parser.add_subparsers(dest="tl_kind")
    setup_import_marker_and_hierarchy_parser(import_subparsers)


def setup_import_marker_and_hierarchy_parser(subparser: _SubParsersAction):
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


def setup_import_by_time(subparser: _SubParsersAction):
    import_time_parser = subparser.add_parser(
        "by-time",
        help="Import components by time",
        aliases=["t"],
    )
    setup_import_file_and_target_args(import_time_parser)


def setup_import_by_measure(subparser: _SubParsersAction):
    parser = subparser.add_parser(
        "by-measure",
        help="Import components by measure and fraction",
        aliases=["m"],
    )
    named_args = setup_import_file_and_target_args(parser)

    ref_group = named_args.add_mutually_exclusive_group(required=True)

    ref_group.add_argument(
        "--reference-tl-ordinal",
        help="Reference beat timeline ordinal",
    )
    ref_group.add_argument(
        "--reference-tl-name",
        help="Reference beat timeline name",
    )


def setup_import_file_and_target_args(subparser: _SubParsersAction):
    named_args = subparser.add_argument_group("required named arguments")

    named_args.add_argument(
        "--file", "-f", required=True, help="File to import data from"
    )

    target_group = named_args.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--target-ordinal", "-o", help="Target timeline ordinal")
    target_group.add_argument("--target-name", "-n", help="Target timeline name")

    return named_args


def validate_timelines_for_import(
    tl: Timeline,
    ref_tl: Optional[Timeline],
    kind_str: Literal["marker", "hierarchy"],
    measure_or_time: Literal["measure", "time"],
) -> None:
    if kind_str == "marker" and tl.KIND != TimelineKind.MARKER_TIMELINE:
        raise WrongTimelineForImport(f"{tl} is not a marker timeline")
    elif kind_str == "hierarchy" and tl.KIND != TimelineKind.HIERARCHY_TIMELINE:
        raise WrongTimelineForImport(f"{tl} is not a hierarchy timeline")

    if ref_tl and ref_tl.KIND != TimelineKind.BEAT_TIMELINE:
        raise WrongTimelineForImport(f"{ref_tl} is not a beat timeline")

    if measure_or_time == "measure" and not ref_tl:
        raise ValueError("Reference beat timeline is required for importing by measure")


def import_timeline(namespace):
    tl, ref_tl = get_timelines_for_import(
        namespace.target_ordinal,
        namespace.target_name,
        namespace.reference_tl_ordinal,
        namespace.reference_tl_name,
        namespace.measure_or_time,
    )

    tl_kind, measure_or_time = namespace.tl_kind, namespace.measure_or_time

    validate_timelines_for_import(tl, ref_tl, tl_kind, measure_or_time)
    ref_tl: BeatTimeline | None

    if tl_kind == "marker":
        tl: MarkerTimeline
        if measure_or_time == "measure":
            csv.markers_by_measure_from_csv(tl, ref_tl, namespace.file)
        else:
            csv.markers_by_time_from_csv(tl, namespace.file)
    elif tl_kind == "hierarchy":
        tl: HierarchyTimeline
        if measure_or_time == "measure":
            csv.hierarchies_by_measure_from_csv(tl, ref_tl, namespace.file)
        else:
            csv.hierarchies_by_time_from_csv(tl, namespace.file)


def get_timelines_for_import(
    target_ordinal: int,
    target_name: str,
    reference_ordinal: int,
    reference_name: str,
    measure_or_time: Literal["measure", "time"],
) -> Tuple[Timeline, Timeline | None]:
    target_tl = get_timeline_for_import(target_ordinal, target_name)

    if measure_or_time == "measure":
        reference_tl = get_timeline_for_import(reference_ordinal, reference_name)
        return target_tl, reference_tl
    else:
        return target_tl, None


def get_timeline_for_import(ordinal: int, name: str) -> Timeline:
    if ordinal is not None:
        tl = get(Get.TIMELINE_BY_ATTR, "ordinal", ordinal)
        if not tl:
            raise ValueError(f"No timeline found with {ordinal=}")
    else:
        tl = get(Get.TIMELINE_BY_ATTR, "name", name)
        if not tl:
            raise ValueError(f"No timeline found with {name=}")

    return tl
