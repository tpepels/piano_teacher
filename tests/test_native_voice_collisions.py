"""Voice columns are read from authentic ink, never native layout telemetry."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
from test_polyphonic_stem_pixels import source

ROOT=Path(__file__).resolve().parents[1]


def collision_source(kind):
    groups=([(('C',5),('E',5)),(('C',5),('G',5))] if kind=='mixed-chords'
            else [(('C',5),),(('D',5),),(('E',5),)] if kind=='three-voice-neighbors'
            else [(('C',5),),(('C',5),),(('G',5),)] if kind=='unrelated-third-voice'
            else [(('C',5),),(('C',5),)])
    # The three-voice specimen deliberately has NO explicit source stems:
    # it exercises the renderer's new default selection, not overrides.
    explicit=([] if kind=='three-voice-neighbors' else
              ['up','up'] if kind=='same-direction' else
              ['up','down','up'][:len(groups)])
    tree=ET.fromstring(source(groups,explicit))
    if kind in {'mixed-chords','beamed-overlap','tuplet-overlap','unrelated-third-voice'}:
        for note in tree.findall('.//note'):
            if note.findtext('voice')=='1':
                note.find('duration').text='2'
                note.find('type').text='half'
                for dot in note.findall('dot'):note.remove(dot)
    if kind in {'beamed-overlap','tuplet-overlap'}:
        division=6 if kind=='tuplet-overlap' else 2
        tree.find('.//divisions').text=str(division)
        for duration in tree.findall('.//duration'):
            duration.text=str(division*int(duration.text))
        measure=tree.find('.//measure')
        first=next(n for n in measure.findall('note')
                   if n.findtext('voice')=='2' and n.find('pitch') is not None)
        first.find('duration').text='2' if kind=='tuplet-overlap' else '1'
        first.find('type').text='eighth'
        ET.SubElement(first,'beam',number='1').text='begin'
        second=ET.fromstring('<note id="v2next"><pitch><step>D</step><octave>5</octave></pitch>'
            '<duration>1</duration><voice>2</voice><type>eighth</type><stem>down</stem>'
            '<beam number="1">end</beam></note>')
        measure.insert(list(measure).index(first)+1,second)
        if kind=='tuplet-overlap':
            # Repeated pitches isolate endpoint reflow from the separate
            # sloped-beam/bracket bounding-box interference limitation.
            second.find('pitch/step').text='C'
            second.find('duration').text='2'
            second.find('beam').text='continue'
            third=ET.fromstring('<note id="v2last"><pitch><step>C</step><octave>5</octave></pitch>'
                '<duration>2</duration><voice>2</voice><type>eighth</type><stem>down</stem>'
                '<beam number="1">end</beam></note>')
            measure.insert(list(measure).index(second)+1,third)
            for note in (first,second,third):
                mod=ET.Element('time-modification')
                note.insert(list(note).index(note.find('stem')),mod)
                ET.SubElement(mod,'actual-notes').text='3'
                ET.SubElement(mod,'normal-notes').text='2'
                ET.SubElement(mod,'normal-type').text='eighth'
            ET.SubElement(ET.SubElement(first,'notations'),'tuplet',type='start',number='1',bracket='yes',placement='below')
            ET.SubElement(ET.SubElement(third,'notations'),'tuplet',type='stop',number='1')
    return ET.tostring(tree,encoding='unicode')


@pytest.fixture(scope='module',params=['mixed-chords','same-shape-shared','same-direction','beamed-overlap','unrelated-third-voice','three-voice-neighbors','tuplet-overlap'])
def actual_collision(request,tmp_path_factory):
    binary=shutil.which('godot') or shutil.which('godot4')
    if not binary or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        pytest.skip('Actual native framebuffer needs Godot and a desktop')
    from scripts.check_native_verovio_overlay import AuditCase,fixture
    folder=tmp_path_factory.mktemp(request.param)
    xml=collision_source(request.param)
    score=folder/'source.musicxml';score.write_text(xml)
    data,_=fixture(AuditCase('voice-collision',str(score),1,1,'right'))
    # Bind reference IDs to the source passed to the independent reader.
    # The application's derived lesson XML intentionally has different IDs.
    import verovio
    reference=verovio.toolkit()
    reference.setOptions(dict(font='Leipzig',breaks='none',header='none',footer='none',
        svgViewBox=True,svgBoundingBoxes=True,svgContentBoundingBoxes=True))
    assert reference.loadData(xml)
    for index in range(reference.getPageCount()):
        (folder/f'verovio-{index}.svg').write_text(reference.renderToSVG(index+1))
    clocks=([0,.5] if request.param=='beamed-overlap' else
            [0,1/3,2/3,1] if request.param=='tuplet-overlap' else [0])
    data.update(sample_beats=clocks,phase3_full=True)
    payload=folder/'fixture.json';payload.write_text(json.dumps(data))
    result=subprocess.run([binary,'--path',str(ROOT/'godot'),'--audio-driver','Dummy',
        '--rendering-method','gl_compatibility','--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'),'--',str(payload),str(folder)],
        capture_output=True,text=True,timeout=90)
    (folder/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    payload.unlink()
    (folder/'bounds-fixture.json').write_text(json.dumps(data))
    return request.param,folder,xml


def test_actual_voice_columns_have_distinct_required_shafts(actual_collision):
    kind,folder,xml=actual_collision
    report=verify_note_feature_pixels(xml,folder,hand='right')
    rows=[r for r in report['measured'] if r['beat']==0]
    (folder/'proof.json').write_text(json.dumps(report,indent=2))
    assert len(rows)==(4 if kind=='mixed-chords' else 3 if kind in {'unrelated-third-voice','three-voice-neighbors'} else 2)
    assert all(r['features']['stem']['status']=='verified' for r in rows),rows
    shafts={r['features']['stem']['evidence']['physical_shaft_id'] for r in rows}
    assert len(shafts)==(3 if kind in {'unrelated-third-voice','three-voice-neighbors'} else 2),rows
    from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
    pitches=verify_all_notehead_pixels(xml,folder,hand='right')
    onset=[r for r in pitches['measured'] if r['beat']==0]
    if kind!='same-shape-shared':
        assert all(r['status']=='verified' for r in onset),onset
    if kind=='beamed-overlap':
        from piano_teacher.notation.connector_pixels import verify_beam_pixels
        beams=verify_beam_pixels(xml,folder,hand='right')
        assert beams['coverage']['expected']==beams['coverage']['verified']==1,beams
    if kind=='tuplet-overlap':
        from piano_teacher.notation.connector_pixels import verify_tuplet_pixels
        tuplets=verify_tuplet_pixels(xml,folder,hand='right')
        assert tuplets['coverage']['expected']==tuplets['coverage']['verified']==1,tuplets
    heads=registered_heads(xml,folder)
    assert len(heads)==len(rows)
    # Inspect independently registered contours, not native head coordinates.
    if kind=='same-shape-shared':
        a,b=heads.values()
        assert a['support']==b['support']
        assert a['shared_stem_direction']!=b['shared_stem_direction']
    else:
        values=list(heads.values())
        assert all(a['support'].isdisjoint(b['support'])
                   for i,a in enumerate(values) for b in values[:i])


def registered_heads(xml,folder):
    from piano_teacher.notation.head_registration import register_noteheads
    from piano_teacher.notation.reference_font import feature_glyphs
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.pixel_proof import detect_staff_lines
    from piano_teacher.notation.raster_matching import photographed_playhead_columns
    from piano_teacher.notation.pixel_ink import bright
    written=read_written_score(xml)
    notes=[n for n in written.symbols if n['kind']=='note' and n['beat']==0]
    with Image.open(folder/'native-0.00000.png') as raw:image=raw.convert('RGB')
    heads,_=register_noteheads(bright(image),detect_staff_lines(image),written,notes,feature_glyphs(),
                      occlusion_columns=photographed_playhead_columns(image))
    return heads


def test_erasing_one_voice_shaft_cannot_borrow_the_other(actual_collision,tmp_path):
    _,folder,xml=actual_collision
    report=verify_note_feature_pixels(xml,folder,hand='right')
    target=next(r for r in report['measured'] if r['beat']==0 and r['voice']=='1')
    stem=target['features']['stem']
    assert stem['status']=='verified',stem
    shutil.copytree(folder,tmp_path,dirs_exist_ok=True)
    frame=tmp_path/'native-0.00000.png'
    with Image.open(frame) as raw:image=raw.convert('RGB')
    x0,top,x1,bottom=stem['evidence']['bbox']
    y0=top+15 if stem['evidence']['direction']=='up' else bottom-25
    ImageDraw.Draw(image).rectangle((x0,y0,x1-1,y0+10),fill=image.getpixel((0,0)))
    image.save(frame)
    erased=verify_note_feature_pixels(xml,tmp_path,hand='right')
    damaged=[r for r in erased['measured'] if r['beat']==0 and r['voice']=='1']
    assert all(r['features']['stem']['status']!='verified' for r in damaged),damaged


def test_erased_head_cannot_be_replaced_by_the_other_voice(actual_collision,tmp_path):
    _,folder,xml=actual_collision
    heads=registered_heads(xml,folder)
    assert heads
    from piano_teacher.notation.proof import read_written_score
    sid=next(n['source']['id'] for n in read_written_score(xml).symbols
             if n['kind']=='note' and n['beat']==0 and n['voice']=='1')
    target=heads[sid]
    shutil.copytree(folder,tmp_path,dirs_exist_ok=True)
    frame=tmp_path/'native-0.00000.png'
    with Image.open(frame) as raw:image=raw.convert('RGB')
    x0,y0,x1,y1=target['bbox']
    ImageDraw.Draw(image).rectangle((x0,y0,x1-1,y1-1),fill=image.getpixel((0,0)))
    image.save(frame)
    erased=verify_note_feature_pixels(xml,tmp_path,hand='right')
    damaged=[r for r in erased['measured'] if r['beat']==0 and r['voice']=='1']
    assert all(r['features']['stem']['status']!='verified' for r in damaged),damaged


def test_sprite_spacing_bounds_follow_the_complete_shifted_voice(actual_collision):
    _,folder,_=actual_collision
    binary=shutil.which('godot') or shutil.which('godot4')
    result=subprocess.run([binary,'--headless','--path',str(ROOT/'godot'),'--script',
        str(ROOT/'tests/godot/native_voice_bounds.gd'),'--',str(folder/'bounds-fixture.json')],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'VOICE_SPRITE_BOUNDS:' in result.stdout,result.stdout+result.stderr
