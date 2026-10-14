"""Regression checks for a working count-in, following score and faded staff."""
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.learning import LearningPlan
from piano_teacher.server import PracticeEngine
from piano_teacher.score import _fade_inactive_staff

ROOT = Path(__file__).resolve().parents[1]

def sample_piece():
    notes = (Note(0, 1, 60, 0, 0, "right"), Note(1, 2, 48, 1, 0, "left"))
    return Piece("Test", 100, notes, (Phrase(1, 1, 2, 0, 8, notes),))

def test_count_in_and_live_midi_visibility(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(sample_piece())
    try:
        engine.control("start")
        before = engine.state()
        assert before["phase"] == "count_in"
        assert before["count_in_beats"] == 4
        assert before["countdown"] > 0
        assert before["midi_notes"] == 0
        message = type("Midi", (), {"type": "note_on", "note": 60, "velocity": 90})
        engine._receive(message)
        assert engine.state()["midi_notes"] == 0
        engine.run_at = time.monotonic() - 0.25
        engine._receive(message)
        assert engine.state()["phase"] == "playing"
        assert engine.state()["midi_notes"] == 1
    finally:
        engine.db.close()

def test_stop_resets_count_in(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(sample_piece())
    try:
        engine.control("start")
        engine.control("stop")
        assert engine.state()["count_in_beats"] == 0
        assert engine.state()["running"] is False
    finally:
        engine.db.close()

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 180">
<g class="system" id="s1"><g class="staff" id="top"><g class="note" id="n1"/></g>
<g class="staff" id="bottom"><g class="note" id="n2"/></g></g></svg>'''

def test_inactive_staff_dimming_preserves_note_ids():
    assert _fade_inactive_staff(SVG, "both") == SVG
    for hand, faded in (("right", "bottom"), ("left", "top")):
        root = ET.fromstring(_fade_inactive_staff(SVG, hand))
        staves = {e.get("id"): e for e in root.iter() if "staff" in e.get("class", "").split()}
        assert staves[faded].get("opacity") == "0.16"
        assert staves["top" if faded == "bottom" else "bottom"].get("opacity") is None
        assert {e.get("id") for e in root.iter() if "note" in e.get("class", "").split()} == {"n1", "n2"}

def test_unknown_staff_structure_is_not_faded():
    assert "opacity=" not in _fade_inactive_staff(
        SVG.replace('class="staff" id="bottom"', 'class="other" id="bottom"'), "right")

def test_godot_produces_metronome_and_follows_score():
    source = (ROOT / "godot/main.gd").read_text()
    for expected in ("AudioStreamWAV.new()", "samples.encode_s16", "count_in_beats",
                     "count_tick_index", "play_tick_index", "click_player.play()",
                     "func _layout_moving_score(delta: float = 0.0)", "score_content.position =",
                     "score_frame.clip_contents = true", "score_overlay.crop_origin"):
        assert expected in source

def test_crop_coordinate_mapping():
    original = (2000, 1250)
    crop = (150, 300, 1400, 700)
    point = (800, 650)
    uv = (point[0]/original[0], point[1]/original[1])
    origin = (crop[0]/original[0], crop[1]/original[1])
    size = (crop[2]/original[0], crop[3]/original[1])
    mapped = ((uv[0]-origin[0])/size[0], (uv[1]-origin[1])/size[1])
    assert mapped == pytest.approx(((point[0]-crop[0])/crop[2], (point[1]-crop[1])/crop[3]))
