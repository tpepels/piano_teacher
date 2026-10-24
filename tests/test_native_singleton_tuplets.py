"""Visible one-event tuplets are required source ink, including rest anchors."""
import json
from pathlib import Path
import shutil
import subprocess
import os
from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest
import numpy as np
from PIL import Image

from piano_teacher.server import PracticeEngine
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.score import render_layout

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("rest", [False, True])
def test_native_requires_authentic_visible_singleton_artwork(tmp_path, rest):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot is required")
    head = "<rest/>" if rest else "<pitch><step>C</step><octave>5</octave></pitch>"
    xml = ("<score-partwise version='4.0'><part-list><score-part id='RH'>"
           "<part-name>Right Hand</part-name></score-part></part-list><part id='RH'>"
           "<measure number='1' implicit='yes'><attributes><divisions>20</divisions>"
           "<time><beats>4</beats><beat-type>4</beat-type></time>"
           "<clef><sign>G</sign><line>2</line></clef></attributes>"
           f"<note id='solo'>{head}<duration>19</duration><voice>1</voice><type>quarter</type>"
           "<time-modification><actual-notes>20</actual-notes><normal-notes>19</normal-notes>"
           "</time-modification><notations><tuplet type='start' number='1' bracket='yes' "
           "show-number='both'/><tuplet type='stop' number='1'/></notations></note>"
           + ("<note id='after'><pitch><step>E</step><octave>5</octave></pitch><duration>20</duration>"
              "<voice>1</voice><type>quarter</type></note>" if rest else "")
           + "</measure></part></score-partwise>")
    path = tmp_path/"singleton.musicxml"
    path.write_text(xml)
    engine = PracticeEngine(tmp_path/"cache", enable_midi=False)
    try:
        engine.load(str(path))
        engine.plan.restore_location(kind="learn", first_bar=1, last_bar=1,
                                     hand="right", level="original")
        piece = engine.plan.piece
        score = build_lesson_score(engine.display_phrase(), boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, source_musicxml=piece.source_musicxml)
        # Exercise the compositor with an explicit visible source choice.
        # The MIDI lesson writer ordinarily keeps an isolated ratio hidden.
        root = ET.fromstring(score.musicxml)
        target = next(n for n in root.find("part").findall("measure/note")
                      if n.find("time-modification") is not None)
        start = target.find("notations/tuplet[@type='start']")
        start.set("show-number", "both")
        start.set("bracket", "yes")
        score = replace(score, musicxml=ET.tostring(root, encoding="unicode"))
        model = build_score_model(score, boundaries=piece.bar_boundaries, hand="right")
        engraved = render_layout(score, 1, 1, "right", total_beats=score.phrase.end,
                                 bpm=120, continuous=True)
        layout = assemble_layout(engraved, native_model=model, notation_xml=score.musicxml)
    finally:
        engine.db.close()
    payload = dict(model=model, assets=layout)
    fixture = tmp_path/"fixture.json"
    fixture.write_text(json.dumps(payload))
    graphical = bool(os.environ.get("DISPLAY"))
    display = ["--rendering-method", "gl_compatibility", "--disable-vsync", "--max-fps", "0",
               "--resolution", "16x16", "--position", "-16384,-16384"] if graphical else ["--headless"]
    result = subprocess.run([godot, *display, "--path", str(ROOT/"godot"),
        "--script", str(ROOT/"tests/godot/native_singleton_tuplets.gd"), "--", str(fixture),
        *([str(tmp_path)] if graphical else [])],
        capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout+result.stderr
    assert "NATIVE_SINGLETON_TUPLET_CHECKED:1" in result.stdout
    if graphical:
        before = np.asarray(Image.open(tmp_path/"with-tuplet.png").convert("RGB"), dtype=int)
        after = np.asarray(Image.open(tmp_path/"without-tuplet.png").convert("RGB"), dtype=int)
        removed = (before-after).min(axis=2) > 20
        assert removed.sum() >= 35, "Visible singleton number and bracket were never drawn"
        assert not ((after-before).max(axis=2) > 5).any(), "Suppressing artwork changed unrelated score ink"
