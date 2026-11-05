"""Save the old-version test file `0.0.96.tla` with TiLiA 0.0.96 itself.

Run with the interpreter of an environment that has TiLiA 0.0.96's
requirements (see README.md), giving the folder of TiLiA 0.0.96's code:

    python save_with_tilia_0_0_96.py TILIA_0_0_96_FOLDER OUT.tla

The media comes from the environment variable GEN_MEDIA. TiLiA's settings,
autosaves and log go to a temporary folder, never to the user's own, and
autosave is off.
"""

import os
import sys
import tempfile
import tkinter
from pathlib import Path


def main(code: Path, out: str) -> None:
    media = os.environ.get("GEN_MEDIA", "")
    media = Path(media).resolve().as_posix() if media else ""
    sys.path.insert(0, str(code))
    from tilia import dirs, settings

    data = Path(tempfile.mkdtemp(prefix="tilia-data-"))
    dirs.settings_path = data / "settings.toml"
    dirs.autosaves_path = data / "autosaves"
    dirs.log_path = data / "log.txt"
    dirs.settings_path.write_text(settings.DEFAULT_SETTINGS, encoding="utf-8")
    settings.load(dirs.settings_path)
    get = settings.get

    def without_autosave(table, name, *_):
        if (table, name) == ("auto-save", "interval"):
            return 0
        if (table, name) == ("dev", "dev_mode"):
            return False
        return get(table, name)

    settings.get = without_autosave
    os.chdir(code / "tilia")  # where the interface finds its images
    root = tkinter.Tk()
    root.withdraw()

    from tilia._tilia import TiLiA
    from tilia.timelines.create import create_timeline
    from tilia.timelines.timeline_kinds import TimelineKind
    from tilia.ui.tkinterui import TkinterUI

    from tilia.timelines.component_kinds import ComponentKind

    app = TiLiA(TkinterUI(root))
    app._player.media_length = 9.952  # the length of TiLiA's example.ogg
    timelines, uis = app._timeline_collection, app._timeline_ui_collection

    app.on_metadata_field_edited("title", "Sonata Op. 2 No. 1, I")
    app.on_metadata_field_edited("composer", "Beethoven")
    app.on_metadata_field_edited("recording year", "1958")

    hierarchy = create_timeline(
        TimelineKind.HIERARCHY_TIMELINE, timelines, uis, "Formal analysis"
    )
    hierarchy.split(4.5)
    first, second = sorted(
        hierarchy.component_manager._components, key=lambda unit: unit.start
    )
    first.ui.label = "Exposição"
    first.formal_type = "sonata form"
    first.formal_function = "exposition"
    first.comments = "tag=p1 first theme gen=ai"
    second.ui.label = "Development"
    second.ui.color = "#68de7c"
    hierarchy.group([first, second])  # a unit above them: parent and children

    markers = create_timeline(TimelineKind.MARKER_TIMELINE, timelines, uis, "Cadences")
    half = markers.create_timeline_component(ComponentKind.MARKER, time=1.25)
    half.ui.label = "HC"
    full = markers.create_timeline_component(ComponentKind.MARKER, time=3.5)
    full.ui.label = "PAC"
    full.comments = "src_start=3.4"

    beats = create_timeline(
        TimelineKind.BEAT_TIMELINE, timelines, uis, "Measures", beat_pattern=[4]
    )
    for index in range(12):
        beats.create_timeline_component(ComponentKind.BEAT, time=index * 0.5)

    app._player.media_path = media
    app._file_manager._file.file_path = out
    app._file_manager.get_file_path = lambda save_as: out
    app._file_manager.save(save_as=False)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), str(Path(sys.argv[2]).resolve()))
