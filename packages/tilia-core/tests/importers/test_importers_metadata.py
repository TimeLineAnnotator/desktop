"""`tilia_core.importers.import_metadata`: a JSON object's fields added to the
document's (spec FR-053, with FR-051 and FR-056 for `media length`; User
Story 6, scenarios 7 and 8)."""

import copy
import json
import sys
import time
import wave
from pathlib import Path

import pytest
from import_docs import component, document, timeline

from tilia_core import build, importers
from tilia_core.importers import ImportFailed

# TiLiA's texts (tilia/errors.py, tilia/ui/strings.py), word for word.
JSON_FAILED = "Error when parsing file {}:\n{}"
FILE_FAILED = "File {} not found."
UTF8_DECODE_FAILED = "'{}' is not a valid UTF-8 encoded JSON file."
NOT_A_MEDIA_LENGTH = (
    "Cannot set media metadata to {}. Media length must be a positive number."
)
MEDIA_LOADED = "Can't change media length when a media file is loaded."
# The spec's, where TiLiA has none.
HAS_COMPONENTS = (
    "The media length can't change once timelines have components:"
    " rescale the file in TiLiA."
)
# Where neither has one (TimeLineAnnotator/project-management#326).
NOT_AN_OBJECT = "expected an object of fields"
# tla's reader's, for a file nested too deep.
TOO_DEEP = "nested more than 100 levels deep"
LENGTH_IGNORED = "media length ignored: " + MEDIA_LOADED


def json_file(tmp_path: Path, content, name: str = "metadata.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return path


def text_file(tmp_path: Path, text: str, name: str = "metadata.json") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def wav(path: Path, *, seconds: float) -> Path:
    rate = 8000
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b"\0\0" * round(rate * seconds))
    return path


def fails(doc, path) -> str:
    """The import's failure, checked to have changed nothing: its message."""
    before = copy.deepcopy(doc)
    with pytest.raises(ImportFailed) as error:
        importers.import_metadata(doc, path)
    assert doc == before
    assert list(doc.metadata) == list(before.metadata)
    assert error.value.path == Path(path)
    return error.value.message


# Fields (FR-053)


def test_the_fields_are_added_and_the_jsons_values_win(tmp_path):
    # US6 scenario 7.
    doc = build.new_script_document()
    build.set_field(doc, "composer", "Beethoven")
    path = json_file(tmp_path, {"title": "Op. 2 No. 1", "performer": "Arrau"})

    result = importers.import_metadata(doc, path)

    assert list(doc.metadata.items()) == [
        ("title", "Op. 2 No. 1"),
        ("notes", ""),
        ("composer", "Beethoven"),
        ("performer", "Arrau"),
    ]
    assert result.created == []
    assert result.problems == []
    assert result.notes == []


def test_an_empty_object_changes_nothing(tmp_path):
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    importers.import_metadata(doc, json_file(tmp_path, {}))

    assert doc == before


def test_the_media_length_and_the_other_fields_are_left_alone(tmp_path):
    doc = build.new_script_document()
    build.set_media_length(doc, 60.0)

    importers.import_metadata(doc, json_file(tmp_path, {"composer": "Haydn"}))

    # TiLiA resets the length to 0 when the JSON has none; the core doesn't.
    assert doc.media_length == 60.0
    assert doc.metadata == {"title": "Untitled", "notes": "", "composer": "Haydn"}


def test_a_number_becomes_text(tmp_path):
    doc = build.new_script_document()

    importers.import_metadata(
        doc, json_file(tmp_path, {"year": 1795, "opus": 2, "tempo": 1.5})
    )

    assert doc.metadata["year"] == "1795"
    assert doc.metadata["opus"] == "2"
    assert doc.metadata["tempo"] == "1.5"


@pytest.mark.parametrize(
    "text, expected",
    [
        # As WP3's migration makes an old file's fields text.
        ("true", "true"),
        ("false", "false"),
        ("null", ""),
        ("1.0", "1.0"),
        ("1e5", "100000.0"),
        ("-0.25", "-0.25"),
        ("NaN", "NaN"),
        ('{"b": 1, "a": [true, null]}', '{"b": 1, "a": [true, null]}'),
        ('{"lieu": "Wien"}', '{"lieu": "Wien"}'),
        ('{"ville": "Brünn"}', '{"ville": "Brünn"}'),
        ('[[1, 2], "a"]', '[[1, 2], "a"]'),
        ('[{"a": 1}]', '[{"a": 1}]'),
    ],
)
def test_a_value_that_isnt_text_becomes_text(tmp_path, text, expected):
    doc = build.new_script_document()

    importers.import_metadata(doc, text_file(tmp_path, f'{{"field": {text}}}'))

    assert doc.metadata["field"] == expected


