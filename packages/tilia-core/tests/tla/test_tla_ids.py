import copy
import hashlib
import json
import threading
import time
import tracemalloc
import unicodedata
import uuid
from types import SimpleNamespace

import pytest

from tilia_core.tla import ids
from tilia_core.tla.ids import derived_document_id, migrated_id, new_id
from tilia_core.tla.parse import parse

BASE_MS = 946_684_800_000  # 2000-01-01T00:00:00Z
DOC = "0190a3c2-7e5f-7a1b-8c3d-4e5f6a7b8c9d"


def time_field(value: str) -> int:
    return uuid.UUID(value).int >> 80


class TestNewId:
    def test_is_a_uuid7(self):
        value = new_id()
        parsed = uuid.UUID(value)
        assert parsed.variant == uuid.RFC_4122
        assert parsed.version == 7
        assert str(parsed) == value

    def test_time_field_is_now(self):
        assert abs(time_field(new_id()) - time.time() * 1000) < 5000

    def test_unique_and_ordered_in_one_thread(self):
        ids = [new_id() for _ in range(10_000)]
        assert len(set(ids)) == len(ids)
        assert ids == sorted(ids)

    def test_unique_and_ordered_in_four_threads(self):
        results: list[list[str]] = [[] for _ in range(4)]

        def make(out: list[str]) -> None:
            for _ in range(2_500):
                out.append(new_id())

        threads = [threading.Thread(target=make, args=(out,)) for out in results]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        everything = [value for out in results for value in out]
        assert len(everything) == 10_000
        assert len(set(everything)) == len(everything)
        for out in results:
            assert out == sorted(out)

    def test_low_bits_are_random(self):
        low = {uuid.UUID(new_id()).int & (2**62 - 1) for _ in range(100)}
        assert len(low) == 100


NOW_MS = 1_760_000_000_000


def fake_clock(monkeypatch, *ms: int) -> None:
    """Make `ids`' clock read the given milliseconds, in turn, then the last one."""
    readings = list(ms)

    def time_ns() -> int:
        return (readings.pop(0) if len(readings) > 1 else readings[0]) * 1_000_000

    monkeypatch.setattr(ids, "time", SimpleNamespace(time_ns=time_ns))


class TestClock:
    def test_counts_on_within_a_millisecond(self, monkeypatch):
        fake_clock(monkeypatch, NOW_MS)
        clock = ids._Clock()
        (ms, first), (ms_again, second) = clock.next(), clock.next()
        assert ms == ms_again == NOW_MS
        assert second == first + 1

    def test_a_full_counter_moves_on_to_the_next_millisecond(self, monkeypatch):
        # 12 bits count within one millisecond; past them, the next one starts.
        # Each millisecond's counter starts at a random value: 0 here.
        fake_clock(monkeypatch, NOW_MS)
        monkeypatch.setattr(ids, "secrets", SimpleNamespace(randbits=lambda bits: 0))
        clock = ids._Clock()
        readings = [clock.next() for _ in range(5_000)]
        assert readings == sorted(set(readings))
        assert readings[2**12 - 1] == (NOW_MS, 2**12 - 1)
        assert readings[2**12] == (NOW_MS + 1, 0)

    def test_stays_in_order_when_the_clock_goes_back(self, monkeypatch):
        fake_clock(monkeypatch, NOW_MS, NOW_MS - 5, NOW_MS - 5)
        clock = ids._Clock()
        readings = [clock.next() for _ in range(3)]
        assert readings == sorted(set(readings))
        assert {ms for ms, _ in readings} == {NOW_MS}

    def test_two_threads_never_get_the_same_reading(self, monkeypatch):
        # The lock keeps a second thread out while the first one has read the
        # clock but not yet moved its state on. Without it, the second one gets
        # the same millisecond and counter.
        fake_clock(monkeypatch, NOW_MS)
        clock = ids._Clock()
        readings = []
        other = threading.Thread(target=lambda: readings.append(clock.next()))
        started = []

        def randbits(bits: int) -> int:
            if not started:
                started.append(True)
                other.start()
                # At once without the lock; with it, the other thread waits.
                other.join(timeout=0.2)
            return 7

        monkeypatch.setattr(ids, "secrets", SimpleNamespace(randbits=randbits))
        readings.append(clock.next())
        other.join()
        assert len(set(readings)) == 2


