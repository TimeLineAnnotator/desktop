"""Harmonies by time, and the symbol reading. The tests ported from TiLiA's
`test_harmony_from_csv.py`, `test_harmony_timeline.py` and
`test_select_harmony_params.py` keep their names and their cases; where they look
for a value in an error, these give the whole message. A value that can't be read
reads as the rules read it, not as TiLiA's importer does
(TimeLineAnnotator/project-management#298).

Everything but what happens without music21 needs the harmony extra."""

import copy
import importlib
import importlib.util
import json
import logging
import sys
import uuid

import pytest
from import_docs import component, document, timeline

from tilia_core import importers, rules, tla
from tilia_core.importers import harmony
from tilia_core.importers._csv import CsvRow
from tilia_core.importers._results import ImportFailed, RowProblem

HARMONY_EXTRA = 'harmony import needs: pip install "tilia-core[harmony]"'
HEADER = "time,harmony_or_key,symbol"
OPTIONAL_HEADER = "comments,display_mode,custom_text,custom_text_font_type"
OPTIONAL_ROW = "a comment,roman,my text,normal"


@pytest.fixture
def music21():
    return pytest.importorskip("music21", reason="needs the harmony extra")


@pytest.fixture
def imported(music21, tmp_path):
    """Writes a CSV, and imports it into a new harmony timeline."""

    def run(data, *, media_length=60.0, time_unit="seconds", components=()):
        path = tmp_path / "harmonies.csv"
        path.write_text(data, encoding="utf-8", newline="")
        target = timeline("harmony", components=components)
        doc = document(
            timelines=[target], media_length=media_length, time_unit=time_unit
        )
        return harmony.import_by_time(doc, target.id, path), target, path

    return run


@pytest.fixture
def without_the_extra(monkeypatch):
    find_spec = importlib.util.find_spec

    def find_spec_without_music21(name, *args, **kwargs):
        if name == "music21":
            return None
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec_without_music21)


