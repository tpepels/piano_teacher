"""MusicXML explicit beaming must survive when its actual source group survives."""
from pathlib import Path
from xml.etree import ElementTree as ET

from piano_teacher.score import import_piece
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score

ROOT = Path(__file__).resolve().parent
BEAMS = ROOT / "fixtures" / "native_pixel_beam_probe.musicxml"


def _lesson(first, last):
    piece, _ = import_piece(BEAMS)
    start = piece.bar_boundaries[first - 1]
    end = piece.bar_boundaries[last]
    phrase = Phrase(1,first,last,start,end,
                    tuple(n for n in piece.notes if start <= n.start < end))
    return build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml)


def test_explicit_written_beam_groups_survive_full_notation():
    original = ET.parse(BEAMS).getroot()
    score = ET.fromstring(_lesson(1,2).musicxml)
    groups = lambda root: [x.text for x in root.findall(".//part[@id='RH']//beam")]
    assert groups(original) == groups(score)
    assert len(groups(score)) == 16
    assert groups(score).count("begin") == groups(score).count("end") == 4
    assert groups(score).count("continue") == 8


def test_second_measure_beams_keep_original_boundaries():
    score = ET.fromstring(_lesson(2,2).musicxml)
    beams = [x.text for x in score.findall(".//part[@id='RH']//beam")]
    assert beams == ["begin","continue","continue","end"]*2
