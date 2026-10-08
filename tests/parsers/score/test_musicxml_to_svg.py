import time
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from tilia.parsers.score.musicxml_to_svg import musicxml_to_svg

# A title that would end a JavaScript template literal, and run code inside one.
SCORE = (
    "<score-partwise><work><work-title>"
    "Rock `n` roll ${window.ran = true} \\u0041"
    "</work-title></work></score-partwise>"
)


def process_events_until(condition, timeout: float = 10.0) -> bool:
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


def test_score_reaches_osmd_page_unchanged(qtui):
    scripts = []
    converter = musicxml_to_svg(0)
    converter.is_engine_loaded = True  # as if svg_maker.html had loaded
    with patch.object(
        QWebEnginePage,
        "runJavaScript",
        lambda _page, script, *_: scripts.append(script),
    ):
        converter.to_svg(SCORE)
    converter.deleteLater()

    # Runs what the converter sent in a page whose loadSVG only keeps its text.
    page = QWebEnginePage()
    loaded = []
    page.loadFinished.connect(loaded.append)
    page.load(QUrl("about:blank"))
    assert process_events_until(lambda: loaded)
    run_js(page, "window.loadSVG = (text) => { window.received = text; }; true")
    run_js(page, scripts[0])

    assert run_js(page, "window.received") == SCORE
    assert run_js(page, "window.ran === undefined")

    page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
