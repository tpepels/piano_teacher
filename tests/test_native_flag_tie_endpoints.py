"""Authentic flag-aware ties, retaining the ordinary half-note contours."""
import base64
from io import BytesIO
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image
import pytest

from piano_teacher.notation.assets import ties

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('eighth', '16th', '32nd', '64th', '128th')


@pytest.fixture(scope='module')
def atlas():
    return ties.tie_templates()


def test_complete_atlas_is_reused_from_warm_disk_cache(tmp_path, monkeypatch):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    cache = PreprocessingCache(tmp_path)
    monkeypatch.setattr(cache, 'enabled', True)
    cold = ties.tie_templates(cache)
    assert set(cold) == {'up', 'down'} | {f'{endpoint}_{kind}_{side}'
        for kind in KINDS for endpoint, side in (('start','above'), ('end','below'))}
    def unexpected_generation(*args):
        pytest.fail('A complete warm atlas must not regenerate engravings')
    monkeypatch.setattr(ties, '_generate', unexpected_generation)
    assert ties.tie_templates(cache) == cold


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('endpoint', ('start', 'end'))
def test_atlas_flagged_endpoint_has_authentic_clearance_and_head_metrics(atlas, kind, endpoint):
    side = 'above' if endpoint == 'start' else 'below'
    key = f'{endpoint}_{kind}_{side}'
    assert key in atlas, 'Flag-side tie needs authentic endpoint-aware engraving'
    item = atlas[key]
    assert item['source'] == 'verovio-engraved-tie'
    assert item['head_families'] == (['black', 'half'] if endpoint == 'start' else ['half', 'black'])
    assert len(item['head_centers']) == len(item['head_widths']) == 2
    left, _, width, _ = item['bounds']
    if endpoint == 'start':
        clearance = (left-item['head_centers'][0]-item['head_widths'][0]/2)/250
    else:
        clearance = (item['span']+item['head_centers'][1]-item['head_widths'][1]/2-left-width)/250
    assert (.4 if endpoint == 'start' else .1) < clearance < .9, 'Flag clearance must remain attached to its own head'
    with Image.open(BytesIO(base64.b64decode(item['png_base64']))) as image:
        alpha = np.asarray(image.convert('RGBA'))[:, :, 3]
    assert np.count_nonzero(alpha) > 30
    assert np.count_nonzero(alpha.sum(axis=0)) == alpha.shape[1], 'A tie contour must stay connected across its span'


@pytest.mark.parametrize('stem', ('up', 'down'))
def test_ordinary_atlas_is_exact_original_half_note_engraving(atlas, stem):
    """Independent old source sample; no new template builder supplies truth."""
    import cairosvg
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.svg import isolate
    from piano_teacher.notation.assets.svg_geometry import parse_svg_geometry

    xml = f'''<score-partwise version="4.0"><work><work-title> </work-title></work>
    <movement-title> </movement-title><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
    <part id="P1"><measure number="1"><attributes><divisions>10080</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="tie-first"><pitch><step>B</step><octave>4</octave></pitch><duration>20160</duration><type>half</type><stem>{stem}</stem>
    <tie type="start"/><notations><tied type="start"/></notations></note>
    <note id="tie-last"><pitch><step>B</step><octave>4</octave></pitch><duration>20160</duration><type>half</type><stem>{stem}</stem>
    <tie type="stop"/><notations><tied type="stop"/></notations></note></measure></part></score-partwise>'''
    toolkit = _create_verovio_toolkit(verovio)
    toolkit.setOptions({'inputFrom':'xml', 'scale':48, 'pageWidth':900, 'pageHeight':650,
        'adjustPageHeight':True, 'svgViewBox':True, 'svgBoundingBoxes':True, 'svgContentBoundingBoxes':True})
    assert toolkit.loadData(xml)
    svg = toolkit.renderToSVG(1)
    root = ET.fromstring(svg)
    group, = [n for n in root.iter() if 'tie' in n.get('class', '').split()
              and not {'bounding-box', 'content-bounding-box'} & set(n.get('class', '').split())]
    for parent in group.iter():
        for child in list(parent):
            if {'bounding-box', 'content-bounding-box'} & set(child.get('class', '').split()):
                parent.remove(child)
    picture = Image.open(BytesIO(cairosvg.svg2png(bytestring=isolate(root, group).encode(), output_width=1600))).convert('RGBA')
    alpha = picture.getchannel('A')
    crop = alpha.getbbox()
    assert np.array_equal(np.asarray(alpha.crop(crop)),
        np.asarray(Image.open(BytesIO(base64.b64decode(atlas[stem]['png_base64']))).getchannel('A')))
    geometry = parse_svg_geometry(svg)
    first_x, first_y, staff = geometry.elements['tie-first']
    last_x, _, _ = geometry.elements['tie-last']
    rails = geometry.staff_systems[staff]['staff_lines']
    scale = 250/((rails[1]-rails[0])*picture.height)
    left, top, right, bottom = crop
    assert atlas[stem]['bounds'] == pytest.approx([(left-first_x*picture.width)*scale,
        (top-first_y*picture.height)*scale, (right-left)*scale, (bottom-top)*scale])
    assert atlas[stem]['span'] == pytest.approx((last_x-first_x)*picture.width*scale)


