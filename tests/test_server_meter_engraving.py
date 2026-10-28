"""The production renderer must receive the same measure grid as recovery."""
import xml.etree.ElementTree as ET

from piano_teacher.application import score_artifacts
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def test_engine_engraves_source_meter_changes_instead_of_averaging_bars(tmp_path, monkeypatch):
    from piano_teacher import server
    original = score_artifacts.build_lesson_score
    rendered = []

    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        rendered.append(ET.fromstring(result.musicxml))
        return result

    monkeypatch.setattr(score_artifacts, "build_lesson_score", capture)
    notes = (Note(0, 1, 60, 0, 0, "right"), Note(3, 4, 64, 0, 0, "right"))
    phrase = Phrase(1, 1, 2, 0, 7, notes)
    piece = Piece("Changing meter", 80, notes, (phrase,),
                  bar_boundaries=(0, 3, 7), time_signatures=((0, 3, 4), (3, 4, 4)))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece)
        engine.engraving()
        measures = rendered[0].findall("./part[@id='RH']/measure")
        assert [(m.findtext("attributes/time/beats"), m.findtext("attributes/time/beat-type"))
                for m in measures] == [("3", "4"), ("4", "4")]
    finally:
        engine.db.close()