class TestMigratedId:
    def test_is_deterministic(self):
        assert migrated_id(DOC, "component", "3", "12") == migrated_id(
            DOC, "component", "3", "12"
        )

    def test_is_a_uuid7(self):
        parsed = uuid.UUID(migrated_id(DOC, "timeline", "3"))
        assert parsed.variant == uuid.RFC_4122
        assert parsed.version == 7

    def test_time_field_is_the_base_plus_the_old_id(self):
        assert time_field(migrated_id(DOC, "component", "3", "12")) == BASE_MS + 12
        assert time_field(migrated_id(DOC, "timeline", "3")) == BASE_MS + 3
        assert time_field(migrated_id(DOC, "timeline", 0)) == BASE_MS

    def test_an_integer_and_its_text_give_the_same_id(self):
        assert migrated_id(DOC, "component", 3, 12) == migrated_id(
            DOC, "component", "3", "12"
        )

    def test_differs_between_kinds(self):
        ids = {
            migrated_id(DOC, kind, "3") for kind in ("timeline", "component", "score")
        }
        assert len(ids) == 3

    def test_differs_between_documents(self):
        other = "0190a3c2-7e5f-7a1b-8c3d-000000000000"
        assert migrated_id(DOC, "timeline", "3") != migrated_id(other, "timeline", "3")

    def test_differs_between_timelines(self):
        assert migrated_id(DOC, "component", "3", "12") != migrated_id(
            DOC, "component", "4", "12"
        )

    def test_differs_however_the_old_ids_split_the_same_text(self):
        assert migrated_id(DOC, "component", "a\x1fb", "c", position=0) != (
            migrated_id(DOC, "component", "a", "b\x1fc", position=0)
        )

    def test_sorts_as_the_old_ids_did(self):
        old = [100, 2, 10, 1000, 0]
        ids = {migrated_id(DOC, "component", "1", str(i)): i for i in old}
        assert [ids[value] for value in sorted(ids)] == sorted(old)

    def test_sorts_before_a_new_id(self):
        assert migrated_id(DOC, "component", "1", "99999") < new_id()

    def test_non_integer_takes_the_base_plus_2_38_plus_its_position(self):
        value = migrated_id(DOC, "component", "1", "a7", position=3)
        assert time_field(value) == BASE_MS + 2**38 + 3

    @pytest.mark.parametrize("old", [2**38 - 1, str(2**38 - 1)])
    def test_the_largest_integer(self, old):
        assert time_field(migrated_id(DOC, "component", "1", old)) == (
            BASE_MS + 2**38 - 1
        )

    @pytest.mark.parametrize(
        "old", ["a7", "", "-3", "03", "1.5", " 4", -3, 2**38, str(2**38), True]
    )
    def test_what_counts_as_not_an_integer(self, old):
        value = migrated_id(DOC, "component", "1", old, position=0)
        assert time_field(value) == BASE_MS + 2**38

    def test_a_very_long_numeric_old_id_isnt_an_integer(self):
        # Longer than Python's int() reads, by default, since 3.10.7.
        value = migrated_id(DOC, "component", "1", "9" * 5000, position=0)
        assert time_field(value) == BASE_MS + 2**38

    def test_non_integer_ids_sort_after_integer_ones(self):
        assert migrated_id(DOC, "component", "1", "x", position=0) > migrated_id(
            DOC, "component", "1", "999999"
        )

    def test_every_migrated_id_sorts_before_a_new_one(self):
        # Entries made after a migration sort after the migrated ones. The time
        # fields stay below 2000-01-01 plus 2**39 ms, in June 2017.
        latest = [
            migrated_id(DOC, "component", "1", 2**38 - 1),
            migrated_id(DOC, "component", "1", "x", position=2**38 - 1),
        ]
        assert max(time_field(value) for value in latest) == BASE_MS + 2**39 - 1
        assert max(latest) < new_id()

    @pytest.mark.parametrize("position", [None, -1, 2**38, 3.0, True])
    def test_non_integer_without_a_position_it_can_take_raises(self, position):
        with pytest.raises(ValueError):
            migrated_id(DOC, "component", "1", "a7", position=position)

    def test_a_lone_surrogate_in_an_old_id(self):
        value = migrated_id(DOC, "component", "1", chr(0xD83C), position=0)
        assert time_field(value) == BASE_MS + 2**38

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            migrated_id(DOC, "measure", "1")

    def test_no_old_id_raises(self):
        with pytest.raises(ValueError):
            migrated_id(DOC, "timeline")

    def test_never_changes(self):
        # Files read before and after an update must get the same ids.
        assert migrated_id(DOC, "component", "3", "12") == (
            "00dc6acf-ac0c-7675-8593-1b87a585215c"
        )