def test_a_list_of_plain_values_becomes_a_list_of_texts(tmp_path):
    doc = build.new_script_document()
    path = json_file(
        tmp_path,
        {"performers": ["Arrau", "Brendel"], "mixed": ["a", 1, 2.5, True, None]},
    )

    importers.import_metadata(doc, path)

    assert doc.metadata["performers"] == ["Arrau", "Brendel"]
    assert doc.metadata["mixed"] == ["a", "1", "2.5", "true", ""]


def test_an_empty_list_stays_a_list(tmp_path):
    doc = build.new_script_document()

    importers.import_metadata(doc, json_file(tmp_path, {"tags": []}))

    assert doc.metadata["tags"] == []


def test_names_and_values_are_stored_in_nfc(tmp_path):
    doc = build.new_script_document()
    decomposed = "Dvořák"
    path = json_file(
        tmp_path,
        {
            "compositeur": decomposed,
            "Mélodie": [decomposed],
            "werk": {"name": decomposed},
        },
    )

    importers.import_metadata(doc, path)

    composed = "Dvořák"
    assert doc.metadata["compositeur"] == composed
    assert doc.metadata["Mélodie"] == [composed]
    assert doc.metadata["werk"] == '{"name": "Dvořák"}'


def test_a_repeated_key_keeps_its_last_value(tmp_path):
    # As TiLiA reads it, with json.load.
    doc = build.new_script_document()

    importers.import_metadata(
        doc, text_file(tmp_path, '{"composer": "A", "composer": "B"}')
    )

    assert doc.metadata["composer"] == "B"


def test_a_byte_order_mark_is_accepted(tmp_path):
    doc = build.new_script_document()
    path = tmp_path / "metadata.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"composer": "Haydn"}')

    importers.import_metadata(doc, path)

    assert doc.metadata["composer"] == "Haydn"


def test_the_path_can_be_text(tmp_path):
    doc = build.new_script_document()

    importers.import_metadata(doc, str(json_file(tmp_path, {"composer": "Haydn"})))

    assert doc.metadata["composer"] == "Haydn"


# The media length (FR-051, FR-053, FR-056)


def test_media_length_sets_the_length_without_media(tmp_path):
    doc = build.new_script_document()
    path = json_file(tmp_path, {"media length": 312.5, "composer": "Mozart"})

    result = importers.import_metadata(doc, path)

    assert doc.media_length == 312.5
    assert "media length" not in doc.metadata
    assert doc.metadata["composer"] == "Mozart"
    assert result.notes == []
    assert result.problems == []


def test_media_length_replaces_a_length_set_before(tmp_path):
    doc = build.new_script_document()
    build.set_media_length(doc, 60.0)

    importers.import_metadata(doc, json_file(tmp_path, {"media length": 120}))

    assert doc.media_length == 120.0


@pytest.mark.parametrize("key", ["Media Length", "MEDIA LENGTH", "media Length"])
def test_media_length_in_any_letter_case_is_the_media_length(tmp_path, key):
    # As `metadata set` refuses it as a field in any letter case.
    doc = build.new_script_document()

    importers.import_metadata(doc, json_file(tmp_path, {key: 120}))

    assert doc.media_length == 120.0
    assert list(doc.metadata) == ["title", "notes"]


@pytest.mark.parametrize("text", ["312.5", " 312.5 ", "3.125e2", "+312.5"])
def test_a_media_length_written_as_text_is_read_as_a_number(tmp_path, text):
    # As WP3's migration reads an old file's media length
    # (TimeLineAnnotator/project-management#326).
    doc = build.new_script_document()

    importers.import_metadata(doc, json_file(tmp_path, {"media length": text}))

    assert doc.media_length == 312.5


