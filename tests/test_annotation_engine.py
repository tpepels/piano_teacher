from pathlib import Path

from piano_teacher.server import PracticeEngine

FIXTURES=Path(__file__).parent/'fixtures/musical_fidelity'


def test_production_semantic_endpoint_uses_projected_source_instructions(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(FIXTURES/'xml_expressions.musicxml'))
        engine.plan.set_hand('both')
        engine.plan.variant_index=len(engine.plan.variants)-1
        model=engine.semantic_score()
        assert model['annotations']
        assert {'dynamics','articulations','ornaments'} <= {a['kind'] for a in model['annotations']}
        assert all(r['status'] != 'unsupported' for r in model['projection_report'])
    finally:
        engine.db.close()


def test_optional_events_cached_for_the_active_production_phrase(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(FIXTURES/'xml_advanced.musicxml'))
        engine.plan.set_hand('right')
        optional=engine.optional_notes()
        assert len(optional)==1
        assert optional is engine.optional_notes()
        assert optional[0]['anchor_source_id'] in {n.source_id for n in engine.plan.active_phrase.notes}
    finally:
        engine.db.close()


def test_production_preparation_supplies_every_required_annotation_fragment(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(FIXTURES/'xml_expressions.musicxml'))
        engine.plan.set_hand('both')
        engine.plan.variant_index=len(engine.plan.variants)-1
        model=engine.semantic_score()
        layout=engine.geometry(native_notes=True)
        assert set(layout['native_annotation_fragments'])=={a['id'] for a in model['annotations']}
        assert not layout.get('native_annotations_error')
    finally:
        engine.db.close()


def test_grace_geometry_does_not_add_required_attacks_or_shift_them(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(FIXTURES/'xml_advanced.musicxml'))
        engine.plan.set_hand('both')
        engine.plan.variant_index=len(engine.plan.variants)-1
        model=engine.semantic_score()
        layout=engine.geometry(native_notes=True)
        assert len(layout['attack_map'])==len(model['notes'])==5
        assert set(layout['native_annotation_fragments'])=={a['id'] for a in model['annotations']} | {g['id'] for g in model['visual_events']}
    finally:
        engine.db.close()
