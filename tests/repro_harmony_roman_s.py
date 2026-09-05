"""Throwaway generator for the repro bundle of the rogue-"s" harmony fix.

Harmony is not covered by the CLI's `timelines add` / `components`, so the
fixture is built through `commands.execute(...)` and saved with `file.save`,
as `CLAUDE.md` prescribes for kinds the CLI cannot populate.

Run from the repo root:

    uv run --python 3.12 pytest tests/repro_harmony_roman_s.py -q

Writes `repro/harmony-roman-s.tla`. Delete both this file and the `.tla`
before merge — the durable artifact is
`TestRomanNumeralDisplay::test_roman_label_has_no_blank_accidental_placeholder`.
"""

from pathlib import Path

from tests.mock import Serve
from tests.ui.timelines.harmony.test_harmony_timeline_ui import add_harmony, add_mode
from tilia.requests import Get
from tilia.ui import commands

OUT = Path(__file__).resolve().parent.parent / "repro" / "harmony-roman-s.tla"

# (time, step, quality, inversion, applied_to) -> what the label should read.
# Every entry but the last two is a one- or two-figure figured bass, which is
# where the blank-accidental placeholder leaks out of the "%" stack.
HARMONIES = [
    (0, 0, "major", 0, 0),  # I       — control, no figures
    (10, 0, "major", 1, 0),  # I6
    (20, 0, "major", 2, 0),  # I64
    (30, 4, "dominant-seventh", 1, 0),  # V65
    (40, 4, "dominant-seventh", 2, 0),  # V43
    (50, 4, "dominant-seventh", 3, 0),  # V42
    (60, 1, "dominant-seventh", 1, 4),  # V65/V  — applied chord
    (70, 1, "minor-seventh", 1, 0),  # ii65
    (80, 4, "dominant-ninth", 3, 0),  # V%sss432 — control, stacked form
]


def test_generate_fixture(harmony_tlui, tilia_state):
    tilia_state.set_duration(100, "no")
    add_mode(0, step=0, accidental=0, type="major")  # C major

    for time, step, quality, inversion, applied_to in HARMONIES:
        add_harmony(
            time,
            step=step,
            quality=quality,
            inversion=inversion,
            applied_to=applied_to,
            display_mode="roman",
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with Serve(Get.FROM_USER_SAVE_PATH_TILIA, (True, OUT)):
        commands.execute("file.save")

    print("\nwrote", OUT)
    for element in sorted(harmony_tlui.harmonies(), key=lambda e: e.get_data("time")):
        print(f"  t={element.get_data('time'):>5} label={element.label!r}")