@pytest.fixture
def music21_that_wont_import(tmp_path, monkeypatch):
    # Installed, so found, but importing it fails, as with a numpy it can't use.
    package = tmp_path / "music21"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise AttributeError("np.float_ was removed in \\udc80 NumPy 2.0.")\n'
    )
    for name in [name for name in sys.modules if name.partition(".")[0] == "music21"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()


def rows(*cells):
    return "\n".join([HEADER, *cells])


def chords(target):
    return [c.attrs for c in target.components.values() if c.kind == "harmony"]


def keys(target):
    return [c.attrs for c in target.components.values() if c.kind == "mode"]


def messages(result):
    return [problem.message for problem in result.problems]


class TestByTime:
    @pytest.mark.parametrize(
        "symbol,step,accidental,quality",
        [
            ("C#", 0, 1, "major"),
            ("C7b9", 0, 0, "dominant-seventh-flat-ninth"),
            ("V7b9", 4, 0, "dominant-seventh-flat-ninth"),
            ("C6/9", 0, 0, "major-sixth-added-ninth"),
            ("Dm7(11)", 1, 0, "minor-seventh-added-eleventh"),
            ("Iadd9", 0, 0, "major-added-ninth"),
            ("V(64)", 4, 0, "cadential-six-four"),
            ("Cad64", 4, 0, "cadential-six-four"),
        ],
    )
    def test_harmony_by_time(self, imported, symbol, step, accidental, quality):
        result, target, _ = imported(f"time,harmony_or_key,symbol\n0,harmony,{symbol}")

        assert result.problems == []
        assert [c.kind for c in target.components.values()] == ["harmony"]
        assert chords(target) == [
            {
                "time": 0.0,
                "comments": "",
                "step": step,
                "accidental": accidental,
                "quality": quality,
                "inversion": 0,
                "applied_to": 0,
                "level": 1,
                "display_mode": "letter",
                "custom_text": "",
                "custom_text_font_type": "analytic",
            }
        ]

    @pytest.mark.parametrize(
        "symbol,step,accidental,type",
        [("C#", 0, 1, "major"), ("d", 1, 0, "minor"), ("Ebb", 2, -2, "major")],
    )
    def test_mode_by_time(self, imported, symbol, step, accidental, type):
        result, target, _ = imported(f"time,harmony_or_key,symbol\n0,key,{symbol}")

        assert result.problems == []
        assert [c.kind for c in target.components.values()] == ["mode"]
        assert keys(target) == [
            {
                "time": 0.0,
                "step": step,
                "accidental": accidental,
                "type": type,
                "comments": "",
                "level": 2,
            }
        ]

    @pytest.mark.parametrize("required_attr", ["time", "symbol", "harmony_or_key"])
    def test_fails_without_a_required_column(self, imported, required_attr):
        data = "time,harmony_or_key,symbol,".replace(f"{required_attr},", "")

        with pytest.raises(ImportFailed) as failed:
            imported(data)

        assert failed.value.message == (
            f"Column '{required_attr}' not found on first row of .csv file."
        )

    def test_returns_error_for_invalid_rows_and_processes_valid_rows(self, imported):
        result, target, _ = imported(
            rows("0,harmony,C", "10,nonsense,X", "20,harmony,D")
        )

        assert [a["time"] for a in chords(target)] == [0.0, 20.0]
        assert messages(result) == ["nonsense is not a valid harmony or key."]

    def test_returns_reason_for_invalid_component(self, imported):
        result, target, _ = imported(rows("0,harmony,C", "0,harmony,D"))

        assert messages(result) == [
            "There is already a harmony component at the selected position."
        ]
        assert [a["step"] for a in chords(target)] == [0]

    @pytest.mark.parametrize(
        "row, column, attribute",
        [
            ("cursed input,harmony,C", "time", "time"),
            ("0,cursed input,C", "harmony_or_key", "harmony or key"),
            ("0,harmony,cursed input", "symbol", "symbol"),
        ],
    )
    def test_fails_if_invalid_attr_value(self, imported, row, column, attribute):
        result, target, path = imported(rows(row))

        assert result.problems == [
            RowProblem(
                path=path,
                line=2,
                column=column,
                message=f"cursed input is not a valid {attribute}.",
                skipped=True,
            )
        ]
        assert target.components == {}

    def test_row_fails_if_missing_required_value(self, imported):
        result, target, _ = imported(rows("0,harmony", "0,harmony,D"))

        assert messages(result) == ["an empty value is not a valid symbol."]
        assert result.problems[0].column == "symbol"
        assert [a["step"] for a in chords(target)] == [1]

    def test_row_does_not_fail_if_missing_non_required_value(self, imported):
        # As in the other importers, and where TiLiA reports it and imports the row:
        # a column the row is too short for is its default.
        result, target, _ = imported(
            "time,harmony_or_key,symbol,display_mode\n0,harmony,C\n10,harmony,D,letter"
        )

        assert result.problems == []
        assert len(chords(target)) == 2

    def test_text_appended_to_error_is_displayed(self, imported):
        # TiLiA appends 'Must be "harmony" or "key".'; there is now one text for a
        # value that isn't one (FR-022).
        result, _, _ = imported(rows("0,nonsense,C"))

        assert messages(result) == ["nonsense is not a valid harmony or key."]

    def test_added_tone_in_the_bass_is_reported(self, imported):
        result, target, _ = imported(rows("0,harmony,C7b9/Db"))

        assert messages(result) == ["C7b9/Db is not a valid symbol."]
        assert target.components == {}

    def test_harmony_doesnt_consider_a_key_the_import_replaces(self, imported):
        # TiLiA's `test_harmony_considers_existing_key` calls its importer on a
        # timeline holding a key, which its callers clear first. An import replaces
        # what the timeline holds (FR-032), so IV is read in C.
        old = component(
            "mode", time=0.0, step=2, accidental=0, type="major", comments="", level=2
        )

        result, target, _ = imported(rows("0,harmony,IV"), components=[old])

        assert result.problems == []
        assert [a["step"] for a in chords(target)] == [3]
        assert keys(target) == []

    def test_harmony_considers_key_created_on_previous_row(self, imported):
        _, target, _ = imported(rows("0,key,E", "0,harmony,IV"))

        assert [a["step"] for a in chords(target)] == [5]


class TestRomanNumeralsInAMinorKey:
    # In a minor key, the case of a numeral chooses the sixth and seventh
    # degrees, as in music21's RomanNumeral, which the CSV import reads.
    @pytest.mark.parametrize(
        "symbol,step,accidental,quality",
        [
            ("vi", 3, 1, "minor"),  # F#m
            ("vio", 3, 1, "diminished"),  # F#o
            ("vii", 4, 1, "minor"),  # G#m
            ("viio", 4, 1, "diminished"),  # G#o
            ("viio7", 4, 1, "diminished-seventh"),  # G#o7
            ("VI", 3, 0, "major"),  # F
            ("VII", 4, 0, "major"),  # G
            ("#VII", 4, 1, "major"),  # G#
            ("bvi", 3, 0, "minor"),  # Fm
            ("bvii", 4, 0, "minor"),  # Gm
        ],
    )
    def test_numeral_is_read_in_the_key(
        self, imported, symbol, step, accidental, quality
    ):
        result, target, _ = imported(rows("0,key,a", f"1,harmony,{symbol}"))

        assert result.problems == []
        [chord] = chords(target)
        assert (chord["step"], chord["accidental"], chord["quality"]) == (
            step,
            accidental,
            quality,
        )

    def test_imported_numeral_keeps_its_display_mode(self, imported):
        # What TiLiA's `test_imported_numeral_is_labelled_as_it_was_written` needs of
        # the importer: drawing the label is the app's. A key has no display mode.
        result, target, _ = imported(
            "time,harmony_or_key,symbol,display_mode\n0,key,a,roman\n1,harmony,vi,roman"
        )

        assert result.problems == []
        assert [a["display_mode"] for a in chords(target)] == ["roman"]
        assert "display_mode" not in keys(target)[0]


class TestOptionalColumns:
    def test_harmony_by_time(self, imported):
        result, target, _ = imported(
            f"{HEADER},{OPTIONAL_HEADER}\n0,harmony,C,{OPTIONAL_ROW}"
        )

        assert result.problems == []
        [chord] = chords(target)
        assert chord["comments"] == "a comment"
        assert chord["display_mode"] == "roman"
        assert chord["custom_text"] == "my text"
        assert chord["custom_text_font_type"] == "normal"

    def test_key_by_time(self, imported):
        # A key takes only the comments, as TiLiA gives it only them.
        result, target, _ = imported(
            f"{HEADER},{OPTIONAL_HEADER}\n0,key,C,{OPTIONAL_ROW}"
        )

        assert result.problems == []
        assert keys(target) == [
            {
                "time": 0.0,
                "step": 0,
                "accidental": 0,
                "type": "major",
                "comments": "a comment",
                "level": 2,
            }
        ]

    def test_absent_columns_keep_defaults_by_time(self, imported):
        result, target, _ = imported(rows("0,harmony,C", "10,key,D"))

        assert result.problems == []
        [chord] = chords(target)
        assert chord["comments"] == ""
        assert chord["display_mode"] == "letter"
        assert chord["custom_text"] == ""
        assert chord["custom_text_font_type"] == "analytic"
        assert keys(target)[0]["comments"] == ""

    @pytest.mark.parametrize("cell", ["", " ", " "])
    def test_a_cell_with_nothing_in_it_is_its_default(self, imported, cell):
        result, target, _ = imported(
            f"{HEADER},{OPTIONAL_HEADER}\n"
            f'0,harmony,C,"{cell}","{cell}","{cell}","{cell}"\n'
            f'1,key,C,"{cell}","{cell}","{cell}","{cell}"\n'
        )

        assert result.problems == []
        [chord] = chords(target)
        assert chord["comments"] == ""
        assert chord["display_mode"] == "letter"
        assert chord["custom_text"] == ""
        assert chord["custom_text_font_type"] == "analytic"
        assert keys(target)[0]["comments"] == ""

    @pytest.mark.parametrize(
        "column, attribute",
        [
            ("display_mode", "display mode"),
            ("custom_text_font_type", "custom text font type"),
        ],
    )
    def test_a_value_the_rules_refuse_skips_the_row(self, imported, column, attribute):
        # FR-037 and `contracts/rules.md`, where TiLiA reports the value and imports the
        # row with the default. Asked on TimeLineAnnotator/project-management#498.
        result, target, path = imported(
            f"{HEADER},{column},comments\n0,harmony,C,nonsense,hello\n1,harmony,D,,\n"
        )

        assert result.problems == [
            RowProblem(
                path=path,
                line=2,
                column=column,
                message=f"nonsense is not a valid {attribute}.",
                skipped=True,
            )
        ]
        assert [a["step"] for a in chords(target)] == [1]

    def test_a_key_doesnt_read_the_chords_columns(self, imported):
        # A key has neither attribute. Asked on
        # TimeLineAnnotator/project-management#498.
        result, target, _ = imported(
            f"{HEADER},display_mode,custom_text_font_type\n0,key,C,nonsense,nonsense\n"
        )

        assert result.problems == []
        assert len(keys(target)) == 1

    def test_columns_it_doesnt_know_are_ignored(self, imported):
        result, target, _ = imported(
            f"{HEADER},mood,step\n0,harmony,V,happy,0\n1,key,G,sad,0\n"
        )

        assert result.problems == []
        assert "mood" not in chords(target)[0]
        assert chords(target)[0]["step"] == 4
        assert keys(target)[0]["step"] == 4

    def test_a_text_is_stored_in_nfc(self, imported):
        _, target, _ = imported(f"{HEADER},comments\n0,harmony,C,café\n")

        assert chords(target)[0]["comments"] == "café"


class TestSymbolsThatRaise:
    def test_key_symbol_without_note_name_is_reported(self, imported):
        result, target, _ = imported(rows("0,key,X", "10,key,D"))

        assert messages(result) == ["X is not a valid symbol."]
        assert len(keys(target)) == 1

    def test_by_time(self, imported):
        result, target, _ = imported(
            rows("0,key,C", "10,key,F:min", "20,harmony,V42/bVII", "30,harmony,D")
        )

        assert messages(result) == [
            "F:min is not a valid symbol.",
            "V42/bVII is not a valid symbol.",
        ]
        assert len(keys(target)) == 1
        assert len(chords(target)) == 1

    @pytest.mark.parametrize(
        "kind, symbol", [("harmony", "V/bVI"), ("key", "F:min"), ("harmony", "Q")]
    )
    def test_a_symbol_it_cant_read_is_a_skipped_row(
        self, imported, kind, symbol, caplog
    ):
        with caplog.at_level(logging.WARNING):
            result, target, path = imported(
                rows("5,harmony,C", f"6,{kind},{symbol}", "7,key,C")
            )

        assert result.problems == [
            RowProblem(
                path=path,
                line=3,
                column="symbol",
                message=f"{symbol} is not a valid symbol.",
                skipped=True,
            )
        ]
        assert len(target.components) == 2
        assert caplog.records == []

    @pytest.mark.parametrize(
        "module, name, row",
        [
            ("roman", "RomanNumeral", "0,harmony,V"),
            ("harmony", "ChordSymbol", "0,harmony,C"),
            ("key", "Key", "0,key,G"),
        ],
    )
    def test_whatever_music21_raises(
        self, imported, music21, monkeypatch, caplog, module, name, row
    ):
        # FR-038. Not one of the kinds TiLiA's importer catches. Nothing is logged for
        # standard error, which holds `tilia run`'s reports.
        def raises(*_):
            raise AttributeError("music21 has no such thing")

        monkeypatch.setattr(getattr(music21, module), name, raises)

        with caplog.at_level(logging.WARNING):
            result, target, _ = imported(rows(row))

        assert len(messages(result)) == 1
        assert messages(result)[0].endswith("is not a valid symbol.")
        assert target.components == {}
        assert caplog.records == []

    def test_import_with_symbols_that_raise_keeps_the_rest(self, imported):
        # What TiLiA's `test_import_with_symbols_that_raise_is_one_undo_step` needs
        # of the importer: undoing is the app's.
        result, target, _ = imported(
            f"{HEADER},comments\n"
            "0,key,C,home key\n"
            "10,key,F:min,\n"
            "20,harmony,V42/bVII,\n"
            "30,harmony,D,a comment\n"
        )

        assert [problem.line for problem in result.problems] == [3, 4]
        assert [a["comments"] for a in keys(target)] == ["home key"]
        assert [a["comments"] for a in chords(target)] == ["a comment"]


class TestTheKeyInForce:
    def test_a_refused_key_changes_nothing(self, imported):
        # Keys C and G at 0, a chord V at 1: G major, read in C, as TiLiA reads it
        # (`contracts/rules.md`, Decisions 15).
        result, target, _ = imported(rows("0,key,C", "0,key,G", "1,harmony,V"))

        assert messages(result) == [
            "There is already a mode component at the selected position."
        ]
        assert [a["step"] for a in keys(target)] == [0]
        [chord] = chords(target)
        assert (chord["step"], chord["quality"]) == (4, "major")

    @pytest.mark.parametrize("time", ["-1", "nan"])
    def test_a_key_refused_for_its_time_changes_nothing(self, imported, time):
        result, target, _ = imported(rows(f"{time},key,G", "1,harmony,V"))

        assert len(result.problems) == 1
        assert keys(target) == []
        assert [a["step"] for a in chords(target)] == [4]

    def test_a_key_it_cant_read_changes_nothing(self, imported):
        _, target, _ = imported(rows("0,key,F:min", "1,harmony,V"))

        assert [a["step"] for a in chords(target)] == [4]

    def test_with_no_key_it_reads_in_c_major(self, imported):
        _, target, _ = imported(rows("1,harmony,V"))

        assert [a["step"] for a in chords(target)] == [4]

    def test_the_last_key_at_or_before_the_time(self, imported):
        # V is G in C (at 0.5), D in G (at 1 and 1.5), and A in D (at 2).
        _, target, _ = imported(
            rows(
                "0,key,C",
                "1,key,G",
                "2,key,D",
                "0.5,harmony,V",
                "1,harmony,V",
                "1.5,harmony,V",
                "2,harmony,V",
            )
        )

        assert [a["step"] for a in chords(target)] == [4, 1, 1, 5]

    def test_keys_are_found_by_their_times_not_by_their_rows(self, imported):
        _, target, _ = imported(
            rows("2,key,D", "0,key,G", "1,harmony,V", "3,harmony,V")
        )

        assert [a["step"] for a in chords(target)] == [1, 5]

    def test_a_key_in_a_later_row_doesnt_change_how_a_chord_reads(self, imported):
        # As in TiLiA, which reads each row with the keys of the rows before it.
        result, target, _ = imported(rows("1,harmony,V", "0,key,G"))

        assert result.problems == []
        assert [a["step"] for a in chords(target)] == [4]

    def test_a_key_of_another_mode_reads_the_numeral_in_it(self, imported):
        _, target, _ = imported(
            rows("0,key,Eb", "1,harmony,V", "2,key,c", "3,harmony,VI")
        )

        assert [(a["step"], a["accidental"]) for a in chords(target)] == [
            (6, -1),  # Bb, in E flat major
            (5, -1),  # Ab, in C minor
        ]


class TestAppliedTo:
    def test_it_comes_from_the_symbol(self, imported):
        _, target, _ = imported(rows("0,harmony,V/V", "1,harmony,V"))

        assert [a["applied_to"] for a in chords(target)] == [4, 0]

    def test_a_key_on_an_earlier_row_changes_how_a_later_chord_reads(self, imported):
        # Its `applied_to` is the symbol's: it is read with the key, not updated.
        _, target, _ = imported(rows("0,key,G", "1,harmony,V/V"))

        [chord] = chords(target)
        assert (chord["step"], chord["applied_to"]) == (5, 4)

    def test_a_key_updates_the_chords_of_the_rows_before_it(self, imported):
        # TiLiA's `_update_harmony_applied_to_on_mode_creation`: 4 + 0 - 1.
        result, target, _ = imported(rows("5,harmony,V/V", "1,key,D"))

        assert result.problems == []
        [chord] = chords(target)
        assert (chord["step"], chord["applied_to"]) == (1, 3)

    def test_it_counts_from_the_key_before_it(self, imported):
        # 4 + 1 (D, at 0) - 2 (E).
        _, target, _ = imported(rows("0,key,D", "5,harmony,V/V", "3,key,E"))

        assert [a["applied_to"] for a in chords(target)] == [3]

    def test_only_the_chords_up_to_the_next_key_are_updated(self, imported):
        # The key at 5 reaches the chords from 5 up to the next key's time, that
        # one's included, as TiLiA's `get_harmonies_in_harmonic_region` has it.
        _, target, _ = imported(
            rows(
                "10,key,F",
                "4.5,harmony,V/V",
                "5,harmony,V/V",
                "7,harmony,V/V",
                "10,harmony,V/V",
                "12,harmony,V/V",
                "5,key,D",
            )
        )

        assert [(a["time"], a["applied_to"]) for a in chords(target)] == [
            (4.5, 4),
            (5.0, 3),
            (7.0, 3),
            (10.0, 3),
            (12.0, 4),
        ]

    @pytest.mark.parametrize(
        "cells, applied_to",
        [
            (("5,harmony,C", "1,key,D"), 0),  # 0 + 0 - 1 is -1
            (("0,key,B", "5,harmony,V/IV", "1,key,C"), 3),  # 3 + 6 - 0 is 9
        ],
        ids=["below", "above"],
    )
    def test_a_value_set_data_would_refuse_is_left_as_it_was(
        self, imported, cells, applied_to
    ):
        # TiLiA's update goes through `set_data`, whose validator refuses it.
        result, target, _ = imported(rows(*cells))

        assert result.problems == []
        assert [a["applied_to"] for a in chords(target)] == [applied_to]

    @pytest.mark.parametrize(
        "cells, applied_to",
        [
            (("5,harmony,I/II", "1,key,D"), 0),  # 1 + 0 - 1
            (("0,key,B", "5,harmony,I", "1,key,C"), 6),  # 0 + 6 - 0
        ],
    )
    def test_the_lowest_and_the_highest_are_set(self, imported, cells, applied_to):
        _, target, _ = imported(rows(*cells))

        assert [a["applied_to"] for a in chords(target)] == [applied_to]

    @pytest.mark.parametrize(
        "cells",
        [
            ("0,key,C", "5,harmony,V/V", "0,key,D"),
            ("5,harmony,V/V", "-1,key,D"),
            ("5,harmony,V/V", "1,key,F:min"),
        ],
        ids=["at a kept one's time", "negative", "unreadable"],
    )
    def test_a_refused_key_updates_nothing(self, imported, cells):
        result, target, _ = imported(rows(*cells))

        assert len(result.problems) == 1
        assert [a["applied_to"] for a in chords(target)] == [4]

    def test_each_key_updates_in_row_order(self, imported):
        # 4 + 0 - 1 is 3, with the key at 1 (D); then 3 + 1 - 4 is 0, with G at 2.
        _, target, _ = imported(rows("5,harmony,V/V", "1,key,D", "2,key,G"))

        assert [a["applied_to"] for a in chords(target)] == [0]


class TestTheRules:
    @pytest.mark.parametrize("kind, symbol", [("harmony", "C"), ("key", "C")])
    @pytest.mark.parametrize(
        "time, message",
        [
            ("-1", "Time can't be negative. Got '-00:01.0'"),
            ("60.5", "Time '01:00.5' is bigger than media time '01:00.0'"),
            ("nan", "nan is not a valid time."),
            ("inf", "inf is not a valid time."),
        ],
    )
    def test_a_time_the_rules_refuse_is_skipped(
        self, imported, kind, symbol, time, message
    ):
        result, target, path = imported(rows(f"{time},{kind},{symbol}"))

        assert result.problems == [
            RowProblem(path=path, line=2, column="time", message=message, skipped=True)
        ]
        assert target.components == {}

    @pytest.mark.parametrize("kind", ["harmony", "key"])
    def test_a_time_at_the_media_length_is_kept(self, imported, kind):
        result, target, _ = imported(rows(f"60,{kind},C"))

        assert result.problems == []
        assert len(target.components) == 1

    def test_a_harmony_and_a_key_can_share_a_time(self, imported):
        result, target, _ = imported(rows("0,harmony,C", "0,key,C"))

        assert result.problems == []
        assert len(target.components) == 2

    @pytest.mark.parametrize(
        "kind, name", [("harmony", "harmony"), ("key", "mode")], ids=["chord", "key"]
    )
    def test_the_later_of_two_at_the_same_time_is_skipped(self, imported, kind, name):
        result, target, path = imported(
            f"{HEADER},comments\n0,{kind},C,first\n0,{kind},D,second\n"
        )

        assert result.problems == [
            RowProblem(
                path=path,
                line=3,
                column="time",
                message=f"There is already a {name} component at the selected position.",
                skipped=True,
            )
        ]
        assert [c.attrs["comments"] for c in target.components.values()] == ["first"]

    def test_a_row_skipped_isnt_compared_with_those_after_it(self, imported):
        result, target, _ = imported(rows("0,harmony,Q", "0,harmony,D"))

        assert messages(result) == ["Q is not a valid symbol."]
        assert [a["step"] for a in chords(target)] == [1]

    @pytest.mark.parametrize(
        "row, message",
        [
            ("0,harmony,C###", "3 is not a valid accidental."),
            ("0,key,C###", "3 is not a valid accidental."),
            # music21 reads it, but gives no chord type.
            ("0,harmony,C5", "an empty value is not a valid quality."),
        ],
    )
    def test_a_value_of_the_symbol_the_rules_refuse_is_reported_on_the_symbol(
        self, imported, row, message
    ):
        result, target, path = imported(rows(row, "1,harmony,D"))

        assert result.problems == [
            RowProblem(
                path=path, line=2, column="symbol", message=message, skipped=True
            )
        ]
        assert [a["step"] for a in chords(target)] == [1]

    def test_the_keys_and_then_the_whole_timeline_are_checked_once_each(
        self, imported, monkeypatch
    ):
        calls = []
        check_timeline = rules.check_timeline

        def counted(media_length, components, **kwargs):
            calls.append((media_length, list(components), kwargs))
            return check_timeline(media_length, components, **kwargs)

        monkeypatch.setattr(rules, "check_timeline", counted)
        for name in ("harmony", "mode"):
            monkeypatch.setattr(
                rules, name, lambda *_: pytest.fail("checked row by row")
            )

        result, target, _ = imported(
            rows(
                "3,harmony,C",
                "0,key,C",
                "0,key,G",
                "abc,harmony,C",
                "1,harmony,D",
                "2,key,F",
            ),
            media_length=10.0,
        )

        (keys_call, whole_call) = calls
        assert keys_call[0] == whole_call[0] == 10.0
        assert keys_call[2] == whole_call[2] == {"skip_broken": True}
        assert [(c.kind, c.attrs["time"]) for c in keys_call[1]] == [
            ("mode", 0.0),
            ("mode", 0.0),
            ("mode", 2.0),
        ]
        # In the CSV's order, without the key the first check refused.
        assert [(c.kind, c.attrs["time"]) for c in whole_call[1]] == [
            ("harmony", 3.0),
            ("mode", 0.0),
            ("harmony", 1.0),
            ("mode", 2.0),
        ]
        assert result.rows == 6
        assert len(target.components) == 4

    def test_a_rule_that_cant_be_checked_fails_the_import(self, imported, monkeypatch):
        # Its keys or chords would go in unchecked. `rules` finds music21 on its own.
        monkeypatch.setattr(rules, "_music21", lambda: (None, None))

        with pytest.raises(ImportFailed) as failed:
            imported(rows("0,key,C"))

        assert failed.value.message == (
            'checking a mode needs: pip install "tilia-core[harmony]"'
        )

    def test_a_chord_that_cant_be_checked_fails_it_too(self, imported, monkeypatch):
        monkeypatch.setattr(rules, "_music21", lambda: (None, None))

        with pytest.raises(ImportFailed) as failed:
            imported(rows("0,harmony,C"))

        assert failed.value.message == (
            'checking a harmony needs: pip install "tilia-core[harmony]"'
        )


class TestSlashChords:
    """A slash chord is never refused for its bass: its inversion is the bass's
    position in a stack of thirds, as music21 gives it. TiLiA draws a bass outside the
    chord in root position, and a note says so
    (TimeLineAnnotator/project-management#501)."""

    @pytest.mark.parametrize(
        "symbol, quality, inversion",
        [
            ("Dsus/G", "suspended-fourth", 5),
            ("Csus/F", "suspended-fourth", 5),
            ("Csus2/D", "suspended-second", 4),
            ("C7sus/F", "suspended-fourth-seventh", 5),
            ("C6/A", "major-sixth", 6),
            ("Cm6/A", "minor-sixth", 6),
            ("Abm6/F", "minor-sixth", 6),
            ("C/E", "major", 1),
            ("C7/Bb", "dominant-seventh", 3),
            ("C13/A", "dominant-13th", 6),
            # A power chord's fifth, though TiLiA's dialog offers it no inversion.
            ("Cpower/G", "power", 2),
            # The added tone is left out: the bass is in the chord without it.
            ("C7(b9)/Bb", "dominant-seventh-flat-ninth", 3),
            # A numeral's bass.
            ("V42", "dominant-seventh", 3),
            ("I64", "major", 2),
        ],
    )
    def test_a_bass_in_the_chord_has_no_note(
        self, imported, symbol, quality, inversion
    ):
        result, target, _ = imported(rows(f"0,harmony,{symbol}"))

        assert result.problems == []
        assert chords(target)[0]["quality"] == quality
        assert chords(target)[0]["inversion"] == inversion

    @pytest.mark.parametrize(
        "symbol, quality, inversion",
        [
            ("G/A", "major", 4),
            ("C7/D", "dominant-seventh", 4),
            ("Am/G", "minor", 3),
            ("D/C", "major", 3),
            ("C/Bb", "major", 3),
            ("Co7/A", "diminished-seventh", 6),
            ("C+/Ab", "augmented", 6),
            ("Cm/D#", "minor", 4),
            ("Cmaj7/D", "major-seventh", 4),
            ("Cpower/E", "power", 1),
            ("Cpedal/G", "pedal", 2),
        ],
    )
    def test_a_bass_outside_the_chord_is_kept_with_a_note(
        self, imported, symbol, quality, inversion
    ):
        result, target, path = imported(rows(f"0,harmony,{symbol}"))

        assert result.problems == [
            RowProblem(
                path=path,
                line=2,
                column="symbol",
                message=(
                    f"{symbol}: the bass isn't in the chord, so it is drawn in root"
                    " position."
                ),
                skipped=False,
            )
        ]
        # What makes it a note, status 0: nothing was skipped.
        assert result.skipped == []
        assert chords(target)[0]["quality"] == quality
        assert chords(target)[0]["inversion"] == inversion

    def test_a_bass_is_outside_just_where_tilia_falls_back(self, music21):
        # TiLiA's `letter_symbol` builds the chord in its inversion, from the
        # abbreviation of its base quality, and falls back to root position when
        # music21 can't. The importer doesn't build one per row, so this holds its
        # test to music21's, in the music21 installed.
        tested = [*music21.harmony.CHORD_TYPES, *rules.ADDED_TONE_QUALITIES]
        for quality in tested:
            base, _ = rules.split_added_tone(quality)
            note = "C" + music21.harmony.CHORD_TYPES[base][1][0]
            for inversion in range(7):
                try:
                    music21.harmony.ChordSymbol(note, inversion=inversion)
                    drawn = True
                except music21.chord.ChordException:
                    drawn = False
                in_the_chord = harmony._bass_is_in_the_chord(quality, inversion)
                assert in_the_chord is drawn, (quality, inversion)

    def test_a_note_keeps_its_rows_place(self, imported):
        result, target, _ = imported(
            rows("0,harmony,D/C", "1,harmony,Q", "2,harmony,C/Bb")
        )

        assert [(p.line, p.skipped) for p in result.problems] == [
            (2, False),
            (3, True),
            (4, False),
        ]
        assert len(chords(target)) == 2

    def test_a_row_the_rules_refuse_has_no_note(self, imported):
        result, target, path = imported(rows("60.5,harmony,D/C"))

        assert result.problems == [
            RowProblem(
                path=path,
                line=2,
                column="time",
                message="Time '01:00.5' is bigger than media time '01:00.0'",
                skipped=True,
            )
        ]
        assert target.components == {}

    def test_the_note_can_be_printed(self, imported, monkeypatch):
        # No CSV gives a lone surrogate, as it is read as UTF-8, but the note quotes
        # its symbol as the other texts that quote a user's do.
        symbol = "D/\udc80"
        row = CsvRow(
            line=2, values={"time": "0", "harmony_or_key": "harmony", "symbol": symbol}
        )
        params = {
            "step": 1,
            "accidental": 0,
            "inversion": 3,
            "quality": "major",
            "applied_to": 0,
        }
        monkeypatch.setattr(harmony, "read_csv", lambda _: (HEADER.split(","), [row]))
        monkeypatch.setattr(
            harmony, "get_harmony_params_from_text", lambda *_: (True, params)
        )

        result, _, _ = imported(rows("0,harmony,D/C"))

        assert messages(result) == [
            "D/\\udc80: the bass isn't in the chord, so it is drawn in root position."
        ]


class TestWhatItReports:
    def test_a_rows_line_counts_a_quoted_fields_line_breaks(self, imported):
        result, _, _ = imported(
            f'{HEADER},comments\n0,harmony,C,"two\nlines"\n1,harmony,Q,\n'
        )

        assert [problem.line for problem in result.problems] == [4]

    def test_problems_are_in_row_order(self, imported):
        # A key's problems are found before the chords', whatever the rows.
        result, _, _ = imported(
            rows(
                "0,harmony,Q", "abc,harmony,C", "61,key,C", "1,key,F:min", "1,harmony,Q"
            )
        )

        assert [problem.line for problem in result.problems] == [2, 3, 4, 5, 6]

    def test_created_is_the_new_ids_in_the_order_of_the_rows(self, imported):
        result, target, _ = imported(
            rows("5,harmony,C", "0,key,C", "abc,harmony,C", "1,harmony,D", "2,key,F")
        )

        assert result.created == list(target.components)
        assert [
            (target.components[i].kind, target.components[i].attrs["time"])
            for i in result.created
        ] == [("harmony", 5.0), ("mode", 0.0), ("harmony", 1.0), ("mode", 2.0)]
        assert result.rows == 5
        assert len(result.skipped) == 1

    def test_each_component_has_a_new_id(self, imported):
        # FR-041.
        result, target, _ = imported(rows("0,harmony,C", "0,key,C"))

        assert len(set(result.created)) == 2
        for component_id in result.created:
            assert target.components[component_id].id == component_id
            assert uuid.UUID(component_id).version == 7

    def test_empty_rows_are_left_out(self, imported):
        result, _, _ = imported(rows("0,harmony,C", "", "1,harmony,C"))

        assert result.rows == 2
        assert result.problems == []


class TestWhatItChanges:
    def test_it_replaces_the_components_the_timeline_had(self, imported):
        old = [
            component("harmony", time=1.0, step=1),
            component("mode", time=2.0, step=1),
        ]

        _, target, _ = imported(rows("5,harmony,C"), components=old)

        assert [a["time"] for a in chords(target)] == [5.0]
        assert keys(target) == []

    def test_a_component_of_a_kind_the_core_doesnt_know_stays(self, music21, tmp_path):
        # FR-032, and WP3's FR-015.
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("5,harmony,C"), encoding="utf-8")
        unknown = tla.Component(
            id=tla.new_id(), kind=tla.UnknownKind("LYRIC"), extra={"time": 1.0}
        )
        target = timeline("harmony", components=[unknown])
        doc = document(timelines=[target])

        result = harmony.import_by_time(doc, target.id, path)

        assert set(target.components) == {unknown.id, *result.created}
        assert target.components[unknown.id] == unknown

    def test_importing_twice_gives_the_same_components_with_new_ids(
        self, music21, tmp_path
    ):
        # FR-032; the second time, the first's keys and chords don't count.
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,key,G", "1,harmony,V", "0.5,key,D"), encoding="utf-8")
        target = timeline("harmony")
        doc = document(timelines=[target])

        first = harmony.import_by_time(doc, target.id, path)
        before = [c.attrs for c in target.components.values()]
        second = harmony.import_by_time(doc, target.id, path)

        assert second.problems == []
        assert [c.attrs for c in target.components.values()] == before
        assert list(target.components) == second.created
        assert not set(first.created) & set(second.created)

    @pytest.mark.parametrize(
        "content",
        [
            b"time,symbol\n0,C\n",
            b"",
            "time,harmony_or_key,symbol\n0,harmony,\xe9\n".encode("cp1252"),
        ],
        ids=["no required column", "empty", "not UTF-8"],
    )
    def test_an_import_that_fails_changes_nothing(self, music21, tmp_path, content):
        # FR-024.
        path = tmp_path / "harmonies.csv"
        path.write_bytes(content)
        target = timeline("harmony", components=[component("harmony", time=1.0)])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed):
            harmony.import_by_time(doc, target.id, path)

        assert doc == before

    def test_a_file_that_cant_be_opened_changes_nothing(self, music21, tmp_path):
        target = timeline("harmony", components=[component("harmony", time=1.0)])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(OSError):
            harmony.import_by_time(doc, target.id, tmp_path / "none.csv")

        assert doc == before

    def test_a_document_with_no_media_length_fails(self, music21, tmp_path):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,harmony,C"), encoding="utf-8")
        target = timeline("harmony")
        doc = document(timelines=[target], media_length=None)

        with pytest.raises(ImportFailed) as failed:
            harmony.import_by_time(doc, target.id, path)

        assert failed.value.message.startswith("No media loaded and no duration set.")
        assert target.components == {}

    def test_the_path_can_be_text(self, music21, tmp_path):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,harmony,C"), encoding="utf-8")
        target = timeline("harmony")
        doc = document(timelines=[target])

        result = harmony.import_by_time(doc, target.id, str(path))

        assert len(result.created) == 1

    def test_a_quarters_document_reads_times_as_they_are(self, imported):
        # US3 scenario 7, FR-033.
        result, target, _ = imported(
            rows("0.5,harmony,C", "2,key,C"), time_unit="quarters"
        )

        assert result.problems == []
        assert [c.attrs["time"] for c in target.components.values()] == [0.5, 2.0]

    def test_import_csv_gets_here_by_time(self, music21, tmp_path):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,key,G", "1,harmony,V"), encoding="utf-8")
        target = timeline("harmony")
        doc = document(timelines=[target])

        result = importers.import_csv(doc, target.id, path, by="time")

        assert result.problems == []
        assert [a["step"] for a in chords(target)] == [1]

    def test_what_it_imports_reads_back_as_it_is(self, music21, tmp_path):
        path = tmp_path / "harmonies.csv"
        path.write_text(
            f"{HEADER},{OPTIONAL_HEADER}\n"
            f"0,key,G,home,,,\n"
            f"1,harmony,V7/V,{OPTIONAL_ROW}\n"
            f"2,harmony,C7b9,,,,\n",
            encoding="utf-8",
        )
        target = timeline(
            "harmony",
            attrs={"level_count": 1, "level_height": 35, "visible_level_count": 2},
        )
        doc = document(timelines=[target])

        result = harmony.import_by_time(doc, target.id, path)

        assert result.problems == []
        written = tla.canonical_bytes(doc)
        read = tla.loads(written)
        assert read.timelines[target.id].components == target.components
        assert tla.canonical_bytes(read) == written
        stored = json.loads(written)["timelines"][target.id]["components"]
        assert stored[result.created[1]]["kind"] == "HARMONY"
        assert stored[result.created[0]]["kind"] == "MODE"


