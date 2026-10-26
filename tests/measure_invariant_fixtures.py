"""Bounded real score inputs for independent measure and motion pixel proof."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALA = 'Ala_–_Joep_Beving.midi'
PEACE = 'Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
DENSITY = 96.0
VIEWPORTS = [(800, 600), (1220, 780), (1600, 1000)]
TEMPOS = [40, 80, 120]
CASES = {
    'ala': (ALA, 29, 32, 'both', None),
    'peace-pickup': (PEACE, 1, 2, 'both', None),
    'peace-simplified': (PEACE, 1, 2, 'right', 2),
    'source-rests': ('tests/fixtures/native_pixel_rest_probe.musicxml', 1, 4, 'both', None),
    'mixed-meter': ('tests/fixtures/continuous_repetition_context.musicxml', 1, 2, 'both', None),
}


def prepare_measure_fixture(name: str, folder: Path) -> tuple[dict, dict]:
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.learning import LearningPlan
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    filename, first, last, hand, step = CASES[name]
    path = ROOT / filename if '/' in filename else ROOT / 'midi' / filename
    piece, _ = import_piece(path)
    phrase = None
    if step is not None:
        plan = LearningPlan(piece)
        plan.select_step(step)
        phrase = plan.active_phrase
    data, engraving = fixture(AuditCase(name, str(path), first, last, hand), piece=piece, phrase=phrase)
    model = data['model']
    if step is not None:
        original_sources = {n.source_id for n in piece.notes
                            if phrase.start <= n.start < phrase.end and n.hand == hand}
        assert {n['id'] for n in model['notes']} < original_sources, 'The real lesson must omit source notes'
    state = {'loaded': True, 'revision': model['revision'], 'running': False, 'paused': False,
             'mode': 'practice', 'phase': 'ready', 'hand': hand,
             'title': piece.title, 'bpm': 40, 'target_bpm': piece.bpm,
             'first_bar': first, 'last_bar': last, 'kind': 'learn', 'lesson_step': 1,
             'practice_timeline': model['practice_timeline'], 'feedback_marks': [],
             'midi_visual_events': [], 'piece_fingerprint': name}
    layout = {**engraving.layout, **data['assets'], 'revision': model['revision']}
    (folder / 'native.json').write_text(json.dumps({'model': model, 'layout': layout, 'state': state}))
    (folder / 'score.musicxml').write_text(data['xml'])
    source_duration = float(model['duration_beats'])
    gap = 4.0 if name.startswith('peace') else (3.0 if name in ('ala', 'mixed-meter') else 4.0)
    assert model['practice_timeline']['gap']['duration_beats'] == gap
    stride = source_duration + gap
    configuration = {'density': DENSITY, 'gap_beats': gap, 'hand': hand,
        'viewports': VIEWPORTS, 'tempos': TEMPOS, 'step_beats': .125,
        'samples': [
            {'name': 'populated', 'clock': max(.5, source_duration - 4)},
            {'name': 'terminal', 'clock': max(0., source_duration - 2), 'state': {'score_loop_enabled': False}},
            {'name': 'into-rest', 'clock': source_duration - .125},
            {'name': 'rest', 'clock': source_duration + gap / 2 - .125},
            {'name': 'repeat', 'clock': stride - .125},
            {'name': 'pause-resume', 'clock': source_duration+gap/2, 'count': 5, 'pause_roundtrip': True},
        ]}
    (folder / 'capture.json').write_text(json.dumps(configuration))
    (folder / 'fixture.json').write_text(json.dumps(data))
    return data, configuration
