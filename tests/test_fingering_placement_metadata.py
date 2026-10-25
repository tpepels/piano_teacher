"""Authored presentation hints never change original whole-piece assignments."""
from dataclasses import replace

from piano_teacher.fingering import FingeringService, project_model
from piano_teacher.music import Note, Piece


def test_authored_placement_projects_without_inference_or_override_changes(tmp_path):
    source=Piece('Authored',120,(Note(0,2,60,0,0,source_id='xml-p0-m0-e0'),),(),
        source_musicxml='''<score-partwise><part><measure><note><pitch><step>C</step><octave>4</octave></pitch>
        <notations><technical><fingering placement="below" default-y="-50" relative-x="3">2</fingering>
        </technical></notations></note></measure></part></score-partwise>''')
    service=FingeringService(tmp_path)
    plan=service.prepare(source,'authored')
    model={'notation_events':[{'source_id':source.notes[0].source_id,'is_attack':True}]}
    result=project_model(model,plan,source_musicxml=source.source_musicxml)
    assert result['notation_events'][0]['fingering']['placement']=={'placement':'below','default_y':-50.0,'relative_x':3.0}
    assert plan.assignments[source.notes[0].source_id].finger==2
    assert service.prepare(source,'authored')==plan
    assert not list(tmp_path.glob('*/overrides.json'))
    assert 'fingering' not in model['notation_events'][0]


def test_nonfinite_or_unrelated_placement_does_not_invent_hints(tmp_path):
    source=Piece('Authored',120,(Note(0,1,60,0,0,source_id='xml-p0-m0-e0'),),(),
        source_musicxml='''<score-partwise><part><measure><note><pitch><step>C</step><octave>4</octave></pitch>
        <notations><technical><fingering placement="sideways" default-x="nan" relative-y="inf">2</fingering>
        </technical></notations></note></measure></part></score-partwise>''')
    plan=FingeringService(tmp_path).prepare(source,'authored')
    result=project_model({'notation_events':[{'source_id':'xml-p0-m0-e0','is_attack':True}]},plan,
                         source_musicxml=source.source_musicxml)
    assert 'placement' not in result['notation_events'][0]['fingering']
