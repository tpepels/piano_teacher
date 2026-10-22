"""Generated piano hands share continuous, genuinely engraved measure bars."""
from collections import Counter
import re
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.score import render_layout


STRAIGHT_PATH = re.compile(r"M\s*([-\d.]+)[ ,]+([-\d.]+)\s*L\s*([-\d.]+)[ ,]+([-\d.]+)")


def straight_path(element):
    match = STRAIGHT_PATH.fullmatch(element.get("d", ""))
    return tuple(map(float, match.groups())) if match else None


@pytest.mark.parametrize("active_hand", ("right", "left", "both"))
def test_real_measure_barlines_span_the_complete_piano_grand_staff(active_hand):
    pytest.importorskip("verovio")
    notes = tuple(Note(beat, beat + .5, pitch, 0, 0, hand, f"{hand}-{beat}", "1")
                  for beat in (0, 1, 3, 4)
                  for pitch, hand in ((72, "right"), (48, "left"))
                  if active_hand == "both" or hand == active_hand)
    phrase = Phrase(1, 1, 2, 0, 6, notes)
    lesson = build_lesson_score(phrase)
    score = render_layout(lesson, 1, 2, total_beats=6, bpm=80)
    bar_count = 0
    for svg in score.pages:
        for system in ET.fromstring(svg).iter():
            if "system" not in system.get("class", "").split():
                continue
            staff_rows = []
            for staff in system.iter():
                if "staff" not in staff.get("class", "").split():
                    continue
                for element in staff:
                    line = straight_path(element)
                    if line and line[1] == line[3] and line[0] != line[2]:
                        staff_rows.append(line[1])
            top, bottom = min(staff_rows), max(staff_rows)
            for barline in system.iter():
                if "barLine" not in barline.get("class", "").split():
                    continue
                strokes = {}
                for element in barline:
                    line = straight_path(element)
                    if line and line[0] == line[2]:
                        strokes.setdefault(line[0], []).append(sorted((line[1], line[3])))
                assert strokes, "Measure bars must contain actual engraved vertical strokes"
                for intervals in strokes.values():
                    intervals.sort()
                    assert intervals[0][0] == pytest.approx(top)
                    reached = top
                    for start, end in intervals:
                        assert start <= reached + .01, "Piano measure bar is broken between the two hands"
                        reached = max(reached, end)
                    assert reached == pytest.approx(bottom)
                bar_count += 1
    assert bar_count == 2  # Internal measure boundary and the final boundary.
    assert lesson.phrase is phrase
    require_lesson_alignment(phrase, score.layout, active_hand)
    assert Counter((entry["source_id"], entry["source_beat"], entry["pitch"])
                   for entry in score.layout["notes"] if entry["is_attack"]) == Counter(
        (note.source_id, note.start, note.pitch) for note in notes)
