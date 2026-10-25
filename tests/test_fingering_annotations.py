"""Native plan owns fingering ink; every unrelated XML mark stays intact."""
from xml.etree import ElementTree as ET

from piano_teacher.fingering import FingeringService, authored_projection_sources, project_model
from piano_teacher.importing.pieces import import_piece
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


def _source(tmp_path, extra=''):
    path=tmp_path/'authored.musicxml'
    path.write_text('''<score-partwise><part-list><score-part id="P1"><part-name>Right hand</part-name>
    </score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type>
    <notations><technical><fingering>2</fingering>'''+extra+'''</technical></notations></note>
    </measure></part></score-partwise>''')
    return import_piece(path)[0]


def _notation(piece, sources=frozenset()):
    return build_lesson_score(piece.phrases[0],boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml,fingering_sources=sources)


def test_only_projected_fingering_leaves_xml_ink_and_fallback(tmp_path):
    piece=_source(tmp_path)
    plan=FingeringService(tmp_path/'plans').prepare(piece,'source')
    original=_notation(piece)
    assert 'note:technical' in original.unrendered_expressions
    assert ET.fromstring(original.musicxml).find('.//fingering').text=='2'
    native=_notation(piece,authored_projection_sources(plan))
    assert 'note:technical' not in native.unrendered_expressions
    assert ET.fromstring(native.musicxml).find('.//fingering') is None
    model=project_model(build_score_model(native,boundaries=piece.bar_boundaries,hand='right',revision=1),plan)
    assert [e['fingering']['finger'] for e in model['notation_events'] if 'fingering' in e]==[2]
    assert ET.fromstring(piece.source_musicxml).find('.//fingering').text=='2'


def test_unrelated_technical_marks_still_require_fallback(tmp_path):
    piece=_source(tmp_path,'<pluck>p</pluck>')
    plan=FingeringService(tmp_path/'plans').prepare(piece,'source')
    native=_notation(piece,authored_projection_sources(plan))
    assert 'note:technical' in native.unrendered_expressions
    assert ET.fromstring(native.musicxml).find('.//pluck').text=='p'
    assert ET.fromstring(native.musicxml).find('.//fingering') is None


def test_fingering_on_tied_continuation_constrains_original_attack(tmp_path):
    piece=_source(tmp_path)
    root=ET.fromstring(piece.source_musicxml)
    first=root.find('.//note')
    ET.SubElement(first.find('pitch'),'alter').text='0.0'
    first.remove(first.find('notations'))
    ET.SubElement(first,'tie',type='start')
    continuation=ET.fromstring(ET.tostring(first))
    continuation.find('tie').set('type','stop')
    technical=ET.SubElement(ET.SubElement(continuation,'notations'),'technical')
    ET.SubElement(technical,'fingering').text='2'
    measure=ET.SubElement(root.find('part'),'measure',number='2')
    measure.append(continuation)
    path=tmp_path/'tied.musicxml'
    ET.ElementTree(root).write(path)
    imported=import_piece(path)[0]
    assert len(imported.notes)==1
    plan=FingeringService(tmp_path/'plans').prepare(imported,'tie')
    a=plan.assignments[imported.notes[0].source_id]
    assert a.finger==a.authored==2 and a.authored_text==('2',)
    notation=build_lesson_score(imported.phrases[0],boundaries=imported.bar_boundaries)
    model=project_model(build_score_model(notation,boundaries=imported.bar_boundaries,hand='right',revision=1),plan)
    assert sum('fingering' in e for e in model['notation_events'])==1
