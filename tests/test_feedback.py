"""Assessment -> exact engraved glyph feedback regressions."""
from piano_teacher.feedback import project_assessment
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import Assessment, NoteAssessment, PlayedNote, evaluate
from piano_teacher.score_geometry import layout_from_pages


def sample_layout():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600"><g class="system" id="s1">'
    for name, x, y in [('a', 120, 110), ('b', 280, 140), ('c', 350, 100),
                       ('d', 490, 110), ('e', 510, 160), ('f', 680, 140)]:
        svg += f'<g id="{name}" class="note"><g class="notehead"><use x="{x}" y="{y}" /></g></g>'
    svg += '</g></svg>'
    timemap = [dict(qstamp=0, on=['a']),dict(qstamp=1,on=['b']),
               dict(qstamp=2,on=['c']),dict(qstamp=3,on=['d','e']),dict(qstamp=4,on=['f'])]
    return layout_from_pages([svg], timemap, 6,
                             pitches={'a':60,'b':62,'c':64,'d':60,'e':67,'f':62})


def fixture():
    notes = (Note(0,1,60,0,0,'right'),Note(1,2,62,0,0,'right'),
             Note(2,3,64,0,0,'right'),Note(3,4,60,0,0,'right'),
             Note(3,4,67,0,0,'right'),Note(4,5,62,0,0,'right'))
    return Phrase(1,1,2,0,6,notes)


def test_wrong_early_late_short_and_missed_are_at_real_glyph_coordinates():
    phrase=fixture()
    # First pitch incorrect; 2nd early; 3rd late; 4th short; 5th missed; 6th correct.
    played=[PlayedNote(61,0,1),PlayedNote(62,.82,1.82),PlayedNote(64,2.18,3.18),
            PlayedNote(60,3,3.2),PlayedNote(62,4,5)]
    assessed=evaluate(phrase,'right',60,played)
    assert [n.status for n in assessed.notes] == ['wrong','early','late','short','missed','correct']
    assert assessed.extra_notes == 0
    projected=project_assessment(assessed,phrase,60,sample_layout())
    assert projected['unmapped']==0
    assert [m['status'] for m in projected['marks']] == ['wrong','early','late','short','missed','correct']
    assert [m['note_id'] for m in projected['marks']] == list('abcdef')
    assert projected['marks'][0]['x']==0.12
    assert projected['marks'][4]['y']==160/600


def test_extra_note_reports_pitch_and_onset_not_fake_notehead():
    phrase=fixture()
    played=[PlayedNote(n.pitch,n.start,n.end) for n in phrase.notes]
    played.append(PlayedNote(72,2.5,2.7))
    assessed=evaluate(phrase,'right',60,played)
    assert assessed.extra_notes == 1
    marks=project_assessment(assessed,phrase,60,sample_layout())['marks']
    extra=[m for m in marks if m['status']=='extra']
    assert len(extra)==1
    assert extra[0]['label']=='C5'
    assert extra[0]['estimated'] is True
    assert extra[0]['x'] == 0.425  # Interpolates between notes at beats 2 and 3


def test_repeated_pitch_matches_unique_notehead_and_unmatched_is_not_invented():
    phrase=fixture()
    assessment=Assessment((NoteAssessment(phrase.notes[0],'missed'),
                           NoteAssessment(phrase.notes[3],'late')),
                          0)
    projected=project_assessment(assessment,phrase,60,sample_layout())
    assert [m['note_id'] for m in projected['marks']]==['a','d']
    wrong_pitch=Assessment((NoteAssessment(Note(0,1,73,0,0,'right'),'missed'),),0)
    missing=project_assessment(wrong_pitch,phrase,60,sample_layout())
    assert missing['marks']==[]
    assert missing['unmapped']==1


def test_feedback_stays_on_correct_page():
    first='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600"><g class="system" id="s"><g class="note" id="one"><use x="100" y="200" /></g></g></svg>'
    second=first.replace('one','two').replace('x="100"','x="400"')
    layout=layout_from_pages([first,second],
                             [{'qstamp':0,'on':['one']},{'qstamp':1,'on':['two']}],2,
                             {'one':60,'two':62})
    phrase=Phrase(1,1,2,0,2,(Note(1,2,62,0,0,'right'),))
    assessed=Assessment((NoteAssessment(phrase.notes[0],'missed'),),0)
    feedback=project_assessment(assessed,phrase,60,layout)
    assert feedback['marks'][0]['page']==1
    assert feedback['marks'][0]['x']==.4
