"""Actual Verovio regression: missing full-page tuplets recover from exact notes."""
from copy import deepcopy
from xml.etree import ElementTree as ET

from piano_teacher.notation.assets.tuplets import tuplet_fragments


def score_xml():
    notes = []
    for index, pitch in enumerate(("C", "D", "E")):
        mark = (f'<notations><tuplet type="{"start" if index == 0 else "stop"}" '
                'number="1" bracket="yes" show-number="actual"/></notations>'
                if index in (0, 2) else "")
        notes.append(
            f'<note id="own{index+1}"><pitch><step>{pitch}</step><octave>5</octave></pitch>'
            '<duration>3360</duration><voice>1</voice><type>eighth</type>'
            '<time-modification><actual-notes>3</actual-notes>'
            '<normal-notes>2</normal-notes></time-modification>'
            + mark + '</note>')
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        '<part-name>Piano</part-name></score-part></part-list>'
        '<part id="P1"><measure number="17"><attributes>'
        '<divisions>10080</divisions><time><beats>4</beats>'
        '<beat-type>4</beat-type></time><clef><sign>G</sign>'
        '<line>2</line></clef></attributes>' + ''.join(notes)
        + '<note><rest/><duration>30240</duration><type>half</type><dot/>'
          '</note></measure></part></score-partwise>')


def score_model():
    return {'notation_events': [
        {'id': f'own{i+1}', 'kind': 'note', 'staff': 'right',
         'voice': '1', 'measure': 17, 'beat': 64+i/3, 'chord': False,
         'tuplet_marks': (
             [{'type': 'start', 'number': '1', 'bracket': 'yes',
               'show_number': 'actual'}] if i == 0 else
             [{'type': 'stop', 'number': '1'}] if i == 2 else [])}
        for i in range(3)]}


def test_missing_tuplet_reengraves_exact_source_notes_with_verovio():
    # Empty source pages deliberately reproduce the absence of a full-page
    # native tuplet fragment. Recovery may not draw invented graphics.
    atlas = tuplet_fragments([], score_model(), notation_xml=score_xml())
    assert set(atlas) == {'own1|own2|own3'}
    group = atlas['own1|own2|own3']
    assert group['source'] == 'verovio-engraved-tuplet'
    assert group['origin'] == 'isolated-source-musicxml-verovio'
    assert group['note_ids'] == ['own1', 'own2', 'own3']
    assert group['number']['png_base64']
    assert group['bracket']['png_base64']
    assert group['span'] > 0


def test_recovery_cannot_replace_missing_or_corrupted_source_note_identity():
    source = ET.fromstring(score_xml())
    note = source.find(".//note[@id='own2']")
    assert note is not None
    note.set('id', 'different')
    damaged = ET.tostring(source, encoding='unicode')
    assert tuplet_fragments([], score_model(), notation_xml=damaged) == {}
    assert tuplet_fragments([], score_model(), notation_xml='') == {}


def test_hidden_tuplets_do_not_trigger_template_engraving(monkeypatch):
    import piano_teacher.notation.assets.tuplet_recovery as recovery
    original = score_model()
    original['notation_events'][0]['tuplet_marks'][0].update(
        bracket='no', show_number='none')
    def unexpected(*args, **kwargs):
        raise AssertionError('A hidden source ratio must never acquire artwork')
    monkeypatch.setattr(recovery, 'recover_missing_tuplets', unexpected)
    assert tuplet_fragments([], original, notation_xml=score_xml()) == {}


def test_recovered_group_keeps_the_selected_written_rhythm(monkeypatch):
    from piano_teacher.notation.assets import tuplet_recovery
    original = tuplet_recovery._isolated_score(
        ('own1', 'own2', 'own3'),
        tuplet_recovery._source_notes(score_xml())[0], 10080)
    assert original
    root = ET.fromstring(original)
    written = root.findall("part/measure/note")
    assert [n.get('id') for n in written] == ['own1', 'own2', 'own3']
    assert [n.findtext('duration') for n in written] == ['3360']*3
    assert [n.findtext('time-modification/actual-notes') for n in written] == ['3']*3
    assert [n.findtext('time-modification/normal-notes') for n in written] == ['2']*3
    assert [(n.get('type'), n.get('number')) for item in written
            for n in item.findall('notations/tuplet')] == [('start', '1'), ('stop', '1')]