HARNESS = r'''extends SceneTree

class FixedStaffLayout extends "res://notation/native/score_layout.gd":
    func staff_center(hand: String) -> float:
        return 110.0 if hand=="right" else 290.0

class LegacyTieObstacles extends "res://notation/native/fingering_obstacles.gd":
    var old_reservation := false
    func build(gap: float, bins: Dictionary, cell: float, play_from_beat: float = 0.0) -> void:
        if not old_reservation:
            super.build(gap,bins,cell,play_from_beat)
            return
        var pairs: Array = score_layout.tie_pairs
        score_layout.tie_pairs = []
        super.build(gap,bins,cell,play_from_beat)
        score_layout.tie_pairs = pairs
        # Exact former reservation, with the current authentic painter.
        for pair in pairs:
            var first: Dictionary = pair["first"]
            var last: Dictionary = pair["last"]
            var place: Dictionary = connector_geometry.tie_placement(first,last,float(first["beat"])*score_layout.timeline.pixels_per_beat,
                float(last["beat"])*score_layout.timeline.pixels_per_beat,gap)
            var info: Dictionary = score_layout.glyphs.tie_metadata[connector_geometry.tie_template_key(first,last,place,gap)]
            var box: Array = info["bounds"]
            var scale: float = (float(place["x1"])-float(place["x0"]))/float(info["span"])
            block(Rect2(float(place["x0"])+float(box[0])*scale,
                float(place["y"])+float(box[1])*gap/250.0,float(box[2])*scale,float(box[3])*gap/250.0),bins,cell)

class TieView extends "res://notation/native/view.gd":
    var spec: Dictionary
    var selected := ""
    var numbered := true
    var labels: Array = []
    var reservations: Array = []
    var reference := Rect2()
    func _init() -> void:
        layout = FixedStaffLayout.new(timeline,glyphs)
        annotations.obstacles = LegacyTieObstacles.new(layout,connector_geometry)
    func selector_checks() -> Dictionary:
        var leader := {"id":"leader","kind":"note","staff":"right","voice":"1","measure":1,"beat":0.0,
            "chord":false,"note_type":"eighth","stem":"up","spelling":{"step":"E","octave":4}}
        var child: Dictionary = leader.duplicate(true)
        child.merge({"id":"child","chord":true,"stem":"","spelling":{"step":"B","octave":4}},true)
        var last: Dictionary = child.duplicate(true)
        last.merge({"id":"stop","chord":false,"note_type":"half","beat":2.0},true)
        ordered_events = [leader,child,last]
        chord_members = {"leader":[leader,child]}
        beamed_note_ids = {}
        beam_stem_up_by_note = {}
        var checks := {"chord_child":_tie_template_key(child,last,{"down":false},21.875)}
        beamed_note_ids = {"leader":true}
        checks["beamed_chord_child"] = _tie_template_key(child,last,{"down":false},21.875)
        beamed_note_ids = {}
        beam_stem_up_by_note = {"leader":true}
        checks["beam_stem_owned_child"] = _tie_template_key(child,last,{"down":false},21.875)
        # At the middle tone the actual leader's beam direction determines
        # the bow, even when the child has no individual map entry.
        leader["stem"] = ""
        leader["spelling"] = {"step":"G","octave":4}
        var top: Dictionary = child.duplicate(true)
        top.merge({"id":"top","spelling":{"step":"D","octave":5}},true)
        chord_members = {"leader":[leader,child,top]}
        ordered_events = [leader,child,top,last]
        checks["middle_tone_bow_down"] = _tie_bow_down(child,last,21.875)
        return checks
    func _draw() -> void:
        annotations.obstacles.old_reservation = bool(spec.get("old_reservation",false))
        var gap: float = float(spec["gap"])
        draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
        for center in [110.0,290.0]:
            for rail in range(-2,3):
                draw_line(Vector2(0,center+rail*gap),Vector2(size.x,center+rail*gap),Color(NOTE_INK,.34),1.0)
        var first := {"id":"first","kind":"note","note_type":spec["first"],"stem":spec["stem"],"staff":"right","hand":"right",
            "spelling":{"step":"B","alter":0,"octave":4},"measure":1,"beat":0.0,"chord":false,
            "tied_marks":[[["type","start"],["placement",spec["side"]]]]}
        var last := first.duplicate(true)
        last.merge({"id":"last","note_type":spec["last"],"beat":2.0,
            "tied_marks":[[["type","stop"],["placement",spec["side"]]]]},true)
        first["beat"] = 100.0/timeline.pixels_per_beat
        last["beat"] = 280.0/timeline.pixels_per_beat
        var measure := {"number":1,"start_beat":0.0,"end_beat":20.0,
            "clefs":{"right":{"sign":"G","line":2,"octave_change":0}}}
        timeline.measures = [measure]
        measure_by_number = {1:measure}
        ordered_events = [first,last]
        var up: bool = spec["stem"]=="up"
        beamed_note_ids = {"first":true} if spec.get("beamed",false) else {}
        beam_stem_up_by_note = {"first":up} if spec.get("beamed",false) else {}
        if spec.get("beamed",false):
            glyphs.paint(self,"head_black",100.0,110.0,gap,NOTE_INK,true)
            glyphs.paint_note_stem(self,spec["first"],up,100.0,110.0,110.0-3.5*gap,gap,NOTE_INK)
        else:
            glyphs.paint_note(self,spec["first"],up,100.0,110.0,gap,NOTE_INK)
        glyphs.paint_note(self,spec["last"],up,280.0,110.0,gap,NOTE_INK)
        var place: Dictionary = _tie_placement(first,last,100.0,280.0,gap)
        selected = _tie_template_key(first,last,place,gap)
        _paint_tie_contour(first,last,place,gap)
        labels.clear()
        reservations.clear()
        if spec.get("fingering",false):
            first["is_attack"] = true
            first["fingering"] = {"source_id":"authored-first","hand":"right","finger":3,"origin":"authored",
                "placement":{"default_x":float(spec.get("hint_x",20.0)),"default_y":-18.0}}
            tie_pairs = [{"first":first,"last":last}]
            expression_note_index = {"first":first,"last":last}
            _layout_fingerings(gap)
            var bins: Dictionary = {}
            _fingering_obstacles(gap,bins,64.0)
            for entries in bins.values():
                for rect in entries:
                    reservations.append([rect.position.x,rect.position.y,rect.size.x,rect.size.y])
            fingering_annotations_enabled = true
            drawn_fingerings.clear()
            if numbered:
                _paint_fingerings(0.0,0.0,gap)
            for item in drawn_fingerings:
                var rect: Rect2 = item["rect"]
                var head: Vector2 = item["head"]
                labels.append({"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],
                    "head":[head.x,head.y],"finger":item["finger"],"font_size":item["font_size"],
                    "orientation":item["orientation"],"event_ids":item["event_ids"]})
            var font_size: int = clampi(roundi(gap*.75),11,16)
            var metrics: Dictionary = _fingering_metrics(font_size)
            reference = Rect2(Vector2(360,340),metrics["cell"])
            draw_string(ThemeDB.fallback_font,reference.position+Vector2(1,ThemeDB.fallback_font.get_ascent(font_size)),
                "3",HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,NOTE_INK)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var reports: Array = []
    for spec in fixture["cases"]:
        var viewport := SubViewport.new()
        viewport.size = Vector2i(420,370)
        viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        root.add_child(viewport)
        var view := TieView.new()
        view.spec = spec
        view.size = Vector2(420,370)
        viewport.add_child(view)
        assert(view.glyphs.load_font(fixture["glyphs"]))
        assert(view.glyphs.load_note_templates(fixture["notes"]))
        assert(view.glyphs.load_tie_templates(fixture["ties"]))
        view.queue_redraw()
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        viewport.get_texture().get_image().save_png(args[1].path_join(spec["name"]+".png"))
        var row := {"name":spec["name"],"selected":view.selected}
        if spec.get("fingering",false):
            row["labels"] = view.labels.duplicate(true)
            row["reservations"] = view.reservations.duplicate(true)
            row["issues"] = view.fingering_placement_issues.duplicate(true)
            row["reference"] = [view.reference.position.x,view.reference.position.y,view.reference.size.x,view.reference.size.y]
            view.numbered = false
            view.queue_redraw()
            await process_frame
            await process_frame
            await RenderingServer.frame_post_draw
            viewport.get_texture().get_image().save_png(args[1].path_join(spec["name"]+"-base.png"))
        row["selector_checks"] = view.selector_checks()
        reports.append(row)
        viewport.queue_free()
        await process_frame
    FileAccess.open(args[1].path_join("report.json"),FileAccess.WRITE).store_string(JSON.stringify(reports))
    quit()
'''


