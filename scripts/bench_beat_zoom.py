"""
Bench: zoom in on an N-beat timeline.

Usage examples:
    python scripts/bench_beat_zoom.py --n 1000 --platform offscreen
    python scripts/bench_beat_zoom.py --n 14000 --platform offscreen --profile
    python scripts/bench_beat_zoom.py --n 14000 --platform windows --runs 5
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
    )
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profile-top", type=int, default=40)
    parser.add_argument("--runs", type=int, default=3)
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

    if not args.quiet:
        print(
            f"# platform={args.platform} N={args.n} runs={args.runs} "
            f"profile={args.profile}"
        )
        print(f"# fill_with_beats took {fill_elapsed*1000:.1f} ms")

    timings = []
    profiler = cProfile.Profile() if args.profile else None
    for i in range(args.runs):
        direction = "in" if i % 2 == 0 else "out"
        if profiler:
            profiler.enable()
        t0 = time.perf_counter()
        commands.execute(f"view.zoom.{direction}")
        q_app.processEvents()
        elapsed = time.perf_counter() - t0
        if profiler:
            profiler.disable()
        timings.append((direction, elapsed))

    print()
    for i, (direction, t) in enumerate(timings):
        print(f"run {i + 1} ({direction}): {t * 1000:8.2f} ms")
    raw = [t for _, t in timings]
    print(f"min   : {min(raw) * 1000:8.2f} ms")
    print(f"median: {sorted(raw)[len(raw) // 2] * 1000:8.2f} ms")
    print(f"max   : {max(raw) * 1000:8.2f} ms")

    if profiler:
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s).strip_dirs().sort_stats("cumulative")
        stats.print_stats(args.profile_top)
        print()
        print(s.getvalue())


if __name__ == "__main__":
    main()
