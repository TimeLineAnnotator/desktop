import sys
from pathlib import Path

import pytest

from tilia_core.tla import UnreadableFile
from tilia_core.tla.parse import parse

BOM = b"\xef\xbb\xbf"
MINIMAL = b'{\n  "timelines": {}\n}\n'


def crlf(data: bytes) -> bytes:
    return data.replace(b"\n", b"\r\n")


def refusal(data: bytes, path: Path | None = None) -> UnreadableFile:
    with pytest.raises(UnreadableFile) as info:
        parse(data, path=path)
    return info.value


def test_reads_an_object_with_timelines():
    assert parse(MINIMAL) == {"timelines": {}}


def test_strips_one_byte_order_mark():
    assert parse(BOM + MINIMAL) == {"timelines": {}}


def test_reads_crlf_like_lf():
    assert parse(crlf(MINIMAL)) == {"timelines": {}}


def test_keeps_numbers_exact():
    data = parse(b'{"timelines": {}, "a": 12.345678901, "b": 0.30000000000000004}')
    assert data["a"] == 12.345678901
    assert data["b"] == 0.1 + 0.2


def test_keeps_text_as_it_is():
    decomposed = "Dvořák"
    data = parse(('{"timelines": {}, "a": "' + decomposed + '"}').encode("utf-8"))
    assert data["a"] == decomposed


INVALID = b'{\n  "timelines": {},\n  "a": 1\n  "b": 2\n}\n'


@pytest.mark.parametrize("data", [INVALID, crlf(INVALID), BOM + crlf(INVALID)])
def test_invalid_json_gives_its_line(data):
    error = refusal(data)
    assert error.line == 4
    assert error.message == "not valid JSON (Expecting ',' delimiter)"
    assert error.place is None


def test_error_names_the_file():
    error = refusal(INVALID, Path("corpus") / "piece.tla")
    assert error.path == Path("corpus") / "piece.tla"
    assert str(error) == "piece.tla, line 4: not valid JSON (Expecting ',' delimiter)"


def test_error_names_a_file_given_as_text():
    error = refusal(INVALID, "corpus/piece.tla")
    assert error.path == Path("corpus") / "piece.tla"
    assert str(error) == "piece.tla, line 4: not valid JSON (Expecting ',' delimiter)"


def test_error_without_a_file():
    assert str(refusal(INVALID)) == "line 4: not valid JSON (Expecting ',' delimiter)"


def test_is_a_value_error():
    assert isinstance(refusal(INVALID), ValueError)


REPEATED = b"""{
  "timelines": {
    "t1": {
      "name": "A",
      "name": "B"
    }
  }
}
"""


@pytest.mark.parametrize("data", [REPEATED, crlf(REPEATED), BOM + REPEATED])
def test_repeated_key_gives_its_place_and_line(data):
    error = refusal(data)
    assert error.place == "/timelines/t1/name"
    assert error.line == 5
    assert '"name"' in error.message


@pytest.mark.parametrize(
    "data, place, line",
    [
        (b'{"timelines": {},\n"timelines": {}}', "/timelines", 2),
        (
            b'{"timelines": {}, "scores": [\n{"id": "a"},\n{"id": "b", "id": "c"}]}',
            "/scores/1/id",
            3,
        ),
        (b'{"timelines": {}, "a/b": {"x~y": 1, "x~y": 2}}', "/a~1b/x~0y", 1),
        (b'{"timelines": {}, "a": {"": 1, "": 2}}', "/a/", 1),
        (b'{"timelines": {}, "a\\u00e9": {"k": 1, "\\u006b": 2}}', "/aé/k", 1),
    ],
)
def test_repeated_key_anywhere(data, place, line):
    error = refusal(data)
    assert (error.place, error.line) == (place, line)


def test_repeated_key_message_when_the_second_pass_finds_nothing(monkeypatch):
    from tilia_core.tla import parse as module

    monkeypatch.setattr(module, "_find", lambda text, keys: (None, None, None))
    error = refusal(REPEATED)
    assert error.message == "a key appears twice in one object"
    assert (error.place, error.line) == (None, None)


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
def test_nan_and_infinity_are_not_json(constant):
    error = refusal(b'{\n  "timelines": {},\n  "a": [1,\n' + constant + b"]\n}\n")
    assert error.message == "not valid JSON (Expecting value)"
    assert error.line == 4
    assert error.place is None


def test_nan_after_a_repeated_key_in_an_open_object():
    # json.loads meets the NaN before it closes the object with the repeated key.
    error = refusal(b'{"timelines": {}, "a": 1, "a": 2,\n"b": NaN}')
    assert error.message == "not valid JSON (Expecting value)"
    assert error.line == 2


def test_nan_as_text_is_fine():
    assert parse(b'{"timelines": {}, "a": "NaN"}')["a"] == "NaN"


# Python 3.10.7 and later read no integer longer than this, unless told to.
INT_DIGITS = getattr(sys, "get_int_max_str_digits", lambda: 0)()


@pytest.mark.skipif(not INT_DIGITS, reason="this Python reads integers of any length")
def test_a_number_too_long_to_read():
    number = b"1" * (INT_DIGITS + 1)
    error = refusal(b'{\n  "timelines": {},\n  "a": [1,\n' + number + b"]\n}\n")
    assert error.message == "number too long to read"
    assert error.line == 4
    assert error.place is None


def nested(opening: bytes, closing: bytes, levels: int) -> bytes:
    # The top level counts as one.
    inner = opening * levels + b"1" + closing * levels
    return b'{"timelines": {}, "x": ' + inner + b"}"


BRACKETS = [(b"[", b"]"), (b'{"a":', b"}")]


@pytest.mark.parametrize("opening, closing", BRACKETS)
@pytest.mark.parametrize("levels", [100, 100_000])
def test_nested_too_deeply(opening, closing, levels):
    # 100,000 levels: some systems' parsers run out of stack, others don't.
    error = refusal(nested(opening, closing, levels))
    assert error.message == "nested more than 100 levels deep"


@pytest.mark.parametrize("opening, closing", BRACKETS)
def test_nested_up_to_the_limit(opening, closing):
    assert parse(nested(opening, closing, 99))


def test_the_same_key_in_two_objects_is_fine():
    assert parse(b'{"timelines": {"a": {"name": 1}, "b": {"name": 2}}}')


@pytest.mark.parametrize("data", [b"", BOM, b"  \n", BOM + b"\r\n"])
def test_empty_file(data):
    error = refusal(data)
    assert error.message == "empty file"
    assert error.line is None


@pytest.mark.parametrize(
    "data", [b"[]", b'"text"', b"3", b"null", b'{"a": 1}', b'{"Timelines": {}}']
)
def test_not_a_tilia_file(data):
    assert refusal(data).message == "not a TiLiA file"


@pytest.mark.parametrize("prefix", [b"", BOM])
def test_invalid_utf8_gives_its_byte_and_line(prefix):
    data = prefix + b'{\n  "timelines": {},\n  "name": "\xff"\n}\n'
    offset = data.index(b"\xff")
    error = refusal(data)
    assert error.message == f"not UTF-8, at byte {offset}"
    assert error.line == 3