def test_media_length_is_ignored_with_a_note_when_media_is_attached(tmp_path):
    # US6 scenario 8.
    doc = build.new_script_document()
    build.load_media(doc, wav(tmp_path / "recording.wav", seconds=1.5))
    path = json_file(tmp_path, {"media length": 300, "composer": "Mozart"})

    result = importers.import_metadata(doc, path)

    assert doc.media_length == 1.5
    assert "media length" not in doc.metadata
    assert doc.metadata["composer"] == "Mozart"
    assert result.notes == [LENGTH_IGNORED]
    assert result.problems == []


def test_the_note_names_the_key_as_the_json_spells_it(tmp_path):
    doc = document(media_length=60.0)
    doc.media_path = "recording.mp3"

    result = importers.import_metadata(doc, json_file(tmp_path, {"Media Length": 3}))

    assert result.notes == ["Media Length ignored: " + MEDIA_LOADED]


@pytest.mark.parametrize("value", [300, 0, -1, "abc", None])
def test_any_media_length_is_ignored_when_media_is_attached(tmp_path, value):
    # Media attached by an opened file counts too (FR-051).
    doc = document(media_length=60.0)
    doc.media_path = "recording.mp3"

    result = importers.import_metadata(
        doc, json_file(tmp_path, {"media length": value})
    )

    assert doc.media_length == 60.0
    assert result.notes == [LENGTH_IGNORED]
    assert "media length" not in doc.metadata


@pytest.mark.parametrize(
    "text, shown",
    [
        ("0", "0"),
        ("0.0", "0.0"),
        ("-1", "-1"),
        ("-312.5", "-312.5"),
        ('"abc"', "abc"),
        ('"0"', "0"),
        ('"-5"', "-5"),
        ('"1e999"', "1e999"),
        ('""', ""),
        ("1" + "0" * 400, "1" + "0" * 400),
        # Anything else as JSON writes it.
        ("null", "null"),
        ("true", "true"),
        ("false", "false"),
        ("NaN", "NaN"),
        ("Infinity", "Infinity"),
        ("-Infinity", "-Infinity"),
        ("1e999", "Infinity"),
        ("[312.5]", "[312.5]"),
        ('["1", 2]', '["1", 2]'),
        ('{"seconds": 312.5}', '{"seconds": 312.5}'),
        ('{"durée": 312.5}', '{"durée": 312.5}'),
    ],
)
def test_a_media_length_that_isnt_one_fails_the_import(tmp_path, text, shown):
    # Checked as `metadata set-media-length` checks it (FR-053, FR-051): the
    # import fails, and the other fields aren't set either. Text is quoted as
    # written (TimeLineAnnotator/project-management#326).
    doc = build.new_script_document()
    build.set_media_length(doc, 60.0)
    path = text_file(tmp_path, f'{{"composer": "Mozart", "media length": {text}}}')

    assert fails(doc, path) == NOT_A_MEDIA_LENGTH.format(shown)


def with_a_marker(media_length):
    marker = timeline("marker", components=[component("marker", time=1.0)])
    return document(media_length=media_length, timelines=[marker])


def test_a_known_length_cant_change_once_timelines_have_components(tmp_path):
    # FR-056: the import fails, and nothing is set.
    doc = with_a_marker(60.0)
    path = json_file(tmp_path, {"composer": "Mozart", "media length": 30})

    assert fails(doc, path) == HAS_COMPONENTS


def test_the_same_length_isnt_a_change(tmp_path):
    doc = with_a_marker(60.0)

    importers.import_metadata(doc, json_file(tmp_path, {"media length": 60}))

    assert doc.media_length == 60.0


def test_a_first_length_isnt_a_change(tmp_path):
    doc = with_a_marker(None)

    importers.import_metadata(doc, json_file(tmp_path, {"media length": 30}))

    assert doc.media_length == 30.0


def test_a_length_within_a_millisecond_keeps_the_known_one(tmp_path):
    # A WAV's length from its header, against the whole milliseconds a file
    # TiLiA saved holds (TimeLineAnnotator/project-management#327).
    doc = with_a_marker(3.125)
    path = json_file(tmp_path, {"media length": 3.124716553287982})

    importers.import_metadata(doc, path)

    assert doc.media_length == 3.125


