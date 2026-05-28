"""
Bench: middle-insert into an N-beat timeline.

Usage examples:
    python scripts/bench_beat_insert.py --n 1000 --platform offscreen
    python scripts/bench_beat_insert.py --n 5000 --platform windows
    python scripts/bench_beat_insert.py --n 1000 --profile
    python scripts/bench_beat_insert.py --n 1000 --platform minimal --runs 5

Notes:
- --platform must be applied before any Qt import; we set QT_QPA_PLATFORM at
  the top of main() before any tilia/PySide6 module is imported.
- --profile wraps each timed insert in cProfile and prints the top-N cumulative
  callers. Numbers are inflated by the profiler; use a non-profile run for
  wall-clock comparisons.
- --runs > 1 runs multiple inserts; each subsequent insert nudges the seek
  position by 0.001s so unique-time validation still passes.
"""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1000, help="number of beats to fill")
    parser.add_argument(
        "--platform",
        choices=["offscreen", "minimal", "windows"],
        default="offscreen",
        help="QT_QPA_PLATFORM to test under",
    )
    parser.add_argument("--profile", action="store_true", help="enable cProfile")
    parser.add_argument("--profile-top", type=int, default=30)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--position",
        choices=["middle", "end"],
        default="middle",
        help="insert point: middle (worst case) or end (live-tap workload)",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    os.environ["QT_QPA_PLATFORM"] = args.platform
    os.environ.setdefault("ENVIRONMENT", "test")

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    run_bench(args)


def run_bench(args):
    import cProfile
    import io
    import pstats
    import time

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from tilia.timelines.timeline_kinds import TimelineKind as TlKind

    from tilia.boot import setup_logic
    from tilia.timelines.beat.timeline import BeatTimeline
    from tilia.ui import commands
    from tilia.ui.qtui import QtUI, TiliaMainWindow

    q_app = QApplication(sys.argv)

    tilia = setup_logic(autosaver=False)
    tilia.set_file_media_duration(100)
    tilia.reset_undo_manager()

    mw = TiliaMainWindow()
    if args.platform == "windows":
        mw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    QtUI(q_app, mw)

    beat_tl: BeatTimeline = tilia.timelines.create_timeline(
        TlKind.BEAT_TIMELINE, [], beat_pattern=[4]
    )

    fill_start = time.perf_counter()
    beat_tl.fill_with_beats(BeatTimeline.FillMethod.BY_AMOUNT, args.n)
    q_app.processEvents()
    fill_elapsed = time.perf_counter() - fill_start

    spacing = 100.0 / args.n
    if args.position == "end":
        seek_time = (args.n - 1) * spacing + spacing / 2
    else:
        seek_time = (args.n // 2) * spacing + spacing / 2
    commands.execute("media.seek", seek_time)
    q_app.processEvents()

    if not args.quiet:
        print(
            f"# platform={args.platform} N={args.n} runs={args.runs} "
            f"profile={args.profile}"
        )
        print(f"# fill_with_beats took {fill_elapsed*1000:.1f} ms")
        print(f"# seeked to t={seek_time:.4f} (spacing={spacing:.4f})")

    timings = []
    profiler = cProfile.Profile() if args.profile else None
    prev_count = len(beat_tl.components)
    for i in range(args.runs):
        if profiler:
            profiler.enable()
        t0 = time.perf_counter()
        commands.execute("timeline.beat.add")
        q_app.processEvents()
        elapsed = time.perf_counter() - t0
        if profiler:
            profiler.disable()
        new_count = len(beat_tl.components)
        if new_count != prev_count + 1:
            raise RuntimeError(
                f"run {i + 1}: insert failed silently "
                f"(component count {prev_count} -> {new_count} at seek={seek_time:.6f})"
            )
        prev_count = new_count
        timings.append(elapsed)

        seek_time += spacing / 10
        commands.execute("media.seek", seek_time)
        q_app.processEvents()

    print()
    for i, t in enumerate(timings):
        print(f"run {i + 1}: {t * 1000:8.2f} ms")
    print(f"min   : {min(timings) * 1000:8.2f} ms")
    print(f"median: {sorted(timings)[len(timings) // 2] * 1000:8.2f} ms")
    print(f"max   : {max(timings) * 1000:8.2f} ms")

    if profiler:
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).strip_dirs().sort_stats("cumulative")
        stats.print_stats(args.profile_top)
        print()
        print(s.getvalue())


if __name__ == "__main__":
    main()