class TestWithoutTheExtra:
    def test_the_importer_names_the_command(self, tmp_path, without_the_extra):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,harmony,C"), encoding="utf-8")
        target = timeline("harmony", components=[component("harmony", time=1.0)])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed) as failed:
            harmony.import_by_time(doc, target.id, path)

        assert failed.value.message == HARMONY_EXTRA
        assert failed.value.path == path
        assert doc == before

    def test_import_csv_says_the_same(self, tmp_path, without_the_extra):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,harmony,C"), encoding="utf-8")
        target = timeline("harmony")
        doc = document(timelines=[target])

        with pytest.raises(ImportFailed) as failed:
            importers.import_csv(doc, target.id, path, by="time")

        assert failed.value.message == HARMONY_EXTRA

    def test_the_chords_reading_names_the_command(self, without_the_extra):
        with pytest.raises(ImportFailed) as failed:
            harmony.get_harmony_params_from_text("C", "C")

        assert failed.value.message == HARMONY_EXTRA
        assert failed.value.path is None
        assert str(failed.value) == HARMONY_EXTRA

    def test_the_keys_reading_names_the_command(self, without_the_extra):
        with pytest.raises(ImportFailed) as failed:
            harmony.get_mode_params_from_text("C")

        assert failed.value.message == HARMONY_EXTRA
        assert failed.value.path is None