@pytest.mark.parametrize("value", [3.126, "3.124"])
def test_a_length_a_millisecond_away_is_a_change(tmp_path, value):
    doc = with_a_marker(3.125)
    path = json_file(tmp_path, {"composer": "Mozart", "media length": value})

    assert fails(doc, path) == HAS_COMPONENTS


def test_without_components_a_length_within_a_millisecond_is_set_as_read(tmp_path):
    doc = document(media_length=3.125, timelines=[timeline("marker")])
    path = json_file(tmp_path, {"media length": 3.124716553287982})

    importers.import_metadata(doc, path)

    assert doc.media_length == 3.124716553287982


def test_a_length_refused_after_another_was_set_changes_nothing(tmp_path):
    # Two keys for the media length, in different letter cases: the second is
    # refused, and the first is undone.
    doc = build.new_script_document()
    build.set_media_length(doc, 60.0)
    path = json_file(tmp_path, {"media length": 120, "Media Length": -1})

    assert fails(doc, path) == NOT_A_MEDIA_LENGTH.format(-1)
    assert doc.media_length == 60.0


# Files it can't import (FR-053, FR-024)


def test_a_file_that_doesnt_exist(tmp_path):
    doc = build.new_script_document()
    path = tmp_path / "missing.json"

    assert fails(doc, path) == FILE_FAILED.format(path)


def test_a_file_in_a_folder_that_doesnt_exist(tmp_path):
    doc = build.new_script_document()
    path = tmp_path / "missing" / "metadata.json"

    assert fails(doc, path) == FILE_FAILED.format(path)


@pytest.mark.parametrize(
    "text, error",
    [
        ("", "Expecting value: line 1 column 1 (char 0)"),
        ("  \n", "Expecting value: line 2 column 1 (char 3)"),
        (
            "{title: 'x'}",
            (
                "Expecting property name enclosed in double quotes:"
                " line 1 column 2 (char 1)"
            ),
        ),
        ('{"title": "x"} {}', "Extra data: line 1 column 16 (char 15)"),
    ],
)
def test_a_file_that_isnt_json(tmp_path, text, error):
    # TiLiA's text, with the error as TiLiA gives it: its repr.
    doc = build.new_script_document()
    path = text_file(tmp_path, text)

    assert fails(doc, path) == JSON_FAILED.format(path, f"JSONDecodeError({error!r})")


@pytest.mark.parametrize(
    # A list of pairs too, which TiLiA's `OrderedDict.update` would take.
    "text",
    ["[]", '[["title", "x"]]', '"title"', "1", "null", "true"],
)
def test_a_file_that_isnt_an_object(tmp_path, text):
    doc = build.new_script_document()
    path = text_file(tmp_path, text)

    assert fails(doc, path) == JSON_FAILED.format(path, NOT_AN_OBJECT)


def test_a_file_that_isnt_utf8(tmp_path):
    doc = build.new_script_document()
    path = tmp_path / "metadata.json"
    path.write_bytes('{"compositeur": "Dvořák"}'.encode("cp1250"))

    assert fails(doc, path) == UTF8_DECODE_FAILED.format(path)


def nested(opening: str, closing: str, levels: int) -> str:
    # The top level counts as one, as in tla's reader.
    inner = opening * (levels - 1) + "1" + closing * (levels - 1)
    return '{"a": ' + inner + "}"


BRACKETS = [("[", "]"), ('{"a": ', "}")]


@pytest.mark.parametrize("opening, closing", BRACKETS)
def test_a_file_nested_up_to_the_limit(tmp_path, opening, closing):
    doc = build.new_script_document()

    importers.import_metadata(doc, text_file(tmp_path, nested(opening, closing, 100)))

    assert doc.metadata["a"] == opening * 99 + "1" + closing * 99


@pytest.mark.parametrize("opening, closing", BRACKETS)
@pytest.mark.parametrize("levels", [101, 100_000])
def test_a_file_nested_too_deep(tmp_path, opening, closing, levels):
    # 101 levels: every Python reads them. 100,000: some systems' parsers run
    # out of stack, others don't. The limit is tla's reader's.
    doc = build.new_script_document()
    path = text_file(tmp_path, nested(opening, closing, levels))

    assert fails(doc, path) == JSON_FAILED.format(path, TOO_DEEP)


