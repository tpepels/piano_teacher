from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model

FIXTURES=Path(__file__).parent/'fixtures/musical_fidelity'


def compile_fixture(name):
    piece=load_musicxml(FIXTURES/name,bpm=80)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,piece.bar_boundaries[-1],piece.notes)
    score=build_lesson_score(phrase,boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,clef_changes=piece.clef_changes,
        barlines=piece.barlines,source_notation=piece.source_notation)
    return piece,score,build_score_model(score,boundaries=piece.bar_boundaries)


def test_grace_128ths_many_dots_voltas_and_source_clef_survive_projection():
    piece,score,model=compile_fixture('xml_advanced.musicxml')
    root=ET.fromstring(score.musicxml)
    assert len(piece.notes)==len(model['notes'])==5
    assert len(model['visual_events'])==1
    assert model['visual_events'][0]['anchor_id'] in score.note_bindings
    assert root.find('.//note[type="128th"]') is not None
    assert max(e['dots'] for e in model['notation_events'])==5
    assert model['measures'][0]['clefs']['right']=={'sign':'C','line':4,'octave_change':1}
    assert len(root.findall('.//ending'))==2
    assert any(a['kind']=='ending' for a in model['annotations'])


def test_nested_groups_cross_measure_boundary_and_include_original_rests():
    piece,score,model=compile_fixture('xml_nested_cross_measure_tuplets.musicxml')
    groups=[g for g in model['groups'] if g['kind']=='tuplet' and len(g['event_ids'])>1]
    assert len(groups)==2
    assert len({g['id'] for g in groups})==2
    outer=max(groups,key=lambda g:len(g['event_ids']))
    assert len(outer['event_ids'])==5 and abs(outer['start_beat']-4/3)<1e-7
    assert outer['end_beat']>model['measures'][0]['end_beat']
    events={e['id']:e for e in model['notation_events']}
    assert any(events[i]['kind']=='rest' for i in outer['event_ids'])
    assert [n['id'] for n in model['notes']]==[n.source_id for n in sorted(piece.notes,key=lambda n:(n.start,n.hand,n.pitch,n.source_id))]


def test_concurrent_slur_numbers_remain_independent_per_source_voice():
    piece,score,model=compile_fixture('xml_independent_slurs.musicxml')
    groups=[g for g in model['groups'] if g['kind']=='slur']
    assert len(groups)==2
    assert all(len(g['event_ids'])==2 for g in groups)


def test_original_rest_only_tuplets_survive_without_becoming_graded_notes():
    piece,score,model=compile_fixture('xml_rest_tuplets.musicxml')
    groups=[g for g in model['groups'] if g['kind']=='tuplet' and len(g['event_ids'])>1]
    assert len(groups)==2
    by_id={e['id']:e for e in model['notation_events']}
    assert all(by_id[i]['kind']=='rest' for g in groups for i in g['event_ids'])
    assert len(model['notes'])==len(piece.notes)==2


@pytest.mark.parametrize("part_name,staff", [
    ("Left hand", "1"), ("LH", "1"), ("Mano sinistra", "1"),
    ("Grand Piano", "2"),
])
def test_left_rest_only_staff_and_directions_keep_the_importer_hand(tmp_path, part_name, staff):
    root=ET.parse(FIXTURES/'xml_rest_tuplets.musicxml').getroot()
    rest_part,pitched_part=root.findall('part')
    definitions=root.findall('./part-list/score-part')
    definitions[0].find('part-name').text=part_name
    definitions[1].find('part-name').text='Right hand'
    if staff == '2':
        # A single unnamed grand staff: only the upper staff has pitched
        # events. The lower staff consists entirely of original tuplets/rests.
        attributes=rest_part.find('./measure/attributes')
        ET.SubElement(attributes,'staves').text='2'
        lower=attributes.find('clef')
        lower.set('number','2')
        lower.find('sign').text='F'
        lower.find('line').text='4'
        upper=ET.SubElement(attributes,'clef',number='1')
        ET.SubElement(upper,'sign').text='G'
        ET.SubElement(upper,'line').text='2'
        for target,source in zip(rest_part.findall('measure'),pitched_part.findall('measure')):
            backup=ET.SubElement(target,'backup')
            ET.SubElement(backup,'duration').text='5760'
            for note in source.findall('note'):
                ET.SubElement(note,'staff').text='1'
                target.append(note)
        root.remove(pitched_part)
        root.find('part-list').remove(definitions[1])
    for note in rest_part.findall('./measure/note'):
        if note.find('rest') is not None:
            ET.SubElement(note,'staff').text=staff
    direction=ET.Element('direction')
    dynamics=ET.SubElement(ET.SubElement(direction,'direction-type'),'dynamics')
    ET.SubElement(dynamics,'p')
    ET.SubElement(direction,'voice').text='9'
    ET.SubElement(direction,'staff').text=staff
    rest_part.find('measure').insert(1,direction)
    path=tmp_path/'left-rest-only.musicxml'
    path.write_text(ET.tostring(root,encoding='unicode'))
    piece=load_musicxml(path,bpm=80)
    assert len(piece.notes)==2 and all(n.hand=='right' for n in piece.notes)
    rests=[e for e in piece.source_notation.events if ET.fromstring(e.xml).find('rest') is not None]
    assert len(rests)==8 and all(e.hand=='left' for e in rests)
    assert [m.hand for m in piece.source_notation.marks if m.kind=='dynamics']==['left']
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,piece.bar_boundaries[-1],piece.notes)
    score=build_lesson_score(phrase,boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,clef_changes=piece.clef_changes,
        barlines=piece.barlines,source_notation=piece.source_notation)
    model=build_score_model(score,boundaries=piece.bar_boundaries)
    by_id={e['id']:e for e in model['notation_events']}
    assert all(by_id[e.id]['kind']=='rest' and by_id[e.id]['staff']=='left' for e in rests)
    groups=[g for g in model['groups'] if g['kind']=='tuplet' and len(g['event_ids'])>1]
    assert len(groups)==2 and all(by_id[i]['staff']=='left' for g in groups for i in g['event_ids'])
    assert len(model['notes'])==2