class TestAMusic21ThatWontImport:
    REASON = (
        "checking a harmony needs music21, which can't be imported (AttributeError:"
        ' np.float_ was removed in \\udc80 NumPy 2.0.): pip install "tilia-core[harmony]"'
    )

    def test_the_importer_says_so(self, tmp_path, music21_that_wont_import):
        path = tmp_path / "harmonies.csv"
        path.write_text(rows("0,harmony,C"), encoding="utf-8")
        target = timeline("harmony", components=[component("harmony", time=1.0)])
        doc = document(timelines=[target])
        before = copy.deepcopy(doc)

        with pytest.raises(ImportFailed) as failed:
            harmony.import_by_time(doc, target.id, path)

        assert failed.value.message == self.REASON
        assert failed.value.path == path
        str(failed.value).encode("utf-8")
        assert doc == before

    def test_the_reading_says_so(self, music21_that_wont_import):
        for read in (
            lambda: harmony.get_harmony_params_from_text("C", "C"),
            lambda: harmony.get_mode_params_from_text("C"),
        ):
            with pytest.raises(ImportFailed) as failed:
                read()

            assert failed.value.message == self.REASON
            assert failed.value.path is None


@pytest.fixture
def read(music21):
    """The chord a text reads as, or None, as the dialog's `populate_from_text`
    is told. `key` is given to music21 as a `Key`, or None, as the dialog gives it."""

    def run(text, key=None):
        key = music21.key.Key(key) if key else None
        success, params = harmony.get_harmony_params_from_text(text, key)
        assert success is (params is not None)
        return params

    return run


