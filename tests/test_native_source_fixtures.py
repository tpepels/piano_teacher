"""Imported notation goes through the production backend and native compositor."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from piano_teacher.server import PracticeEngine

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['xml_expressions.musicxml','xml_advanced.musicxml',
    'xml_nested_cross_measure_tuplets.musicxml','xml_rest_tuplets.musicxml',
    'xml_independent_slurs.musicxml'])
def test_imported_source_fixture_renders_every_required_note_without_fallback(name,tmp_path):
    godot=shutil.which('godot') or shutil.which('godot4')
    if not godot:
        pytest.skip('Godot unavailable')
    engine=PracticeEngine(tmp_path/'cache',enable_midi=False)
    try:
        engine.load(str(ROOT/'tests/fixtures/musical_fidelity'/name))
        if 'both' in engine.plan.hands:
            engine.plan.set_hand('both')
        engine.plan.variant_index=len(engine.plan.variants)-1
        model=engine.semantic_score()
        layout=engine.geometry(native_notes=True)
        assert not layout.get('native_annotations_error')
        payload=tmp_path/'payload.json'
        payload.write_text(json.dumps({'model':model,'layout':layout}))
        report=tmp_path/'native.json'
        run=subprocess.run([godot,'--headless','--path',str(ROOT/'godot'),'--script',
            str(ROOT/'tests/godot/native_library.gd'),'--',str(payload),str(report)],
            capture_output=True,text=True,timeout=60,
            env={**os.environ,'PIANO_TEACHER_NATIVE_NOTATION':'1'})
        data=json.loads(report.read_text()) if report.exists() else {}
        assert run.returncode==0,(data,run.stdout,run.stderr)
        assert 'SCRIPT ERROR' not in run.stderr
        assert data['native_ready'] and data['linear_timeline']
        assert data['drawn_noteheads']==data['expected_noteheads']>0
        assert not data['missing_noteheads'] and data['pixels_per_beat']<=480
        requested={a['id'] for a in model['annotations']}|{g['id'] for g in model['visual_events']}
        assert set(layout['native_annotation_fragments'])==requested
    finally:
        engine.db.close()