@pytest.mark.parametrize(
    "after",
    [', "b": }', ', "b": ' + "1" * 5000 + "}"],
    ids=["not JSON", "a number too long to read"],
)
def test_a_file_nested_too_deep_before_another_problem(tmp_path, after):
    # Whether json.loads runs out of stack at 2000 levels, before it meets the
    # error or the number too long to read, depends on the Python version. The
    # first problem in the file is the depth, on every one.
    doc = build.new_script_document()
    path = text_file(tmp_path, nested("[", "]", 2000)[:-1] + after)

    assert fails(doc, path) == JSON_FAILED.format(path, TOO_DEEP)


def test_a_file_that_isnt_json_before_it_nests_too_deep(tmp_path):
    doc = build.new_script_document()
    path = text_file(tmp_path, '{"b": x, ' + nested("[", "]", 2000)[1:])

    error = "Expecting value: line 1 column 7 (char 6)"
    assert fails(doc, path) == JSON_FAILED.format(path, f"JSONDecodeError({error!r})")


@pytest.mark.skipif(
    not hasattr(sys, "get_int_max_str_digits"), reason="no limit on this Python"
)
def test_a_number_too_long_to_read_before_the_file_nests_too_deep(tmp_path):
    doc = build.new_script_document()
    path = text_file(
        tmp_path, '{"b": ' + "1" * 5000 + ", " + nested("[", "]", 2000)[1:]
    )

    message = fails(doc, path)

    assert message.startswith(f"Error when parsing file {path}:\nValueError(")


@pytest.mark.parametrize("text", ["[" * 200, '\\"' + "[" * 200, "{" * 200])
def test_brackets_in_text_dont_count(tmp_path, text):
    doc = build.new_script_document()

    importers.import_metadata(doc, text_file(tmp_path, f'{{"{text}": "{text}"}}'))

    unescaped = text.replace('\\"', '"')
    assert doc.metadata[unescaped] == unescaped


def test_a_text_that_never_closes_takes_little_time(tmp_path):
    # The nesting check reads it once: 200,000 escaped quotes take
    # milliseconds, where a pattern that starts again at each quote in it takes
    # minutes.
    doc = build.new_script_document()
    path = text_file(tmp_path, '{"a": "' + '\\"' * 200_000)

    start = time.perf_counter()
    message = fails(doc, path)
    assert time.perf_counter() - start < 1

    error = "Unterminated string starting at: line 1 column 7 (char 6)"
    assert message == JSON_FAILED.format(path, f"JSONDecodeError({error!r})")


def test_a_value_too_deep_to_write_as_text(tmp_path, monkeypatch):
    # Within the limit, json.dumps runs out of stack only for an import called
    # near the end of it.
    doc = build.new_script_document()
    path = json_file(tmp_path, {"composer": "Haydn", "work": {"a": [[1]]}})

    def too_deep(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(json, "dumps", too_deep)

    message = fails(doc, path)

    assert message == JSON_FAILED.format(
        path, "RecursionError('maximum recursion depth exceeded')"
    )


def test_a_file_that_cant_be_opened(tmp_path):
    # A folder: OSError, as the CSV reader raises it.
    doc = build.new_script_document()
    before = copy.deepcopy(doc)

    with pytest.raises(OSError):
        importers.import_metadata(doc, tmp_path)

    assert doc == before


@pytest.mark.skipif(
    not hasattr(sys, "get_int_max_str_digits"), reason="no limit on this Python"
)
def test_a_number_too_long_to_read(tmp_path):
    doc = build.new_script_document()
    path = text_file(tmp_path, '{"a": ' + "1" * 5000 + "}")

    message = fails(doc, path)

    assert message.startswith(f"Error when parsing file {path}:\nValueError(")


def test_a_failure_names_the_file_once(tmp_path):
    doc = build.new_script_document()
    path = tmp_path / "missing.json"

    with pytest.raises(ImportFailed) as error:
        importers.import_metadata(doc, path)

    assert str(error.value) == f"File {path} not found."


def test_a_refused_length_is_given_with_the_files_name(tmp_path):
    doc = build.new_script_document()
    path = json_file(tmp_path, {"media length": 0})

    with pytest.raises(ImportFailed) as error:
        importers.import_metadata(doc, path)

    assert str(error.value) == "metadata.json: " + NOT_A_MEDIA_LENGTH.format(0)
