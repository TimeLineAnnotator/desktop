"""Save the old-version test files with TiLiA 0.5.x to 0.7.x itself.

Run with the interpreter of an environment where that TiLiA version is
installed (see README.md); `neutral` runs with any Python:

    python save_with_tilia.py new OUT.tla        # every timeline kind
    python save_with_tilia.py resave IN.tla OUT.tla   # open, save again unedited
    python save_with_tilia.py neutral FOLDER TARGET   # neutral paths, into TARGET

`new` takes the media and the PDF from the environment variables GEN_MEDIA
and GEN_PDF. TiLiA's settings go to a temporary file, never to the user's
own; no autosaver or logger is started.
"""

import glob
import json
import os
import sys
import tempfile
from pathlib import Path

NEUTRAL_FOLDER = "C:/Users/user/Documents/TiLiA"
_KEPT = []  # Qt's application, which must outlive the run


def neutral(folder: str, target: str) -> None:
    """Copy the .tla files in `folder` to `target`, with `folder`'s path, in
    the two forms JSON writes it, replaced by a neutral user's folder."""
    backslash = chr(92)
    prefix = os.path.abspath(folder)
    forward = prefix.replace(backslash, "/")
    backward = json.dumps(prefix.replace("/", backslash))[1:-1]
    neutral_backward = json.dumps(NEUTRAL_FOLDER.replace("/", backslash))[1:-1]
    for path in glob.glob(os.path.join(folder, "*.tla")):
        text = Path(path).read_bytes().decode("utf-8")
        text = text.replace(forward, NEUTRAL_FOLDER).replace(backward, neutral_backward)
        json.loads(text)
        Path(target, os.path.basename(path)).write_bytes(text.encode("utf-8"))


def _boot():
    """Start TiLiA's logic without its windows, with settings in a temporary
    file. No module of TiLiA may be imported before: its settings would be
    the user's own, which TiLiA writes its defaults into when it starts."""
    if any(name == "tilia" or name.startswith("tilia.") for name in sys.modules):
        raise RuntimeError("TiLiA was imported before its settings were redirected")
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import PySide6.QtCore as QtCore
        from PySide6.QtWidgets import QApplication
    except ImportError:  # TiLiA before 0.6
        import PyQt6.QtCore as QtCore
        from PyQt6.QtWidgets import QApplication

    ini = Path(tempfile.mkdtemp(prefix="tilia-settings-")) / "settings.ini"
    original = QtCore.QSettings

    class TemporarySettings(original):
        def __init__(self, *args, **kwargs):
            super().__init__(str(ini), original.Format.IniFormat)

    QtCore.QSettings = TemporarySettings
    _KEPT.append(QApplication(sys.argv))

    import tilia.settings
    from tilia.boot import setup_logic
    from tilia.requests import Get, serve

    if not isinstance(tilia.settings.settings._settings, TemporarySettings):
        raise RuntimeError("TiLiA's settings aren't the temporary ones")
    app = setup_logic(autosaver=False)

    class Replier:
        pass

    replier = Replier()
    for name, reply in [
        ("FROM_USER_RETRY_MEDIA_PATH", False),
        ("FROM_USER_YES_OR_NO", True),
        ("FROM_USER_SHOULD_SAVE_CHANGES", (True, False)),
        ("FROM_USER_UNKNOWN_TIMELINE_KIND_ACTION", (True, False)),
    ]:
        if hasattr(Get, name):
            serve(replier, getattr(Get, name), lambda *_, reply=reply: reply)
    return app


def _kind(name: str):
    """The timeline kind as this version's create_timeline takes it."""
    try:
        from tilia.timelines.base.timeline import Timeline

        finder = Timeline.get_class_by_name  # TiLiA 0.6 and later
    except AttributeError:
        finder = None
    if finder is not None:
        try:
            return finder(name.lower())
        except ValueError:
            return None
    from tilia.timelines.timeline_kinds import TimelineKind

    return TimelineKind.__members__.get(name + "_TIMELINE")


def _path(variable: str) -> str:
    value = os.environ.get(variable, "")
    return Path(value).resolve().as_posix() if value else ""


