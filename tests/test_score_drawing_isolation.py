import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from tests.mock import patch_file_dialog
from tilia.parsers.score.musicxml_to_svg import musicxml_to_svg
from tilia.ui import commands

SCORE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
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


def _import_score(beat_tlui, tmp_path):
    beat_tlui.timeline.beat_pattern = [1]
    for time in range(3):
        commands.execute("timeline.beat.add", time=time)
    path = tmp_path / "score.musicxml"
    path.write_text(SCORE, encoding="utf-8")
    with patch_file_dialog(True, [str(path)]):
        commands.execute("timelines.import.score")


def _converters() -> list[musicxml_to_svg]:
    return [w for w in QApplication.allWidgets() if isinstance(w, musicxml_to_svg)]


class TestScoreDrawingIsolation:
    """Drawing a score starts a web engine that loads OSMD from its CDN and
    finishes long after the test that imported the score, so the suite leaves
    imported scores undrawn unless a test is marked `draws_scores`."""

    def test_imported_score_is_not_drawn(self, score_tlui, beat_tlui, tmp_path):
        _import_score(beat_tlui, tmp_path)

        assert not _converters()

    @pytest.mark.draws_scores
    def test_imported_score_is_drawn_when_marked(self, score_tlui, beat_tlui, tmp_path):
        _import_score(beat_tlui, tmp_path)

        converters = _converters()
        assert converters
        for converter in converters:
            converter.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
