import time
from html import escape
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWebEngineCore import QWebEnginePage

from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.parsers.score.musicxml_to_svg import musicxml_to_svg
from tilia.timelines.component_kinds import ComponentKind

# Stands in for svg_maker.html: keeps the text loadSVG gets, and needs no network.
STUB_PAGE = (
    "<html><body><script>"
    "window.loadSVG = (text) => { window.received = text; };"
    "</script></body></html>"
)

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


def process_events_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        QCoreApplication.processEvents()
        time.sleep(0.005)
    return True


def run_js(page: QWebEnginePage, script: str):
    results = []
    page.runJavaScript(script, 0, results.append)
    assert process_events_until(lambda: results), f"No result from {script!r}"
    return results[0]


@pytest.fixture
def osmd_pages():
    """The pages the score import opens for OSMD, showing STUB_PAGE instead."""
    views = []

    def load(view, _url):
        view.setHtml(STUB_PAGE)
        views.append(view)

    try:
        with patch.object(musicxml_to_svg, "load", load):
            yield views
    finally:
        for view in views:
            view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def import_score_titled(title: str, score_tl, beat_tl, tmp_path) -> None:
    beat_tl.beat_pattern = [1]
    for time_ in range(3):
        beat_tl.create_component(ComponentKind.BEAT, time_)
    beat_tl.recalculate_measures()
    path = tmp_path / "score.musicxml"
    path.write_text(SCORE.format(title=escape(title)), encoding="utf-8")
    success, errors = notes_from_musicXML(score_tl, beat_tl, str(path))
    assert success, errors


def text_received(view) -> str:
    page = view.page()
    assert process_events_until(
        lambda: run_js(page, "window.received !== undefined")
    ), "OSMD's page got no score."
    return run_js(page, "window.received")


def test_backticks_reach_osmd_page(osmd_pages, score_tl, beat_tl, tmp_path):
    import_score_titled("Rock `n` roll \\u0041", score_tl, beat_tl, tmp_path)

    (view,) = osmd_pages
    assert "<work-title>Rock `n` roll \\u0041</work-title>" in text_received(view)


def test_code_in_score_does_not_run(osmd_pages, score_tl, beat_tl, tmp_path):
    import_score_titled("${window.ran = true}", score_tl, beat_tl, tmp_path)

    (view,) = osmd_pages
    assert "<work-title>${window.ran = true}</work-title>" in text_received(view)
    assert run_js(view.page(), "window.ran === undefined")