class TestChordSymbolParsing:
    NOTE_NAME_TO_INT = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
    ACCIDENTAL_TO_INT = {0: "", 1: "#", -1: "b", 2: "##", -2: "bb"}
    ADDED_TONE_SYMBOLS = {
        "dominant-seventh-flat-ninth": "C7b9",
        "dominant-seventh-sharp-ninth": "C7#9",
        "dominant-seventh-sharp-eleventh": "C7#11",
        "dominant-seventh-flat-thirteenth": "C7b13",
        "dominant-seventh-added-thirteenth": "C7add13",
        "dominant-ninth-sharp-eleventh": "C9#11",
        "major-seventh-sharp-eleventh": "Cmaj7#11",
        "major-seventh-added-sixth": "Cmaj7add6",
        "major-sixth-added-ninth": "C6add9",
        "minor-sixth-added-ninth": "Cm6add9",
        "major-added-ninth": "Cadd9",
        "minor-added-ninth": "Cmadd9",
        "minor-seventh-added-eleventh": "Cm7add11",
        "cadential-six-four": "C(64)",
    }
    SPECIAL_ABBREVIATIONS_TO_QUALITY = {
        "dimb9": "diminished-minor-ninth",
        "9#5": "augmented-dominant-ninth",
        "m7b5": "half-diminished-seventh",
        "m#7": "minor-major-seventh",
    }

    def test_what_it_gives(self, read):
        assert read("Bb7/D") == {
            "step": 6,
            "accidental": -1,
            "inversion": 1,
            "quality": "dominant-seventh",
            "applied_to": 0,
        }

    @pytest.mark.parametrize("text,step", NOTE_NAME_TO_INT.items())
    def test_only_note_name(self, read, text, step):
        params = read(text)
        assert params["accidental"] == 0
        assert params["step"] == step
        assert params["quality"] == "major"

    @pytest.mark.parametrize("accidental_n, accidental", ACCIDENTAL_TO_INT.items())
    @pytest.mark.parametrize("note,step", NOTE_NAME_TO_INT.items())
    def test_accidental_and_note_name(self, read, accidental_n, accidental, note, step):
        params = read(note + accidental)
        assert params["accidental"] == accidental_n
        assert params["step"] == step

    def test_minus_sign_is_parsed_as_quality(self, read):
        params = read("D-")
        assert params["accidental"] == 0
        assert params["step"] == 1
        assert params["quality"] == "minor"

    def test_minus_sign_after_accidental_is_parsed_as_minor_quality(self, read):
        params = read("Cb-")
        assert params["accidental"] == -1
        assert params["step"] == 0
        assert params["quality"] == "minor"

    def test_minus_sign_after_double_accidental_is_parsed_as_minor_quality(self, read):
        params = read("C##-")
        assert params["accidental"] == 2
        assert params["step"] == 0
        assert params["quality"] == "minor"

    def test_b_before_quality(self, read):
        params = read("Dbm7")
        assert params["accidental"] == -1
        assert params["step"] == 1
        assert params["quality"] == "minor-seventh"

    def test_regular_abbreviations(self, read, music21):
        for quality, entry in music21.harmony.CHORD_TYPES.items():
            for abbreviation in entry[1]:
                if abbreviation in self.SPECIAL_ABBREVIATIONS_TO_QUALITY:
                    continue
                params = read("D" + abbreviation)
                assert params["step"] == 1, abbreviation
                assert params["quality"] == quality, abbreviation

    @pytest.mark.parametrize("abbrev,quality", SPECIAL_ABBREVIATIONS_TO_QUALITY.items())
    def test_special_abbreviations(self, read, abbrev, quality):
        params = read("D" + abbrev)
        assert params["step"] == 1
        assert params["quality"] == quality

    @pytest.mark.parametrize(
        "applied_to,suffix",
        [
            (0, ""),
            (1, "/II"),
            (2, "/III"),
            (3, "/IV"),
            (4, "/V"),
            (5, "/VI"),
            (6, "/VII"),
        ],
    )
    def test_applied_chords(self, read, applied_to, suffix):
        assert read("I" + suffix)["applied_to"] == applied_to

    def test_slash_chords_where_bass_is_not_in_chord_symbol(self, read):
        params = read("G/A")
        assert params["step"] == 4
        # The dialog has no such inversion to select, and stays at the root position.
        # The importer keeps the chord, with a note.
        assert params["inversion"] == 4

    @pytest.mark.parametrize(
        "extension",
        ["7#9", "7#11", "m713", "7b9", "11", "7(b13)", "7(b9,#11)", "(b9,#13)"],
    )
    def test_parse_with_extensions_does_not_crash(self, music21, extension):
        # This only tests that it doesn't crash. Some of these are read as a
        # quality with an added tone, the others without their extensions, and the
        # dialog keeps what the text before them read as.
        success, params = harmony.get_harmony_params_from_text("C" + extension, None)
        assert not success or params["step"] == 0

    @pytest.mark.parametrize(
        "text, step, accidental, inversion",
        [
            ("C7b9", 0, 0, 0),
            ("C7(b9)", 0, 0, 0),
            ("Bb7b9", 6, -1, 0),
            ("C7b9/E", 0, 0, 1),
            ("C7(b9)/G", 0, 0, 2),
            ("C7b9/Bb", 0, 0, 3),
        ],
    )
    def test_dominant_seventh_flat_ninth(self, read, text, step, accidental, inversion):
        params = read(text)
        assert params["quality"] == "dominant-seventh-flat-ninth"
        assert params["step"] == step
        assert params["accidental"] == accidental
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text, quality, inversion",
        [
            ("C7#9", "dominant-seventh-sharp-ninth", 0),
            ("C7(#9)/E", "dominant-seventh-sharp-ninth", 1),
            ("C7#11", "dominant-seventh-sharp-eleventh", 0),
            ("C7b13/G", "dominant-seventh-flat-thirteenth", 2),
            ("C7add13", "dominant-seventh-added-thirteenth", 0),
            ("C7(13)/Bb", "dominant-seventh-added-thirteenth", 3),
            ("C9#11/D", "dominant-ninth-sharp-eleventh", 4),
            ("Cmaj7#11", "major-seventh-sharp-eleventh", 0),
            ("CM7(#11)", "major-seventh-sharp-eleventh", 0),
            ("Cmaj7add6/B", "major-seventh-added-sixth", 3),
            ("C6add9", "major-sixth-added-ninth", 0),
            ("C6/9/E", "major-sixth-added-ninth", 1),
            ("C6(9)", "major-sixth-added-ninth", 0),
            ("Cm6/9/G", "minor-sixth-added-ninth", 2),
            ("Cadd9", "major-added-ninth", 0),
            ("C(add9)/E", "major-added-ninth", 1),
            ("C(9)", "major-added-ninth", 0),
            ("Cmadd9/G", "minor-added-ninth", 2),
            ("Cm(add9)", "minor-added-ninth", 0),
            ("Cm7add11/Eb", "minor-seventh-added-eleventh", 1),
            ("Cm7(11)", "minor-seventh-added-eleventh", 0),
        ],
    )
    def test_added_tone_qualities(self, read, text, quality, inversion):
        params = read(text)
        assert params["quality"] == quality
        assert params["step"] == 0
        assert params["accidental"] == 0
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text, step, accidental, quality",
        [
            ("C#7#9", 0, 1, "dominant-seventh-sharp-ninth"),
            ("Bb6/9", 6, -1, "major-sixth-added-ninth"),
            ("F#m7add11", 3, 1, "minor-seventh-added-eleventh"),
        ],
    )
    def test_added_tone_quality_on_altered_root(
        self, read, text, step, accidental, quality
    ):
        params = read(text)
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["accidental"] == accidental

    @pytest.mark.parametrize(
        "text",
        [
            "C7b9/Db",
            "C7#9/D#",
            "C7#11/F#",
            "C7b13/Ab",
            "C7add13/A",
            "C9#11/F#",
            "Cmaj7#11/F#",
            "Cmaj7add6/A",
            "C6add9/D",
            "Cm6add9/D",
            "Cadd9/D",
            "Cmadd9/D",
            "Cm7add11/F",
        ],
    )
    def test_added_tone_in_the_bass_is_refused(self, read, text):
        # No inversion of the base quality puts the added tone in the bass.
        assert read(text) is None

    @pytest.mark.parametrize("text", ["Cm7(b9)", "CM7(b9)", "C(#9)"])
    def test_tone_in_parentheses_that_makes_no_quality_is_refused(self, read, text):
        # As before, since music21 reads no parentheses. Without them,
        # "C(#9)" would read as a C sharp ninth chord.
        assert read(text) is None

    @pytest.mark.parametrize(
        "text, quality",
        [
            ("Cm7b9", "minor-seventh"),
            ("CM7b9", "major-seventh"),
            ("Cdim7b9", "diminished-seventh"),
            ("C+7b9", "augmented-seventh"),
        ],
    )
    def test_flat_ninth_on_other_sevenths_is_dropped_as_before(
        self, read, text, quality
    ):
        # TiLiA has no quality for these, so the flat ninth is dropped, as before.
        assert read(text)["quality"] == quality

    @pytest.mark.parametrize("quality, text", ADDED_TONE_SYMBOLS.items())
    def test_each_added_tone_quality_has_a_symbol(self, read, quality, text):
        # The text the dialog of TiLiA's
        # `test_added_tone_quality_is_offered_after_its_base` shows, read back.
        assert read(text)["quality"] == quality

    def test_every_added_tone_quality_is_among_them(self):
        assert sorted(self.ADDED_TONE_SYMBOLS) == sorted(rules.ADDED_TONE_QUALITIES)

    def test_applied_to_is_cleared_when_no_longer_applied(self, read):
        assert read("V7/V")["applied_to"] == 4
        assert read("V7")["applied_to"] == 0


