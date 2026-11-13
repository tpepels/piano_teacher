"""MusicXML explicit beaming must survive when its actual source group survives."""
from pathlib import Path
from xml.etree import ElementTree as ET

from piano_teacher.importing.pieces import import_piece
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


def test_beam_photographic_window_contains_actual_three_level_ink_without_reconstructing_it():
    """11-pixel staff spaces: third-level source rows must not be cropped."""
    import numpy as np
    from piano_teacher.notation.connector_pixels import _beam_sample_band, _photographed_beam_runs

    gap = 11.0
    tip = 218.0
    photographed = np.zeros((260, 16), dtype=bool)
    # Three *actual* uninterrupted bright rows, as found in Chopin 14/16.
    for top, bottom in ((198, 204), (207, 212), (215, 220)):
        photographed[top:bottom, 6] = True
    frame = {"pixels": photographed}
    old_low, old_high = round(tip - 1.5 * gap), round(tip + 1.5 * gap)
    assert _photographed_beam_runs(frame, old_low, old_high, 6)[0] == (202, 204)
    low, high = _beam_sample_band(tip, gap, 3, photographed.shape[0])
    assert _photographed_beam_runs(frame, low, high, 6) == [
        (198, 204), (207, 212), (215, 220)]
    assert _beam_sample_band(tip, gap, 1, 260) == (old_low, old_high)
    # A genuinely missing source beam is never painted by the new window.
    photographed[198:204, 6] = False
    assert len(_photographed_beam_runs(frame, low, high, 6)) == 2