def old_file() -> dict:
    return {
        "file_path": "C:/Users/someone/corpus/piece.tla",
        "media_path": "C:/Users/someone/corpus/piece.mp3",
        "media_metadata": {
            "title": "Piece",
            "notes": "",
            "media length": 120.5,
            "composer": "Dvořák",
        },
        "timelines": {
            "1": {
                "kind": "Hierarchy",
                "name": "Form",
                "ordinal": 1,
                "height": 30,
                "is_visible": True,
                "hash": "0a1b",
                "components_hash": "2c3d",
                "components": {
                    "2": {
                        "kind": "HIERARCHY",
                        "start": 0,
                        "end": 10.5,
                        "level": 1,
                        "label": "Exposição",
                        "hash": "4e5f",
                    }
                },
            }
        },
        "timelines_hash": "6a7b",
        "app_name": "TiLiA",
        "version": "0.6.0",
    }


def edited(change) -> dict:
    data = old_file()
    change(data)
    return data


def set_key(*path_and_value):
    *path, key, value = path_and_value

    def change(data):
        for step in path:
            data = data[step]
        data[key] = value

    return change


def remove_key(*path):
    *path, key = path

    def change(data):
        for step in path:
            data = data[step]
        del data[key]

    return change


def normalized(data, form):
    if isinstance(data, str):
        return unicodedata.normalize(form, data)
    if isinstance(data, dict):
        return {
            normalized(key, form): normalized(value, form)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [normalized(value, form) for value in data]
    return data


def nfd(data):
    return normalized(data, "NFD")


def nfc(data):
    return normalized(data, "NFC")


class TestDerivedDocumentId:
    def test_is_a_uuid8(self):
        parsed = uuid.UUID(derived_document_id(old_file()))
        assert parsed.variant == uuid.RFC_4122
        assert parsed.version == 8

    @pytest.mark.parametrize(
        "change",
        [
            set_key("file_path", "/home/other/elsewhere/piece.tla"),
            remove_key("file_path"),
            set_key("version", "0.7.0"),
            set_key("app_name", "TiLiA 2"),
            set_key("timelines_hash", "ffff"),
            set_key("timelines", "1", "hash", "ffff"),
            set_key("timelines", "1", "components_hash", "ffff"),
            set_key("timelines", "1", "components", "2", "hash", "ffff"),
            set_key("media_metadata", "media length", 121.0),
            remove_key("media_metadata", "media length"),
        ],
    )
    def test_unchanged_by_what_changes_without_an_edit(self, change):
        assert derived_document_id(edited(change)) == derived_document_id(old_file())

    def test_unchanged_by_nfd_text(self):
        assert derived_document_id(nfd(old_file())) == derived_document_id(old_file())

    def test_unchanged_by_key_order(self):
        data = old_file()
        reordered = dict(reversed(list(data.items())))
        assert derived_document_id(reordered) == derived_document_id(data)

    @pytest.mark.parametrize(
        "place",
        [("timelines", "1", "height"), ("timelines", "1", "components", "2", "start")],
    )
    @pytest.mark.parametrize(
        "integer, number", [(10, 10.0), (0, -0.0), (10**20, 1e20)]
    )
    def test_numbers_by_value(self, place, integer, number):
        def with_value(value):
            return derived_document_id(edited(set_key(*place, value)))

        assert with_value(integer) == with_value(number)

    def test_keys_that_nfc_would_merge_keep_both_values(self):
        decomposed, composed = "é", "é"

        def with_fields(fields):
            return derived_document_id(edited(set_key("media_metadata", "x", fields)))

        both = with_fields({decomposed: "a", composed: "b"})
        assert both != with_fields({composed: "b"})
        assert both != with_fields({composed: "a"})
        assert both == with_fields({composed: "b", decomposed: "a"})
        assert with_fields({decomposed: "a"}) == with_fields({composed: "a"})

    def test_unchanged_by_crlf_and_a_byte_order_mark(self):
        text = json.dumps(old_file(), indent=2, ensure_ascii=False)
        lf = text.encode("utf-8")
        crlf_bom = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        assert derived_document_id(parse(lf)) == derived_document_id(parse(crlf_bom))

    @pytest.mark.parametrize(
        "change",
        [
            set_key("timelines", "1", "components", "2", "label", "Exposition"),
            set_key("timelines", "1", "components", "2", "start", 0.5),
            set_key("media_metadata", "composer", "Dvorak"),
            set_key("media_metadata", "hash", "a field a user added"),
            set_key("media_path", "C:/Users/someone/corpus/other.mp3"),
        ],
    )
    def test_changed_by_an_edit(self, change):
        assert derived_document_id(edited(change)) != derived_document_id(old_file())

    def test_a_lone_surrogate_gives_an_id(self):
        # TiLiA saved a label cut inside an emoji as an escaped lone surrogate.
        label = {"label": chr(0xD83C)}
        data = parse(
            json.dumps({"timelines": {"1": {"components": {"2": label}}}}).encode()
        )
        assert uuid.UUID(derived_document_id(data)).version == 8

    def test_leaves_its_argument_alone(self):
        data = old_file()
        before = copy.deepcopy(data)
        derived_document_id(data)
        assert data == before

    def test_is_the_sha256_of_one_sorted_json_text_in_nfc(self):
        # However the content is taken apart to be hashed.
        data = {
            "timelines": {
                "1": {
                    "svg_data": "x" + "é" * 40_000 + '"\\\n\x00' + chr(0xD83C),
                    "viewer_beat_x": [0.5, 1, None, True, [], {}, ""],
                    "components": {
                        "2": {"label": nfd("Exposição"), "deep": [[{"a": [1.25]}]]},
                        "10": {},
                    },
                }
            },
            "media_metadata": {nfd("título"): "x"},
            "z": [[[["deep"]]], "é" * 70_000],
        }
        text = json.dumps(
            nfc(data), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()
        version_and_variant = 0xF << 76 | 0b11 << 62
        expected = int.from_bytes(digest[:16], "big") & ~version_and_variant
        assert uuid.UUID(derived_document_id(data)).int & ~version_and_variant == (
            expected
        )

    def test_hashes_long_text_in_slices(self):
        # An old file holds its score's SVG, megabytes long.
        svg = "<svg>" + "x" * 4_000_000 + "</svg>"
        data = edited(set_key("timelines", "1", "svg_data", svg))
        # Leaves tracing as it found it, for a run with -X tracemalloc.
        tracing = tracemalloc.is_tracing()
        if not tracing:
            tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        try:
            derived_document_id(data)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            if not tracing:
                tracemalloc.stop()
        assert peak - before < len(svg) / 4

    def test_never_changes(self):
        # Files read before and after an update must get the same id.
        assert derived_document_id(old_file()) == "03209ea7-1448-859f-900b-712a89d6f7c2"
