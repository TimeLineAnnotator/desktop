"""Check a migrated copy of a corpus against the original (SC-002).

    python scripts/check_migration.py SOURCE COPY

COPY has to be a copy of SOURCE: it is migrated in place. Never give an original
corpus as COPY. SOURCE is only read. tilia-core has to be installed, for example
with `uv run --package tilia-core python scripts/check_migration.py SOURCE COPY`.

The script migrates COPY with `migrate_folder(apply=True)`, which does nothing to
a file already migrated, then checks each file:

- it reads back, without an error;
- a second read and write leaves it byte-identical;
- it holds what SOURCE's file holds when read through the migration: every
  timeline, component, label, time, colour, comment and metadata entry, and every
  score;
- for an old file, nothing in the original's own JSON is missing from it: no
  timeline, component, label, time, colour, word of a comment, metadata entry or
  score SVG, but what FR-021 drops. Reading both through the migration couldn't
  show that. Since the migration gives new ids, what each holds is compared as a
  whole, not component by component.

It prints a report, and exits with 0 when there is no difference, 1 when there is
any, and 2 when it was given something it won't check, having written nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from tilia_core import tla
from tilia_core.tla.folder import corpus_files

# What reading an old file and reading its migrated copy differ in on purpose: the
# version it was read from, the warnings of a migration done since, and where it
# was read from.
NOT_CONTENT = frozenset({"format_version", "warnings", "origin"})
LEGACY_SCORE = "svg-osmd-legacy"
SHOWN_PER_FILE = 20
SHORT = 100
# A comment's words, as the migration tells them. A word that starts with one of
# the marks and has a value moves to the component's metadata (FR-021).
SEPARATORS = re.compile(r"[\s|]+")
TAG = "tag="
GEN = "gen="


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def plain(value: Any) -> Any:
    """`value`, a document or a part of one, as dicts, lists and values."""
    if dataclasses.is_dataclass(value):
        return {
            field.name: plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.compare and field.name not in NOT_CONTENT
        }
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= SHORT else f"{text[:SHORT]}... ({len(text)} characters)"


def differences(before: Any, after: Any, place: str = "") -> Iterator[str]:
    """How `after` differs from `before`, both plain, each with its place. A number
    of another type is a difference, as it is in a file: 1 and 1.0."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys(), key=str):
            at = f"{place}/{key}"
            if key not in after:
                yield f"{at}: missing from the copy, was {short(before[key])}"
            elif key not in before:
                yield f"{at}: only in the copy, is {short(after[key])}"
            else:
                yield from differences(before[key], after[key], at)
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            yield f"{place}: {len(before)} items in the original, {len(after)} here"
        for index, (one, other) in enumerate(zip(before, after, strict=False)):
            yield from differences(one, other, f"{place}/{index}")
    elif type(before) is not type(after) or before != after:
        yield f"{place}: {short(before)} in the original, {short(after)} in the copy"


def kind_of(kind: Any) -> str:
    """A timeline's or a component's kind, however a file spells it."""
    return str(getattr(kind, "spelling", kind)).lower().removesuffix("_timeline")


def in_comment(comment: str) -> Iterator[str]:
    """A comment's words, and its marks: a tag once, as the migration keeps it."""
    tags = set()
    for word in SEPARATORS.split(nfc(comment)):
        if word.startswith(TAG) and word != TAG:
            tags.add(word)
        elif word.startswith(GEN) and word != GEN:
            yield f"mark {word}"
        elif word:
            yield f"comment {word}"
    yield from (f"mark {tag}" for tag in tags)


def in_component(kind: Any, attrs: Mapping[str, Any]) -> Iterator[str]:
    """What a component holds, each as its category and its value."""
    yield f"component {kind_of(kind)}"
    if attrs.get("label"):
        yield f"label {nfc(attrs['label'])}"
    for key in ("time", "start", "end"):
        value = attrs.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            yield f"time {float(value)}"
    if attrs.get("color"):
        yield f"colour {attrs['color']}"
    if isinstance(attrs.get("comments"), str):
        yield from in_comment(attrs["comments"])