@pytest.fixture(scope='module')
def endpoint_frames(tmp_path_factory, atlas):
    from piano_teacher.notation.assets.glyphs import native_glyphs
    from piano_teacher.notation.assets.notes import note_templates
    from test_native_fingering import _godot, _run_godot
    folder = tmp_path_factory.mktemp('native-flag-tie-endpoints')
    cases = []
    for kind in KINDS:
        for endpoint, stem, side in (('start','up','above'), ('end','down','below')):
            cases.append(dict(name=f'{endpoint}-{kind}', first=kind if endpoint=='start' else 'half',
                last=kind if endpoint=='end' else 'half', stem=stem, side=side, gap=21.875))
    cases.extend((dict(name='beamed-above',first='eighth',last='half',stem='up',side='above',gap=21.875,beamed=True),
                  dict(name='opposite-below',first='eighth',last='half',stem='up',side='below',gap=21.875)))
    for ordinary in (False, True):
        for old in (False, True):
            cases.append(dict(name=('ordinary' if ordinary else 'flagged')+'-fingering'+('-old' if old else ''),
                first='half' if ordinary else 'eighth',last='half',stem='down' if ordinary else 'up',side='above',
                gap=21.875,fingering=True,old_reservation=old,hint_x=14.0 if ordinary else 20.0))
    payload = folder/'fixture.json'
    payload.write_text(json.dumps(dict(cases=cases,glyphs=native_glyphs(),notes=note_templates(),ties=atlas)))
    script = folder/'flag-tie-endpoints.gd'
    script.write_text(HARNESS)
    result = _run_godot([*_godot(),'--path',str(ROOT/'godot'),'--audio-driver','Dummy',
        '--rendering-method','gl_compatibility','--script',str(script),'--',str(payload),str(folder)],timeout=60)
    output = result.stdout+result.stderr
    (folder/'godot.log').write_text(output)
    assert result.returncode==0 and 'SCRIPT ERROR' not in output, output
    reports = {r['name']:r for r in json.loads((folder/'report.json').read_text())}
    return folder, cases, reports


