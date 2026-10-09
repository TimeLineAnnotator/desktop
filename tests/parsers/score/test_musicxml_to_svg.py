import re
import time
from unittest.mock import patch

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent

from tests.mock import patch_file_dialog
from tilia.errors import SCORE_SVG_CREATE_ERROR
from tilia.parsers.score import musicxml_to_svg as musicxml_to_svg_module
from tilia.parsers.score.musicxml_to_svg import SVG_MAKER_PATH, musicxml_to_svg
from tilia.ui import commands

# Stands in for svg_maker.html: keeps the text loadSVG gets, says so in its
# title, and needs no network.
STUB_PAGE = """<html><head><title>waiting</title></head><body><script>
window.loadSVG = (text) => { window.received = text; document.title = "received"; };
</script></body></html>
"""

SCORE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>{title}</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>1</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>5</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""

# Each would have come out changed, or broken the script, in a template
# literal. Kept apart, as the backticks' syntax error would hide the others.
TITLES = {
    "backticks": "Rock `n` roll",
    "code": "${window.ran = true}",
    "backslashes": r"C:\new \u0041",
}


def wait_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return True


@pytest.fixture
def osmd_calls(tmp_path):
    """The converters that load STUB_PAGE while it's active, with the text each
    is asked to convert."""
    path = tmp_path / "svg_maker.html"
    path.write_text(STUB_PAGE, encoding="utf-8")
    calls = []
    to_svg = musicxml_to_svg.to_svg

    def record(converter, data):
        calls.append((converter, data))
        return to_svg(converter, data)

    with (
        patch.object(musicxml_to_svg_module, "SVG_MAKER_PATH", path),
        patch.object(musicxml_to_svg, "to_svg", record),
    ):
        yield calls
    # A converter deletes itself once OSMD sends back an SVG or an error, and
    # the stub page sends neither.
    for converter, _ in calls:
        converter.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("title", TITLES.values(), ids=TITLES.keys())
def test_score_reaches_osmd_page_unchanged(
    title, osmd_calls, score_tlui, beat_tlui, beat_tl, tmp_path
):
    beat_tl.beat_pattern = [1]
    for time_ in range(3):
        beat_tl.create_beat(time_)
    beat_tl.recalculate_measures()
    path = tmp_path / "score.musicxml"
    path.write_text(SCORE.format(title=title), encoding="utf-8")

    with patch_file_dialog(True, [str(path)]):
        commands.execute("timelines.import.score")

    ((converter, sent),) = osmd_calls
    assert wait_until(lambda: converter.title() == "received"), "No score arrived."
    received = []
    converter.page().runJavaScript("window.received", 0, received.append)
    assert wait_until(lambda: received)
    assert received[0] == sent
    assert f"<work-title>{title}</work-title>" in received[0]


OSMD_SCRIPT = re.compile(
    r'src="https://cdn\.jsdelivr\.net/npm/opensheetmusicdisplay@[^"]+"'
)


def _fake_osmd(load: str, render: str = "") -> str:
    """A stand-in for OSMD's script: `load` and `render` are its methods'
    bodies."""
    return f"""window.opensheetmusicdisplay = {{
    OpenSheetMusicDisplay: class {{
        constructor() {{ this.EngravingRules = {{}}; }}
        load(text) {{ {load} }}
        render() {{ {render} }}
    }},
}};"""


# A score page with one beat marker, as the score viewer needs.
DRAW = (
    'document.body.insertAdjacentHTML("beforeend", `<svg id="osmdSvgPage1">'
    '<g class="vf-text"><text font-size="0.000001px" x="10">1\\u241f0\\u241f1'
    "</text></g></svg>`);"
)
FAKE_OSMD = {
    "draws": _fake_osmd("return Promise.resolve();", DRAW),
    "draws nothing": _fake_osmd("return Promise.resolve();"),
    "rejects the score": _fake_osmd(
        'return Promise.reject(new Error("Not a score OSMD can read."));'
    ),
    "draws when released": _fake_osmd(
        "return new Promise((resolve) => { window.release = resolve; });", DRAW
    ),
}