class TestRomanNumeralParsing:
    @pytest.mark.parametrize(
        "text, quality, step, inversion",
        [
            ("V", "major", 4, 0),
            ("V7", "dominant-seventh", 4, 0),
            ("V65", "dominant-seventh", 4, 1),
            ("V43", "dominant-seventh", 4, 2),
            ("V42", "dominant-seventh", 4, 3),
            ("ii7", "minor-seventh", 1, 0),
            ("viio7", "diminished-seventh", 6, 0),
        ],
    )
    def test_quality_step_and_inversion(self, read, text, quality, step, inversion):
        params = read(text)
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["inversion"] == inversion

    def test_seventh_quality_is_not_collapsed_to_triad(self, read):
        # Direct guard for the reported bug: typing "V7" selected "Major".
        assert read("V7")["quality"] == "dominant-seventh"

    def test_applied_seventh(self, read):
        params = read("V7/V")
        assert params["quality"] == "dominant-seventh"
        assert params["applied_to"] == 4
        assert params["step"] == 1

    @pytest.mark.parametrize(
        "key, text, step, inversion, applied_to",
        [
            ("C", "V7b9", 4, 0, 0),
            ("C", "V7(b9)", 4, 0, 0),
            ("C", "Vb9", 4, 0, 0),
            ("C", "V65b9", 4, 1, 0),
            ("C", "V42(b9)", 4, 3, 0),
            ("C", "V7b9/IV", 0, 0, 3),
            ("C", "V7(b9)/II", 5, 0, 1),
            ("a", "V7b9", 2, 0, 0),
            ("a", "Vb9", 2, 0, 0),  # the flat ninth of E7 is F
        ],
    )
    def test_dominant_seventh_flat_ninth(
        self, read, key, text, step, inversion, applied_to
    ):
        params = read(text, key)
        assert params["quality"] == "dominant-seventh-flat-ninth"
        assert params["step"] == step
        assert params["accidental"] == 0
        assert params["inversion"] == inversion
        assert params["applied_to"] == applied_to

    @pytest.mark.parametrize(
        "text, step, inversion, quality",
        [
            ("V7#9", 4, 0, "dominant-seventh-sharp-ninth"),
            ("V#9", 4, 0, "dominant-seventh-sharp-ninth"),
            ("V65#9", 4, 1, "dominant-seventh-sharp-ninth"),
            ("V7#11", 4, 0, "dominant-seventh-sharp-eleventh"),
            ("V7b13", 4, 0, "dominant-seventh-flat-thirteenth"),
            ("V7add13", 4, 0, "dominant-seventh-added-thirteenth"),
            ("V7(13)", 4, 0, "dominant-seventh-added-thirteenth"),
            ("I7#11", 0, 0, "major-seventh-sharp-eleventh"),
            ("I7(#11)", 0, 0, "major-seventh-sharp-eleventh"),
            ("I7add6", 0, 0, "major-seventh-added-sixth"),
            ("Iadd9", 0, 0, "major-added-ninth"),
            ("I(9)", 0, 0, "major-added-ninth"),
            ("I6(add9)", 0, 1, "major-added-ninth"),
            ("iadd9", 0, 0, "minor-added-ninth"),
            ("ii7add11", 1, 0, "minor-seventh-added-eleventh"),
            ("ii65(11)", 1, 1, "minor-seventh-added-eleventh"),
        ],
    )
    def test_added_tone_qualities(self, read, text, step, inversion, quality):
        params = read(text, "C")
        assert params["quality"] == quality
        assert params["step"] == step
        assert params["inversion"] == inversion

    @pytest.mark.parametrize(
        "text", ["ii7b9", "I7b9", "viio7b9", "ii7#11", "I7(9)", "Vadd6"]
    )
    def test_tone_that_makes_no_quality_is_refused(self, read, text):
        # TiLiA has no quality for these. A minor seventh with a flat ninth,
        # say, is not read as a minor seventh.
        assert read(text) is None

    @pytest.mark.parametrize("text", ["V/bVI", "V42/bVII"])
    def test_a_symbol_that_raises_is_refused(self, read, text):
        # An applied chord to a chromatic degree, on which TiLiA's raises.
        assert read(text) is None

    def test_the_key_can_be_text(self, music21):
        success, params = harmony.get_harmony_params_from_text("V", "G")

        assert success
        assert params["step"] == 1