@pytest.mark.parametrize('name', [f'{endpoint}-{kind}' for kind in KINDS for endpoint in ('start','end')]
                         + ['beamed-above','opposite-below'])
def test_native_flagged_start_and_end_are_independently_connected(endpoint_frames, name):
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_curve, _connector_head
    folder, cases, reports = endpoint_frames
    for case in [case for case in cases if case['name']==name]:
        # Literal authored endpoint positions are test inputs. Actual head
        # contours/rails come from PNG and the independent external font.
        xml = f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name></score-part></part-list>
        <part id="RH"><measure number="1"><attributes><divisions>4</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
        <note id="first"><pitch><step>B</step><octave>4</octave></pitch><duration>8</duration><type>{case['first']}</type><tie type="start"/></note>
        <note id="last"><pitch><step>B</step><octave>4</octave></pitch><duration>8</duration><type>{case['last']}</type><tie type="stop"/></note>
        </measure></part></score-partwise>'''
        written = read_written_score(xml)
        notes = [n for n in written.symbols if n['kind']=='note']
        picture = Image.open(folder/(case['name']+'.png')).convert('RGB')
        heads = [_connector_head(picture,written,n,x) for n,x in zip(notes,(100.,280.))]
        assert all(heads), case
        proof = _connector_curve(picture,heads,'tie',case['side'])
        assert proof['status']=='verified', (case,proof)
        if case['name']=='beamed-above':
            assert reports[case['name']]['selected']=='down', 'A beamed eighth has no visible flag to clear'
        elif case['name']=='opposite-below':
            assert reports[case['name']]['selected']=='up', 'Explicit placement away from the flag keeps the ordinary contour'
        else:
            endpoint, kind = case['name'].split('-',1)
            assert reports[case['name']]['selected']==f'{endpoint}_{kind}_{case["side"]}'


def _number_clearance(folder, name, row):
    from PIL import ImageFilter
    base = np.asarray(Image.open(folder/(name+'-base.png')).convert('RGB')).astype(int)
    numbered = np.asarray(Image.open(folder/(name+'.png')).convert('RGB')).astype(int)
    assert not row['issues'] and len(row['labels'])==1, row
    label, = row['labels']
    x,y,w,h = map(int,label['rect'])
    rx,ry,rw,rh = map(int,row['reference'])
    reference = base[ry:ry+rh,rx:rx+rw].max(axis=2)>100
    assert reference.sum()>12
    changed = np.max(np.abs(numbered-base),axis=2)>12
    actual = changed[y:y+h,x:x+w] & (numbered[y:y+h,x:x+w].max(axis=2)>100)
    assert actual.shape==reference.shape
    assert (actual & reference).sum()/max(1,(actual | reference).sum())>.8
    ink = np.zeros(changed.shape,dtype=np.uint8)
    ink[y:y+h,x:x+w] = reference*255
    clearance = np.asarray(Image.fromarray(ink).filter(ImageFilter.MaxFilter(5)))>0
    assert not (clearance & (base.max(axis=2)>145)).any(), 'Numeral touches photographed musical ink'


@pytest.mark.parametrize('kind', ('flagged','ordinary'))
def test_fingering_clears_actual_fixed_margin_tie(endpoint_frames, kind):
    folder, _, reports = endpoint_frames
    name = kind+'-fingering'
    _number_clearance(folder,name,reports[name])


def test_old_affine_tie_reservation_fails_actual_number_clearance(endpoint_frames):
    folder, _, reports = endpoint_frames
    name = 'ordinary-fingering-old'
    with pytest.raises(AssertionError,match='Numeral touches photographed musical ink'):
        _number_clearance(folder,name,reports[name])


@pytest.mark.parametrize('kind', ('flagged','ordinary'))
def test_actual_tie_ink_is_reserved_and_old_affine_box_leaves_it_unreserved(endpoint_frames, kind):
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_curve, _connector_head
    folder, cases, reports = endpoint_frames
    for old in (False,True):
        name = kind+'-fingering'+('-old' if old else '')
        case = next(case for case in cases if case['name']==name)
        xml = f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name></score-part></part-list>
        <part id="RH"><measure number="1"><attributes><divisions>4</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
        <note id="first"><pitch><step>B</step><octave>4</octave></pitch><duration>8</duration><type>{case['first']}</type><tie type="start"/></note>
        <note id="last"><pitch><step>B</step><octave>4</octave></pitch><duration>8</duration><type>{case['last']}</type><tie type="stop"/></note>
        </measure></part></score-partwise>'''
        written = read_written_score(xml)
        notes = [n for n in written.symbols if n['kind']=='note']
        picture = Image.open(folder/(name+'-base.png')).convert('RGB')
        heads = [_connector_head(picture,written,n,x) for n,x in zip(notes,(100.,280.))]
        proof = _connector_curve(picture,heads,'tie','above')
        assert proof['status']=='verified', proof
        rectangles = reports[name]['reservations']
        uncovered = [(x,y) for y,left,right in proof['pixel_runs'] for x in range(left,right)
                     if not any(rx<=x+.5<=rx+rw and ry<=y+.5<=ry+rh for rx,ry,rw,rh in rectangles)]
        if old:
            assert len(uncovered)>20, 'The former box must leave genuine photographed tie ink unreserved'
        else:
            assert not uncovered, 'Every photographed tie pixel needs a collision reservation'


def test_chord_children_inherit_the_visible_leader_and_beam_ownership(endpoint_frames):
    _, _, reports = endpoint_frames
    checks = reports['start-eighth']['selector_checks']
    assert checks == dict(chord_child='start_eighth_above',beamed_chord_child='down',
                          beam_stem_owned_child='down',middle_tone_bow_down=True)
