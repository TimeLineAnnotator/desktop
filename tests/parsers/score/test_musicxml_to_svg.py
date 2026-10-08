import time
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from tests.mock import patch_file_dialog
from tilia.parsers.score import musicxml_to_svg as musicxml_to_svg_module
from tilia.parsers.score.musicxml_to_svg import musicxml_to_svg
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


def get_converters() -> list[musicxml_to_svg]:
    return [w for w in QApplication.allWidgets() if isinstance(w, musicxml_to_svg)]


@pytest.fixture
def stub_osmd_page(tmp_path):
    path = tmp_path / "svg_maker.html"
    path.write_text(STUB_PAGE, encoding="utf-8")
    before = set(get_converters())
    with patch.object(musicxml_to_svg_module, "SVG_MAKER_PATH", path):
        yield
    # A converter deletes itself only once OSMD has sent back an SVG.
    for converter in set(get_converters()) - before:
        converter.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("title", TITLES.values(), ids=TITLES.keys())
def test_score_reaches_osmd_page_unchanged(
    title, stub_osmd_page, score_tlui, beat_tlui, beat_tl, tmp_path
):
    beat_tl.beat_pattern = [1]
    for time_ in range(3):
        beat_tl.create_beat(time_)
    beat_tl.recalculate_measures()
    path = tmp_path / "score.musicxml"
    path.write_text(SCORE.format(title=title), encoding="utf-8")
    before = set(get_converters())
    sent = []
    to_svg = musicxml_to_svg.to_svg

    def spy(converter, data):
        sent.append(data)
        return to_svg(converter, data)

    with (
        patch.object(musicxml_to_svg, "to_svg", spy),
        patch_file_dialog(True, [str(path)]),
    ):
        commands.execute("timelines.import.score")

    (converter,) = set(get_converters()) - before
    assert wait_until(lambda: converter.title() == "received"), "No score arrived."
    received = []
    converter.page().runJavaScript("window.received", 0, received.append)
    assert wait_until(lambda: received)
    assert received[0] == sent[0]
    assert f"<work-title>{title}</work-title>" in received[0]