class TestCadentialSixFourParsing:
    @pytest.mark.parametrize(
        "key, text, step, accidental, applied_to",
        [
            # Roman numerals
            ("C", "V(64)", 4, 0, 0),
            ("C", "Vadd64", 4, 0, 0),
            ("C", "Cad64", 4, 0, 0),
            ("C", "cad64", 4, 0, 0),
            ("C", "V(64)/V", 1, 0, 4),
            ("C", "Cad64/V", 1, 0, 4),
            ("a", "V(64)", 2, 0, 0),
            ("a", "Cad64", 2, 0, 0),
            # Chord symbols
            (None, "G(64)", 4, 0, 0),
            (None, "Gadd64", 4, 0, 0),
            (None, "Bb(64)", 6, -1, 0),
            (None, "F#(64)", 3, 1, 0),
        ],
    )
    def test_is_read(self, read, key, text, step, accidental, applied_to):
        params = read(text, key)
        assert params["quality"] == "cadential-six-four"
        assert params["step"] == step
        assert params["accidental"] == accidental
        assert params["inversion"] == 0
        assert params["applied_to"] == applied_to

    def test_six_four_without_parentheses_is_the_second_inversion(self, read):
        params = read("V64", "C")
        assert params["quality"] == "major"
        assert params["inversion"] == 2

    @pytest.mark.parametrize(
        "key, text",
        [
            # Its root is in the bass by definition.
            ("C", "V6(64)"),
            ("C", "G(64)/B"),
            ("C", "G(64)/D"),
            # Only a major triad has one.
            ("C", "V7(64)"),
            ("a", "v(64)"),
            ("C", "Gm(64)"),
        ],
    )
    def test_is_refused(self, read, key, text):
        assert read(text, key) is None


class TestModeParamsFromText:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("C", {"step": 0, "accidental": 0, "type": "major"}),
            ("f#", {"step": 3, "accidental": 1, "type": "minor"}),
        ],
    )
    def test_valid_symbol(self, music21, text, expected):
        assert harmony.get_mode_params_from_text(text) == (True, expected)

    @pytest.mark.parametrize("text", ["F:min", "X", "V", ""])
    def test_invalid_symbol_fails_without_raising(self, music21, text):
        assert harmony.get_mode_params_from_text(text) == (False, None)


class TestTheNames:
    @pytest.mark.parametrize(
        "name", ["get_harmony_params_from_text", "get_mode_params_from_text"]
    )
    def test_the_readings_are_documented(self, name):
        assert getattr(harmony, name).__doc__