def in_metadata(name: str, value: Any) -> Iterator[str]:
    """A metadata entry, each item of a list by itself: the migration makes text
    of what isn't."""
    for item in value if isinstance(value, list) else [value]:
        text = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
        yield f"metadata {nfc(name)} {nfc(text)}"


def svg(lines: list[str]) -> str:
    return f"score SVG {hashlib.sha256(chr(10).join(lines).encode()).hexdigest()}"


def in_old_file(content: Mapping[str, Any]) -> Iterator[str]:
    """What an old file holds, from its own JSON. AudioWave's amplitude bars, which
    TiLiA computes from the media, are dropped, and so is the media length as an
    entry of the metadata, which becomes the media's (FR-021)."""
    for name, value in content.get("media_metadata", {}).items():
        if name != "media length":
            yield from in_metadata(name, value)
    for timeline in content["timelines"].values():
        kind = kind_of(timeline["kind"])
        yield f"timeline {kind}"
        if kind == "score" and timeline.get("svg_data"):
            score = tla.Score(id="", format=LEGACY_SCORE)
            score.text = timeline["svg_data"]
            yield svg(score.lines)
        if kind != "audiowave":
            for component in timeline.get("components", {}).values():
                yield from in_component(component.get("kind"), component)


def in_document(document: tla.Document) -> Iterator[str]:
    """What a document holds, in the terms of `in_old_file`."""
    for name, value in document.metadata.items():
        yield from in_metadata(name, value)
    for score in document.scores.values():
        if score.format == LEGACY_SCORE:
            yield svg(score.lines)
    for timeline in document.timelines.values():
        yield f"timeline {kind_of(timeline.kind)}"
        for component in timeline.components.values():
            yield from in_component(component.kind, component.attrs)
            for tag in component.metadata.get("tags", []):
                yield f"mark {TAG}{nfc(tag)}"
            generated = component.metadata.get("generated_by", [])
            for mark in [generated] if isinstance(generated, str) else generated:
                yield f"mark {GEN}{nfc(mark)}"


def tally(held: Counter[str]) -> str:
    """How many things of each category `held` has."""
    counts: Counter[str] = Counter()
    for item, count in held.items():
        counts[item.partition(" ")[0]] += count
    return (
        f"timelines {counts['timeline']}, components {counts['component']},"
        f" labels {counts['label']}, times {counts['time']},"
        f" colours {counts['colour']}, words of comments {counts['comment']},"
        f" marks {counts['mark']}, metadata items {counts['metadata']},"
        f" legacy scores {counts['score']}"
    )


def check_file(source: Path, copy: Path) -> tuple[list[str], Counter[str]]:
    """The differences between a file of SOURCE and its migrated copy, and what the
    copy holds."""
    after = tla.read(copy)
    written = copy.read_bytes()
    original = source.read_bytes()
    # As if it were at the copy's place, where the copy was migrated: the media's
    # path is relative to the file's folder (FR-021).
    before = tla.loads(original, path=copy)
    found = list(differences(plain(before), plain(after)))
    if not found and tla.canonical_bytes(before) != written:
        found.append("the copy isn't what the original migrates to")
    held = Counter(in_document(after))
    if before.format_version != tla.FORMAT_VERSION:
        missing = Counter(in_old_file(json.loads(original))) - held
        found.extend(
            f"missing from the copy: {short(item)}, {missing[item]} of them"
            for item in sorted(missing)
        )
    tla.write(copy, after, expect=tla.fingerprint(copy))
    if copy.read_bytes() != written:
        found.append("a second read and write changed its bytes")
    return found, held


def is_within(inner: Path, outer: Path) -> bool:
    """Whether the folder `inner` is `outer`, or inside it."""
    inner_path = os.path.normcase(os.path.realpath(inner))
    outer_path = os.path.normcase(os.path.realpath(outer))
    try:
        return os.path.commonpath([inner_path, outer_path]) == outer_path
    except ValueError:  # on another drive
        return False


