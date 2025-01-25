import argparse
import os
from functools import partial
from pathlib import Path
from typing import Callable

from tilia.media.constants import ALL_SUPPORTED_MEDIA_FORMATS
from collections import namedtuple

from tilia.ui.cli import io
from tilia.requests import post, Post


def setup_parser(subparser, parse_and_run: Callable[[str], bool]):
    generate_subp = subparser.add_parser("generate_scripts", exit_on_error=False)
    generate_subp.add_argument("path", type=str, nargs="+")
    generate_subp.set_defaults(func=partial(generate, parse_and_run))


def generate(namespace: argparse.Namespace, parse_and_run: Callable[[str], bool]):
    if not check_starting_directory(namespace.path):
        return
    script_paths = get_scripts(namespace.path)
    if not script_paths:
        return

    io.output("\n".join(["Saved scripts:", *script_paths]))
    confirm = io.ask_yes_or_no("Would you like to run the generated scripts?")
    if confirm:
        for path in script_paths:
            io.output(f"Running script:")
            parse_and_run(f'script "{path}"')
            post(Post.APP_CLEAR)


def check_starting_directory(directory: str | Path) -> bool:
    return os.path.exists(directory) and os.path.isdir(directory)


def _get_media_files(filenames: list[str]) -> list:
    media_files = []
    for file in filenames:
        for format in ALL_SUPPORTED_MEDIA_FORMATS:
            if file.endswith(format):
                media_files.append(file)
                break

    return media_files


def _get_args_from_filename(filename: str, kind: str) -> tuple[str, bool, str]:
    args = ""
    by_time_or_measure_set = False
    split_name = filename.split("_")
    split_name.remove(kind)
    for arg in {"height", "beat-pattern"}:
        if arg in split_name:
            args = " ".join(
                [args, f"--{arg} {split_name.pop(split_name.index(arg) + 1)}"]
            )
            split_name.remove(arg)

    if "by-measure" in split_name:
        is_by_time = False
        by_time_or_measure_set = True
        split_name.remove("by-measure")

    if "by-time" in split_name:
        if by_time_or_measure_set:
            raise ValueError("File name contains both by-time and by-measure.")
        else:
            is_by_time = True
            by_time_or_measure_set = True
        split_name.remove("by-time")

    if not by_time_or_measure_set:
        is_by_time = True

    return args, is_by_time, "_".join(split_name)


timeline_args = namedtuple("timeline_args", "add imp is_beat requires_beat ref_name")


def _get_timeline_args(filename: str, folder_name: str):
    timeline_kinds = ["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
    for kind in timeline_kinds:
        if kind in filename:
            args, is_by_time, name = _get_args_from_filename(
                filename.removesuffix(".csv"), kind
            )
            if kind in {"beat", "bea"}:
                return True, timeline_args(
                    f'timelines add {kind} --name "{name}" {args or ""}',
                    f'timelines import csv {kind} --target-name "{name}" --file "{os.path.join(folder_name, filename)}"',
                    True,
                    False,
                    name,
                )

            if not is_by_time:
                requires_beat = True
                time_or_measure = " by-measure "
            else:
                requires_beat = False
                time_or_measure = " by-time "

            return True, timeline_args(
                f'timelines add {kind} --name "{name}" {args or ""}',
                f'timelines import csv {kind}{time_or_measure}--target-name "{name}" --file "{os.path.join(folder_name, filename)}"',
                False,
                requires_beat,
                "",
            )

    return False, None


def _get_script_for_folder(
    folder_name: str | Path, filenames: list[str | Path]
) -> Path:
    to_write = []
    timelines_to_import = []
    has_beat = False
    requires_beat = False
    reference_beat = ""

    media_data = _get_media_files(filenames)

    if not (media_data or "set_media_length.txt" in filenames):
        print(
            f'{"No suitable media found in " + folder_name + ".":<100}{"Folder skipped.":>14}'
        )
        return
    if len(media_data) > 1:
        print(
            f'{"Multiple media files found in " + folder_name + ".":<100}{"Folder skipped.":>14}'
        )
        return

    if media_data:
        to_write.append(f'load-media "{os.path.join(folder_name, media_data[0])}"\n')
        filenames.remove(media_data[0])

    if "set_media_length.txt" in filenames:
        to_write.append(
            f'metadata set-media-length {open(os.path.join(folder_name, "set_media_length.txt"), "r").read()}\n'
        )
        filenames.remove("set_media_length.txt")

    for file in filenames:
        if file.endswith(".json"):
            to_write.append(f'metadata import "{os.path.join(folder_name, file)}"\n')

        if file.endswith(".csv"):
            try:
                success, args = _get_timeline_args(file, folder_name)
                if not success:
                    continue

                to_write.append(f"{args.add}\n")
                timelines_to_import.append(args.imp)
                has_beat |= args.is_beat
                requires_beat |= args.requires_beat
                if not reference_beat and args.ref_name:
                    reference_beat = args.ref_name
                elif reference_beat and args.ref_name:
                    print(
                        f'{"Multiple beat timelines found. Using " + reference_beat + " as reference instead of " + args.ref_name +".":<100}{os.path.join(folder_name, file):>20}'
                    )

            except ValueError as e:
                print(f"{e:<100}{os.path.join(folder_name, file):>20}")
                return

    if requires_beat and not has_beat:
        print(f"{folder_name} requires beat but no beat csv found.")
        return

    with open(os.path.join(folder_name, "script.txt"), "w") as f:
        f.writelines(to_write)
        for timeline in timelines_to_import:
            f.write(
                timeline
                + (
                    ' --reference-tl-name "' + reference_beat + '"\n'
                    if "by-measure" in timeline
                    else "\n"
                )
            )
        f.write(
            'save "'
            + os.path.join(folder_name, folder_name.split(os.path.sep)[-1])
            + '.tla"'
        )
        return f.name


def get_scripts(directory: str | Path) -> list[Path]:
    """
    A TUI for generating .txt files for parsing into TiLiA's CLI script.

    Parameters:
        Directory path (str): The absolute path to the directory that contains relevant files.
            - The function traverses through each folder/subfolder.
            - Each folder should contain at least a media file or "set_media_length.txt" (containing a single line of the number of seconds to set media length).
            - .csv files should contain relevant timeline kind in their title, as well as "beat-pattern", "height", "by-time" or "by-measure" if applicable. These fields should be separated by '_'.
            - .json files will be imported as metadata.
            - A 'script.txt' file will be produced per folder with sufficient data to create a potential script.
    Returns:
        List of paths to individual scripts (str): The absolute path to each script.
    """
    saved_scripts = []
    for folder_name, sub_folders, filenames in os.walk(directory):
        saved_scripts += filter(None, [_get_script_for_folder(folder_name, filenames)])

    return saved_scripts