def new(out: Path) -> None:
    app = _boot()
    from tilia.requests import Post, post
    from tilia.timelines.component_kinds import ComponentKind as CK

    app.setup_file()  # the slider timeline every new file starts with
    app.set_file_media_duration(9.952)  # the length of TiLiA's example.ogg
    timelines, file_manager = app.timelines, app.file_manager

    file_manager.on_set_media_metadata_field("title", "Sonata Op. 2 No. 1, I")
    for name in ("composer", "recording year"):
        if name not in file_manager.file.media_metadata:
            file_manager.on_add_media_metadata_field(name)
    file_manager.on_set_media_metadata_field("composer", "Beethoven")
    file_manager.on_set_media_metadata_field("recording year", "1958")

    hierarchy = timelines.create_timeline(_kind("HIERARCHY"), name="Formal analysis")
    first, _ = hierarchy.create_component(CK.HIERARCHY, start=0.0, end=4.5, level=1)
    hierarchy.set_component_data(first.id, "label", "Exposição")
    hierarchy.set_component_data(first.id, "formal_type", "sonata form")
    hierarchy.set_component_data(first.id, "formal_function", "exposition")
    hierarchy.set_component_data(first.id, "comments", "tag=p1 first theme gen=ai")
    second, _ = hierarchy.create_component(CK.HIERARCHY, start=4.5, end=9.952, level=1)
    hierarchy.set_component_data(second.id, "label", "Development")
    hierarchy.set_component_data(second.id, "pre_start", 4.25)
    hierarchy.set_component_data(second.id, "color", "#68de7c")
    below, _ = hierarchy.create_component(CK.HIERARCHY, start=0.0, end=2.0, level=2)
    hierarchy.set_component_data(below.id, "label", "P")

    markers = timelines.create_timeline(_kind("MARKER"), name="Cadences")
    half, _ = markers.create_component(CK.MARKER, time=1.25)
    markers.set_component_data(half.id, "label", "HC")
    full, _ = markers.create_component(CK.MARKER, time=3.5)
    markers.set_component_data(full.id, "label", "PAC")
    markers.set_component_data(full.id, "comments", "src_start=3.4")

    beats = timelines.create_timeline(_kind("BEAT"), beat_pattern=[4], name="Measures")
    for index in range(12):
        beats.create_component(CK.BEAT, time=index * 0.5)

    harmony = timelines.create_timeline(_kind("HARMONY"), name="Harmony")
    harmony.create_component(CK.MODE, time=0.0, step=5, accidental=0, type="minor")
    harmony.create_component(
        CK.HARMONY, time=0.0, step=5, accidental=0, quality="minor"
    )
    harmony.create_component(
        CK.HARMONY, time=2.0, step=4, accidental=0, quality="major", inversion=1
    )

    pdf = timelines.create_timeline(
        _kind("PDF"), path=_path("GEN_PDF"), name="Score pages"
    )
    pdf.create_component(CK.PDF_MARKER, time=0.0, page_number=1)
    pdf.create_component(CK.PDF_MARKER, time=3.0, page_number=2)

    wave = timelines.create_timeline(_kind("AUDIOWAVE"), name="")
    for index, amplitude in enumerate([0.25, 0.5, 1.0]):
        wave.create_component(
            CK.AUDIOWAVE, start=float(index), end=index + 1.0, amplitude=amplitude
        )

    from tilia.timelines.score.components.clef import Clef

    score = timelines.create_timeline(_kind("SCORE"), name="Score")
    # Positional where this version's validation reads the time from them.
    score.create_component(CK.STAFF, 0, 5)
    score.create_component(CK.CLEF, 0, 0.0, shorthand=Clef.Shorthand.TREBLE)
    score.create_component(CK.KEY_SIGNATURE, staff_index=0, time=0.0, fifths=-4)
    score.create_component(
        CK.TIME_SIGNATURE, staff_index=0, time=0.0, numerator=2, denominator=2
    )
    score.create_component(CK.NOTE, 0.0, 0.5, 5, 0, 4, 0)
    score.create_component(CK.BAR_LINE, time=1.0)
    score.create_component(CK.SCORE_ANNOTATION, 10.5, 20.0, 0, "Allegro", 12)
    score.set_data("svg_data", '<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    score.set_data("viewer_beat_x", {0.0: 12.5, 0.5: 48.0})

    if _kind("RANGE") is not None:  # TiLiA 0.7 and later
        ranges = timelines.create_timeline(_kind("RANGE"), name="Voices")
        ranges.add_row(name="Soprano")
        ranges.add_row(name="Bass", color="#ff0000")
        soprano, bass = ranges.rows[1].id, ranges.rows[2].id
        left, _ = ranges.create_component(CK.RANGE, start=0.0, end=1.0, row_id=soprano)
        right, _ = ranges.create_component(CK.RANGE, start=1.0, end=2.0, row_id=soprano)
        low, _ = ranges.create_component(CK.RANGE, start=0.5, end=1.5, row_id=bass)
        ranges.set_component_data(low.id, "comments", "tag=bass")
        ranges.set_component_data(low.id, "pre_start", 0.25)
        ranges.set_component_data(left.id, "label", "a")
        ranges.set_component_data(left.id, "joined_right", right.id)

    media = _path("GEN_MEDIA")
    post(Post.PLAYER_URL_CHANGED, media)
    app.player.media_path = media
    file_manager.save(app.get_app_state(), out)


def resave(source: Path, out: Path) -> None:
    app = _boot()
    app.on_open(source)
    app.file_manager.save(app.get_app_state(), out)


if __name__ == "__main__":
    command, *arguments = sys.argv[1:]
    if command == "new":
        new(Path(arguments[0]).resolve())
    elif command == "resave":
        resave(Path(arguments[0]).resolve(), Path(arguments[1]).resolve())
    elif command == "neutral":
        neutral(*arguments)
    else:
        sys.exit(f"unknown command {command!r}")
