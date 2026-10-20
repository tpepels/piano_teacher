from pathlib import Path
from xml.etree import ElementTree as ET
from piano_teacher.server import PracticeEngine

ROOT=Path(__file__).resolve().parents[1]


def test_real_peace_outline_rests_keep_the_same_ids_in_xml_model_and_fragments(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(ROOT/'midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'))
        engine.plan.select(39)
        engine.plan.set_hand('right')
        engine.plan.variant_index=next(i for i,v in enumerate(engine.plan.variants) if v.level=='outline')
        notation=engine._compile_notation(engine.display_phrase())
        model=engine.semantic_score()
        xml=ET.fromstring(notation.musicxml)
        xml_rests={n.get('id') for n in xml.findall('.//note') if n.find('rest') is not None}
        semantic_rests={e['id'] for e in model['notation_events'] if e['kind']=='rest'}
        assert semantic_rests <= xml_rests
        layout=engine.geometry(native_notes=True)
        from piano_teacher.notation.assets.tuplets import _semantic_groups
        for group in _semantic_groups(model):
            key='|'.join(group.get('_legacy_key',group['event_ids']))
            assert key in layout['native_tuplet_fragments'],key
    finally:
        engine.db.close()