def _use_svg_maker(tmp_path, osmd: str | None):
    """Makes converters load svg_maker.html with OSMD's script replaced by
    `osmd`, or by a file that doesn't exist, as when TiLiA is offline."""
    html, count = OSMD_SCRIPT.subn(
        'src="osmd.js"', SVG_MAKER_PATH.read_text(encoding="utf-8")
    )
    assert count == 1, "svg_maker.html no longer loads OSMD from its CDN."
    page = tmp_path / "svg_maker.html"
    page.write_text(html, encoding="utf-8")
    if osmd is not None:
        (tmp_path / "osmd.js").write_text(osmd, encoding="utf-8")
    return patch.object(musicxml_to_svg_module, "SVG_MAKER_PATH", page)


@pytest.fixture
def converters():
    """The converters created while the test runs."""
    created = []
    init = musicxml_to_svg.__init__

    def record(converter, *args, **kwargs):
        init(converter, *args, **kwargs)
        created.append(converter)

    with patch.object(musicxml_to_svg, "__init__", record):
        yield created
    for converter in created:
        if shiboken6.isValid(converter):
            converter.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _add_beats(beat_tlui):
    beat_tlui.timeline.beat_pattern = [1]
    for time_ in range(3):
        commands.execute("timeline.beat.add", time=time_)


def _import_score(tmp_path, text: str = SCORE.format(title="Title")):
    path = tmp_path / "score.musicxml"
    path.write_text(text, encoding="utf-8")
    with patch_file_dialog(True, [str(path)]):
        commands.execute("timelines.import.score")


def _is_deleted(converter) -> bool:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return not shiboken6.isValid(converter)


def test_drawn_score_is_kept(converters, score_tlui, beat_tlui, tilia_errors, tmp_path):
    _add_beats(beat_tlui)
    with _use_svg_maker(tmp_path, FAKE_OSMD["draws"]):
        _import_score(tmp_path)

    (converter,) = converters
    assert wait_until(lambda: _is_deleted(converter))
    assert 'id="osmdSvgPage1"' in score_tlui.get_data("svg_data")
    tilia_errors.assert_no_error()


@pytest.mark.parametrize(
    "osmd, message",
    [
        (None, "OpenSheetMusicDisplay, which draws the score, couldn't be loaded"),
        (FAKE_OSMD["rejects the score"], "Not a score OSMD can read."),
        (FAKE_OSMD["draws nothing"], "OpenSheetMusicDisplay drew no score."),
    ],
    ids=["offline", "osmd rejects the score", "osmd draws nothing"],
)
def test_score_that_osmd_does_not_draw_is_reported(
    osmd, message, converters, score_tlui, beat_tlui, tilia_errors, tmp_path
):
    _add_beats(beat_tlui)
    with _use_svg_maker(tmp_path, osmd):
        _import_score(tmp_path)

    (converter,) = converters
    assert wait_until(lambda: tilia_errors.errors), "No error was shown."
    assert tilia_errors.errors[0]["title"] == SCORE_SVG_CREATE_ERROR.title
    tilia_errors.assert_in_error_message(message)
    assert wait_until(lambda: _is_deleted(converter))
    assert score_tlui.get_data("svg_data") == ""


def test_page_that_does_not_load_is_reported(
    converters, score_tlui, beat_tlui, tilia_errors, tmp_path
):
    _add_beats(beat_tlui)
    missing = tmp_path / "missing.html"
    with patch.object(musicxml_to_svg_module, "SVG_MAKER_PATH", missing):
        _import_score(tmp_path)

    (converter,) = converters
    assert wait_until(lambda: tilia_errors.errors), "No error was shown."
    tilia_errors.assert_in_error_message("The page that draws the score")
    assert wait_until(lambda: _is_deleted(converter))


def test_file_that_is_not_musicxml_creates_no_converter(
    converters, score_tlui, beat_tlui, tilia_errors, tmp_path
):
    _add_beats(beat_tlui)

    _import_score(tmp_path, "<not-a-score/>")

    tilia_errors.assert_in_error_message("is not valid musicxml")
    assert not converters


def test_score_drawn_after_its_timeline_is_deleted_is_dropped(
    converters, score_tlui, beat_tlui, tilia_errors, tmp_path
):
    _add_beats(beat_tlui)
    with _use_svg_maker(tmp_path, FAKE_OSMD["draws when released"]):
        _import_score(tmp_path)
    (converter,) = converters
    loading = []

    def osmd_is_loading():
        converter.page().runJavaScript("typeof window.release", 0, loading.append)
        return "function" in loading

    assert wait_until(osmd_is_loading)

    commands.execute("timeline.delete", score_tlui, confirm=False)
    converter.page().runJavaScript("window.release()")

    assert wait_until(lambda: _is_deleted(converter))
    tilia_errors.assert_no_error()