def is_current(data: bytes) -> bool:
    try:
        return tla.loads(data).format_version == tla.FORMAT_VERSION
    except ValueError:  # UnreadableFile is a ValueError
        return False


def looks_swapped(files: dict[str, tuple[Path, Path]]) -> str | None:
    """A file already migrated in SOURCE and not in COPY, which may be the original:
    a copy migrated with `tilia migrate` is the other way round."""
    for relative, (source, copy) in files.items():
        original, copied = source.read_bytes(), copy.read_bytes()
        if original != copied and is_current(original) and not is_current(copied):
            return relative
    return None


def check(source: Path, copy: Path) -> int:
    """Check `copy` against `source`, print the report and give the exit status."""
    for folder in (source, copy):
        if not folder.is_dir():
            print(f"not a folder: {folder}", file=sys.stderr)
            return 2
    if is_within(source, copy) or is_within(copy, source):
        print(f"SOURCE and COPY overlap: {source}, {copy}", file=sys.stderr)
        return 2
    try:
        in_source = dict(corpus_files(source))
        in_copy = dict(corpus_files(copy))
        only = sorted(in_source.keys() ^ in_copy.keys())
        for relative in only:
            print(
                f"{relative}: only in {'SOURCE' if relative in in_source else 'COPY'}"
            )
        if only:
            print(f"{len(only)} files aren't in both: nothing was written.")
            return 1
        files = {path: (in_source[path], in_copy[path]) for path in in_source}
        swapped = looks_swapped(files)
    except OSError as error:
        print(error, file=sys.stderr)
        return 2
    if swapped is not None:
        print(
            f"{swapped} is migrated in SOURCE and not in COPY: are they the wrong way"
            " round? Nothing was written.",
            file=sys.stderr,
        )
        return 2
    return migrate_and_compare(copy, files)


def migrate_and_compare(copy: Path, files: dict[str, tuple[Path, Path]]) -> int:
    """Migrate `copy`, compare each of `files`, print what was found and give the
    exit status."""
    migrated = tla.migrate_folder(copy, apply=True)
    different = len(migrated.folders_not_listed)
    total: Counter[str] = Counter()
    for unlisted in migrated.folders_not_listed:
        print(f"{unlisted.path}: {unlisted.reason}")
    for result in migrated.files:
        found: list[str] = []
        held: Counter[str] = Counter()
        if result.outcome not in (tla.Outcome.MIGRATED, tla.Outcome.CURRENT):
            found.append(f"{result.outcome.value}: {result.reason}")
        else:
            try:
                found, held = check_file(*files[result.path])
            except Exception as error:  # an error in the core too: go on (FR-052)
                found.append(f"{type(error).__name__}: {error}")
        total.update(held)
        origin = f" (from {result.from_version})" if result.from_version else ""
        if not found:
            print(f"{result.path}{origin}: no difference: {tally(held)}")
            continue
        different += 1
        print(f"{result.path}{origin}: differences: {len(found)}")
        for line in found[:SHOWN_PER_FILE]:
            print(f"  {line}")
        if len(found) > SHOWN_PER_FILE:
            print(f"  and {len(found) - SHOWN_PER_FILE} more")
    for paths in migrated.shared_ids:
        print(f"These files share a document id: {', '.join(paths)}")
    print(f"{len(migrated.files)} files, {different} with a difference.")
    print(f"In all: {tally(total)}.")
    return 1 if different else 0


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.partition("\n")[0])
    parser.add_argument("source", type=Path, metavar="SOURCE", help="only read")
    parser.add_argument("copy", type=Path, metavar="COPY", help="migrated in place")
    args = parser.parse_args(arguments)
    # A console may not have every character of a label or a file's name.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    return check(args.source, args.copy)


if __name__ == "__main__":
    sys.exit(main())
