"""Phase 2 image-space symbol proof using independently read MusicXML and ink.

This module never reads Godot's reported coordinates to decide where or
which symbol to accept. It reads actual native PNG pixels, recovers the five-
line staves, and checks expected glyph silhouettes (against original Verovio
font outlines) and connective ink from source beam/tie declarations.
A semantic preflight rejects symbols lost before rendering.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from functools import lru_cache
from pathlib import Path
from io import BytesIO
import json

import cairosvg
import numpy as np
from PIL import Image

from .proof import read_written_score
from .pixel_proof import detect_staff_lines, expected_y, RasterStaff

PLAYHEAD = .42
REST_TYPES = ("whole","half","quarter","eighth","16th","32nd","64th","128th")
ACCIDENTAL_TYPES = ("flat","natural","sharp","double-flat","double-sharp")
ACCIDENTAL_GLYPH = {"flat":"acc_flat","natural":"acc_natural","sharp":"acc_sharp",
                    "double-flat":"acc_double_flat","double-sharp":"acc_double_sharp"}


def bright(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    # Native score ink is pale; native staff rules are dim and the mint
    # playhead has too little red. This does not consult Godot telemetry.
    return ((rgb[:,:,0] > 155) & (rgb[:,:,1] > 160) & (rgb[:,:,2] > 150))


@lru_cache(maxsize=256)
def _outline(svg: str, width: int, height: int) -> np.ndarray:
    png = cairosvg.svg2png(bytestring=svg.encode(),
                          output_width=width, output_height=height)
    return np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3] > 96


def _match_glyph(pixels: np.ndarray, glyph: dict, gap: float,
                 origin_x: float, origin_y: float,
                 *, centered: bool, dxs, dys) -> float:
    bounds = glyph["bounds"]
    width = max(1,round(bounds[2]*gap/250))
    height = max(1,round(bounds[3]*gap/250))
    template = _outline(glyph["svg"], width, height)
    # Godot's font atlas uses source MusicXML font-space glyph bounds.
    # Its actual placement is unknown; search nearby for the best PNG fit.
    left = origin_x - (bounds[2]*gap/250/2 if centered else -bounds[0]*gap/250)
    top = origin_y + bounds[1]*gap/250
    expected_count = int(template.sum())
    best = 0.0
    for dx in dxs:
        x = round(left + dx)
        if x < 0 or x+width >= pixels.shape[1]:
            continue
        for dy in dys:
            y = round(top+dy)
            if y < 0 or y+height >= pixels.shape[0]:
                continue
            block = pixels[y:y+height,x:x+width]
            observed_count = int(block.sum())
            intersection = int(np.count_nonzero(template & block))
            dice = 2*intersection/(expected_count+observed_count+1e-9)
            best = max(best,dice)
    return best


def classify_symbol(image: Image.Image, fonts: dict, names: tuple[str,...],
                    x: float, y: float, gap: float,
                    *, centered: bool, dxs, dys) -> list[tuple[str,float]]:
    pixels = bright(image)
    return sorted(((name,round(_match_glyph(
        pixels, fonts[name], gap, x, y, centered=centered, dxs=dxs, dys=dys),4))
        for name in names), key=lambda p:p[1],reverse=True)


def _staff_clefs(reference):
    result = {}
    for _m,hand,sign,line,octave in reference.clefs:
        spec = sign,line,octave
        if hand in result and result[hand] != spec:
            raise ValueError("Mixed clefs require new image-space test positions")
        result[hand] = spec
    return result


def _check_match(label: str, expected: str, ranked, errors, records):
    first,score = ranked[0]
    second_score = ranked[1][1] if len(ranked)>1 else 0.0
    records.append({"symbol":label,"expected":expected,
                    "observed":first,"score":score,"runner_up":second_score})
    if first != expected or score < .72 or score-second_score < .05:
        errors.append(f"{label}: expected {expected}, image identified {first} "
                      f"({score:.3f} vs runner-up {second_score:.3f})")


def prove_rest_ink(original_xml: str, generated_xml: str,
                   folder: Path) -> dict:
    source = read_written_score(original_xml)
    generated = read_written_score(generated_xml)
    expected = [e for e in source.symbols
                if e["kind"]=="rest" and e["staff"]=="right" and e["visible"]]
    actual = [e for e in generated.symbols
              if e["kind"]=="rest" and e["staff"]=="right" and e["visible"]]
    sig = lambda e: (round(float(e["beat"]),6),e["note_type"],int(e["dots"]))
    errors = []
    if Counter(map(sig,expected)) != Counter(map(sig,actual)):
        errors.append("Source RH rest inventory diverges from generated MusicXML")
    fonts = json.loads((folder/"fixture.json").read_text())["assets"]["native_glyphs"]
    records = []
    for event in expected:
        beat=float(event["beat"])
        frame=folder/f"native-{beat:.2f}.png"
        if not frame.is_file():
            errors.append(f"Rest at beat {beat}: screenshot missing")
            continue
        image=Image.open(frame)
        staff=detect_staff_lines(image)["right"]
        y=(staff.lines[0]+staff.lines[-1])/2
        x=round(image.width*PLAYHEAD)
        ranked=classify_symbol(image,fonts,tuple("rest_"+t for t in REST_TYPES),
               x,y,staff.gap,centered=True,dxs=range(-3,4),
               dys=range(-30,31,2))
        _check_match(f"rest beat {beat}", "rest_"+str(event["note_type"]),
                     ranked,errors,records)
    if not expected:
        errors.append("Source rest specimen has no rest symbols")
    return {"passed":not errors,"source_rests":len(expected),
            "matched":records,"errors":errors}


def prove_accidental_ink(original_xml: str, generated_xml: str,
                         folder: Path) -> dict:
    source=read_written_score(original_xml)
    generated=read_written_score(generated_xml)
    expected=[e for e in source.symbols if e["accidental"] and e["staff"]=="right"]
    source_sig=lambda e:(round(float(e["beat"]),6),e["spelling"],e["accidental"])
    gen_acc={source_sig(e) for e in generated.symbols if e["accidental"] and e["staff"]=="right"}
    errors=[]
    if Counter(map(source_sig,expected)) != Counter(
            source_sig(e) for e in generated.symbols if e["accidental"] and e["staff"]=="right"):
        errors.append("Written accidental semantics differ from generated notation")
    clefs=_staff_clefs(source)
    fonts=json.loads((folder/"fixture.json").read_text())["assets"]["native_glyphs"]
    records=[]
    for e in expected:
        beat=float(e["beat"])
        frame=folder/f"native-{beat:.2f}.png"
        if not frame.is_file():
            errors.append(f"Accidental at beat {beat}: screenshot missing")
            continue
        image=Image.open(frame)
        staff=detect_staff_lines(image)["right"]
        y=expected_y(staff,e["spelling"],clefs["right"])
        x=round(image.width*PLAYHEAD)-staff.gap*1.15
        ranked=classify_symbol(image,fonts,tuple(ACCIDENTAL_GLYPH.values()),
               x,y,staff.gap,centered=True,dxs=range(-9,10),
               dys=range(-10,11,2))
        expected_glyph=ACCIDENTAL_GLYPH.get(e["accidental"])
        if expected_glyph is None:
            errors.append(f"Unsupported source accidental {e['accidental']}")
        else:
            _check_match(f"accidental beat {beat}",expected_glyph,ranked,errors,records)
    if not expected:
        errors.append("No explicit accidentals in original specimen")
    return {"passed":not errors,"source_accidentals":len(expected),
            "matched":records,"errors":errors}


def bridge_ink(image: Image.Image, row_range: range, *, x_pad: int=5) -> int:
    mask=bright(image)
    x=round(image.width*PLAYHEAD)
    # A beam/tie crosses the *middle* of a note interval: isolated flags
    # and note stems at endpoints cannot satisfy the full-width bridge.
    horizontal=mask[max(0,row_range.start):min(image.height,row_range.stop),
                    x+x_pad:x+x_pad+9]
    if horizontal.size==0:
        return 0
    return int(max(horizontal.sum(axis=1),default=0))


def prove_tie_ink(original_xml: str, generated_xml: str,folder: Path) -> dict:
    source=read_written_score(original_xml)
    generated=read_written_score(generated_xml)
    starts=[e for e in source.symbols if e["tie_start"] and e["staff"]=="right"]
    if not starts or sum(e["tie_stop"] for e in generated.symbols)==0:
        return {"passed":False,"errors":["Source tie missing from generated notation"]}
    # Midpoint of a source tie extending across the barline: test actual
    # tapered white arc, separate from both notehead images.
    frame=folder/"native-2.00.png"
    image=Image.open(frame)
    staff=detect_staff_lines(image)["right"]
    clef=_staff_clefs(source)["right"]
    y=expected_y(staff,starts[0]["spelling"],clef)
    ys=range(round(y+staff.gap*.35),round(y+staff.gap*1.5))
    bridge=bridge_ink(image,ys)
    errors=[] if bridge>=7 else [f"Source tie: missing curved bridge ink at midpoint (max {bridge})"]
    return {"passed":not errors,"ties":len(starts),"bridge_pixels":bridge,"errors":errors}


def prove_beam_ink(original_xml: str, generated_xml: str,folder: Path) -> dict:
    from xml.etree import ElementTree as ET
    source=ET.fromstring(original_xml)
    generated=ET.fromstring(generated_xml)
    get_marks=lambda root:[(e.findtext("type"),b.text) for e in root.findall(".//part[@id='RH']//note")
                           for b in e.findall("beam")]
    sm=get_marks(source)
    gm=get_marks(generated)
    errors=[]
    if not sm or sm!=gm:
        errors.append(f"Source beam structure was not preserved: original={len(sm)} generated={len(gm)}")
    # Verify actual bridges in six explicitly connected eighth-note
    # intervals, excluding the two unconnected inter-group boundaries.
    positives=(.25,.75,1.25,2.25,2.75,3.25)
    source_score=read_written_score(original_xml)
    clef=_staff_clefs(source_score)["right"]
    notes={float(n["beat"]):n for n in source_score.symbols
           if n["kind"]=="note" and n["staff"]=="right"}
    checks=[]
    for at in positives:
        a=notes.get(at-.25);b=notes.get(at+.25)
        if a is None or b is None:
            errors.append(f"Expected beamed source pair missing at {at}")
            continue
        image=Image.open(folder/f"native-{at:.2f}.png")
        staff=detect_staff_lines(image)["right"]
        ya=expected_y(staff,a["spelling"],clef)
        yb=expected_y(staff,b["spelling"],clef)
        top=min(ya,yb)
        band=range(round(top-5.0*staff.gap),round(top-1.3*staff.gap))
        bridge=bridge_ink(image,band)
        checks.append({"midpoint":at,"bright_pixels":bridge})
        if bridge < 7:
            errors.append(f"Beam between {at-.25} and {at+.25} not found in native pixels")
    return {"passed":not errors,"beamed_pairs":len(checks),
            "bridges":checks,"errors":errors}


def _match_note_template(pixels: np.ndarray, entry: dict, gap: float,
                         x: float, y: float) -> float:
    import base64
    bounds=entry["bounds"]
    width=max(1,round(bounds[2]*gap/250))
    height=max(1,round(bounds[3]*gap/250))
    rgba=Image.open(BytesIO(base64.b64decode(entry["png_base64"]))).convert("RGBA")
    rgba=rgba.resize((width,height),Image.Resampling.BILINEAR)
    template=np.asarray(rgba)[:,:,3]>96
    count=int(template.sum())
    best=0.0
    for dx in range(-4,5):
        for dy in range(-4,5):
            left=round(x+bounds[0]*gap/250+dx)
            top=round(y+bounds[1]*gap/250+dy)
            if left<0 or top<0 or left+width>=pixels.shape[1] or top+height>=pixels.shape[0]:
                continue
            crop=pixels[top:top+height,left:left+width]
            score=2*int(np.count_nonzero(crop&template))/(count+int(crop.sum())+1e-9)
            best=max(score,best)
    return best


def prove_note_rhythm_ink(original_xml: str, generated_xml: str,folder: Path) -> dict:
    """Check whole/half/quarter/eighth silhouettes and augmentation dots."""
    src=read_written_score(original_xml)
    gen=read_written_score(generated_xml)
    expected=[e for e in src.symbols if e["kind"]=="note" and e["staff"]=="right"]
    actual=[e for e in gen.symbols if e["kind"]=="note" and e["staff"]=="right"]
    sig=lambda e:(round(float(e["beat"]),6), e["note_type"],e["dots"],e["spelling"])
    errors=[]
    if Counter(map(sig,expected))!=Counter(map(sig,actual)):
        errors.append("Original written note types/dots/spelling diverge from generated score")
    if not expected:
        errors.append("No source note rhythms exercised")
    atlas=json.loads((folder/"fixture.json").read_text())["assets"]
    note_templates=atlas["native_note_templates"]
    fonts=atlas["native_glyphs"]
    clef=_staff_clefs(src)["right"]
    candidate_names=("whole","half_up","quarter_up","eighth_up","16th_up")
    records=[]
    dots_checked=0
    for item in expected:
        beat=float(item["beat"])
        image_path=folder/f"native-{beat:.2f}.png"
        if not image_path.exists():
            errors.append(f"Rhythm beat {beat}: screenshot missing")
            continue
        image=Image.open(image_path)
        staff=detect_staff_lines(image)["right"]
        y=expected_y(staff,item["spelling"],clef)
        x=round(image.width*PLAYHEAD)
        pixels=bright(image)
        ranked=sorted(((name,round(_match_note_template(
            pixels,note_templates[name],staff.gap,x,y),4))
                for name in candidate_names), key=lambda p:p[1],reverse=True)
        expected_glyph=item["note_type"]+("_up" if item["note_type"]!="whole" else "")
        if expected_glyph not in note_templates:
            errors.append(f"Unsupported note sprite {expected_glyph}")
            continue
        if item["note_type"]=="eighth":
            # A quarter sprite is a subset of the eighth sprite. Pixel-Dice
            # alone can rank the smaller quarter higher even with an authentic
            # flag visibly present. Check the *additional flag ink*, far to
            # the right of the narrow stem, and require a strong eighth match.
            top=max(0,round(y-3.8*staff.gap))
            bottom=max(top,round(y-.7*staff.gap))
            flag_pixels=int(pixels[top:bottom,
                round(x+.82*staff.gap):round(x+1.9*staff.gap)].sum())
            expected_score=dict(ranked).get(expected_glyph,0.0)
            records.append({"symbol":f"rhythm beat {beat}","expected":expected_glyph,
                            "observed":expected_glyph if flag_pixels>=30 else "unflagged",
                            "score":expected_score,"flag_pixels":flag_pixels})
            if expected_score<.8 or flag_pixels<30:
                errors.append(f"Missing authentic eighth flag at beat {beat}: "
                              f"template={expected_score:.3f}, flag_pixels={flag_pixels}")
        else:
            _check_match(f"rhythm beat {beat}",expected_glyph,ranked,errors,records)
            if item["note_type"] in ("quarter","half","whole"):
                top=max(0,round(y-3.8*staff.gap))
                bottom=max(top,round(y-.7*staff.gap))
                unexpected=int(pixels[top:bottom,
                    round(x+.82*staff.gap):round(x+1.9*staff.gap)].sum())
                if unexpected>=30:
                    errors.append(f"Unexpected flag on {item['note_type']} beat {beat}")
        if item["dots"]:
            # A separate Verovio augmentation-dot outline must appear to
            # the right of the head, independent of its note sprite.
            ranked_dot=classify_symbol(image,fonts,("augmentation_dot",),
                x+staff.gap*1.05,y-staff.gap*.24,staff.gap,centered=True,
                dxs=range(-6,7),dys=range(-5,6))
            dot_score=ranked_dot[0][1]
            dots_checked+=1
            if dot_score<.72:
                errors.append(f"Missing augmentation-dot ink beat {beat} ({dot_score:.3f})")
    return {"passed":not errors,"written_notes":len(expected),
            "dots_checked":dots_checked,"matched":records,"errors":errors}


def prove_slur_ink(original_xml: str, generated_xml: str,folder: Path) -> dict:
    from xml.etree import ElementTree as ET
    source=ET.fromstring(original_xml)
    generated=ET.fromstring(generated_xml)
    source_marks=[(m.get("type"),m.get("number","1"))
                  for m in source.findall(".//notations/slur")]
    generated_marks=[(m.get("type"),m.get("number","1"))
                  for m in generated.findall(".//notations/slur")]
    errors=[]
    if source_marks != generated_marks or source_marks != [("start","1"),("stop","1")]:
        errors.append("Original slur endpoints are missing or changed")
    # Scan the physical midpoint away from note stems and noteheads. The
    # slur contour spans a D4-to-E4 interior interval in original MusicXML.
    frame=folder/"native-1.50.png"
    if not frame.is_file():
        errors.append("Missing middle-of-slur Godot screenshot")
        return {"passed":False,"errors":errors}
    image=Image.open(frame)
    staves=detect_staff_lines(image)
    score=read_written_score(original_xml)
    clef=_staff_clefs(score)["right"]
    notes={float(e["beat"]):e for e in score.symbols if e["kind"]=="note"
           and e["staff"]=="right"}
    low=min(expected_y(staves["right"],notes[i]["spelling"],clef)
            for i in (1.0,2.0))
    high=max(expected_y(staves["right"],notes[i]["spelling"],clef)
             for i in (1.0,2.0))
    gap=staves["right"].gap
    candidate=bridge_ink(image,range(round(low-3.5*gap),round(high+3.5*gap)))
    if candidate<7:
        errors.append(f"No source-expected slur curve at native image midpoint ({candidate})")
    return {"passed":not errors,"slur_marks":len(source_marks),
            "bridge_pixels":candidate,"errors":errors}


def _connector_pairs(xml, written, constructs, hand):
    """Pair printed segments, not the oracle's collapsed sounding attacks."""
    from xml.etree import ElementTree as ET

    notes = {n['source']['id']: n for n in written.symbols if n['kind'] == 'note'}
    pairs, opened = [], {}
    identifiers = Counter(n['id'] for n in notes.values() if n['id'])
    issues = {item['source']['id']: item['reason'] for item in written.issues}

    def emit(kind, a, b=None, reason=None, **details):
        endpoints = [n for n in (a, b) if n is not None]
        if hand != 'both' and any(n['staff'] != hand for n in endpoints):
            return
        if any(identifiers[n.get('id')] > 1 for n in endpoints):
            reason = 'Duplicate source segment identity prevents unique ownership'
        reason = reason or next((issues[n['source']['id']] for n in endpoints
                                 if n['source']['id'] in issues), None)
        pairs.append(dict(construct=kind, notes=endpoints, reason=reason, **details))

    if 'tie' in constructs:
        for n in sorted(notes.values(), key=lambda n: (n['beat'], n['index'], n['source']['ordinal'])):
            key = (n['part_index'], n['raw_staff'], n['voice'], n['pitch'])
            if n['tie_stop']:
                a = opened.pop(key, None)
                if a is None:
                    emit('tie', n, reason='Unpaired source tie stop, possibly outside the source window')
                else:
                    reason = (None if a['beat']+a['duration'] == n['beat'] else
                              'Source tie segments are not contiguous')
                    marks = [dict(attributes) for endpoint, kind in ((a, 'start'), (n, 'stop'))
                             for attributes in endpoint['tied_marks']
                             if dict(attributes).get('type') == kind]
                    if any(mark.get('line-type', 'solid') != 'solid' or
                           mark.get('print-object') == 'no' for mark in marks):
                        reason = 'Noncontinuous or hidden source tie style is not verified'
                    placement = next((mark['placement'] for mark in marks if 'placement' in mark), None)
                    emit('tie', a, n, reason, placement=placement,
                         number=next((mark['number'] for mark in marks if 'number' in mark), '1'))
            if n['tie_start']:
                if key in opened:
                    emit('tie', opened[key], reason='Overlapping source tie starts lack unique ownership')
                opened[key] = n
        for n in opened.values():
            emit('tie', n, reason='Unpaired source tie start, possibly outside the source window')
    if 'slur' in constructs:
        root = ET.fromstring(xml)
        for node in root.iter():
            node.tag = node.tag.rsplit('}', 1)[-1]
        opened = {}
        for pi, part in enumerate(root.findall('part')):
            for mi, measure in enumerate(part.findall('measure')):
                for ordinal, node in enumerate(measure):
                    if node.tag != 'note':
                        continue
                    sid = f'xml-p{pi}-m{mi}-e{ordinal}'
                    n = notes.get(sid)
                    for mark in node.findall('notations/slur'):
                        if n is None:
                            stub = dict(id=node.get('id'), source=dict(id=sid),
                                        staff='left' if node.findtext('staff') == '2' or
                                        part.get('id') == 'LH' or pi > 0 else 'right')
                            emit('slur', stub, reason='Untimed or unsupported source slur endpoint')
                            continue
                        key = (pi, mark.get('number', '1'))
                        kind = mark.get('type')
                        if kind == 'start':
                            if key in opened:
                                emit('slur', opened[key][0], reason='Overlapping source slur numbers are ambiguous')
                            opened[key] = (n, mark)
                        elif kind == 'stop':
                            previous = opened.pop(key, None)
                            if previous is None:
                                emit('slur', n, reason='Unpaired source slur stop, possibly outside the source window')
                            else:
                                a, start = previous
                                style = start.get('line-type', 'solid')
                                reason = (None if style == 'solid' and
                                          start.get('print-object') != 'no' and mark.get('print-object') != 'no'
                                          else 'Noncontinuous or hidden source slur style is not verified')
                                emit('slur', a, n, reason=reason, number=mark.get('number', '1'),
                                     placement=start.get('placement') or mark.get('placement'))
                        else:
                            emit('slur', n, reason='Source slur continuation needs separate boundary evidence')
        for n, _mark in opened.values():
            emit('slur', n, reason='Unpaired source slur start, possibly outside the source window')
    return pairs


def _connector_head(picture, written, note, origin_x):
    """Current PNG contour registration; no atlas or supplied pitch report."""
    from .reference_font import reference_glyphs
    from .raster_matching import _joint_candidates, photographed_playhead_columns
    from .phase3_pixels import _clef_at, _ledger_context_rows
    import math

    staves = detect_staff_lines(picture)
    rail = staves[note['staff']]
    y = expected_y(rail, note['spelling'], _clef_at(written, note['index'], note['staff']))
    kind = ('head_whole' if note['note_type'] == 'whole' else
            'head_half' if note['note_type'] == 'half' else 'head_black')
    # An image cannot assign one unison silhouette to multiple written voices.
    if sum(n['visible'] and n['kind'] == 'note' and n['beat'] == note['beat']
           and n['staff'] == note['staff'] and n['spelling'] == note['spelling']
           for n in written.symbols) > 1:
        return None
    glyph = reference_glyphs()[kind]
    pixels = bright(picture)
    radius = math.floor(.42*rail.gap/2)
    request = dict(glyph=glyph, gap=rail.gap, origin_y=y,
                   dxs=range(-round(rail.gap*.75), round(rail.gap*.75)+1),
                   dys=range(-radius, radius+1),
                   occlusion_columns=photographed_playhead_columns(picture),
                   alternatives=tuple((name,reference_glyphs()[name])
                       for name in ('head_black','head_half','head_whole') if name!=kind),
                   background_rows=_ledger_context_rows(pixels, rail, written, [note])
                   if kind != 'head_black' else ())
    candidates = _joint_candidates(pixels, request, origin_x, request['dys'], .79)
    if not candidates:
        return None
    chosen = candidates[0]
    if any(abs(row['x']-chosen['x']) > rail.gap*.6 and row['score'] >= chosen['score']-.03
           for row in candidates[1:]):
        return None
    b = glyph['bounds']
    width, height = max(1, round(b[2]*rail.gap/250)), max(1, round(b[3]*rail.gap/250))
    return dict(x=chosen['x']+width/2, y=chosen['y']-b[1]*rail.gap/250,
                bbox=[chosen['x'], chosen['y'], chosen['x']+width, chosen['y']+height],
                gap=rail.gap, contour_score=chosen['score'])


def _connector_shift(first, second):
    """Unique whole-ink translation between PNGs, independent of beat spacing."""
    if first.size != second.size:
        return None
    a, b = bright(first), bright(second)
    if min(int(a.sum()), int(b.sum())) < 24:
        return None
    left, right = a.sum(axis=0).astype(float), b.sum(axis=0).astype(float)
    ranked = []
    for shift in range(-round(first.width*.75), round(first.width*.75)+1):
        aa, bb = ((left[shift:], right[:-shift]) if shift > 0 else
                  (left[:shift], right[-shift:]) if shift < 0 else (left, right))
        norm = float(np.linalg.norm(aa)*np.linalg.norm(bb))
        ranked.append((float(aa.dot(bb))/norm if norm else 0., shift))
    measured = []
    for _, shift in sorted(ranked, reverse=True)[:12]:
        aa, bb = ((a[:, shift:], b[:, :-shift]) if shift > 0 else
                  (a[:, :shift], b[:, -shift:]) if shift < 0 else (a, b))
        total = int(aa.sum())+int(bb.sum())
        measured.append((2*int((aa & bb).sum())/total if total else 0., shift))
    score, shift = max(measured, key=lambda row: (row[0], -abs(row[1])))
    if score < .80 or any(s >= score-.02 and abs(x-shift) > 2 for s, x in measured):
        return None
    return dict(shift=shift, contour_agreement=round(score, 4))


def _connector_components(mask):
    """Eight-connected actual foreground, retaining all branches and gaps."""
    from collections import deque

    unseen = set(zip(*np.nonzero(mask)))
    while unseen:
        seed = unseen.pop()
        pending, component = deque([seed]), [seed]
        while pending:
            y, x = pending.popleft()
            for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1),
                           (0, 1), (1, -1), (1, 0), (1, 1)):
                item = (y+dy, x+dx)
                if item in unseen:
                    unseen.remove(item)
                    component.append(item)
                    pending.append(item)
        yield component


def _connector_neighbor_heads(picture, heads):
    """Find competing head silhouettes near attachments, irrespective of ID.

    An arc merely close to the requested pitch may belong to an adjacent
    note. Its endpoint must not be closer to another independently observed
    head. This local inventory reads only PNG and external font contours.
    """
    from .reference_font import reference_glyphs
    from .raster_matching import _joint_candidates

    pixels, neighbors = bright(picture), []
    for head in heads:
        gap = head['gap']
        radius = round(2*gap)
        for name in ('head_black', 'head_half', 'head_whole'):
            glyph = reference_glyphs()[name]
            request = dict(glyph=glyph, gap=gap, origin_y=head['y'],
                           dxs=range(-radius, radius+1), dys=range(-radius, radius+1))
            candidates = _joint_candidates(pixels, request, head['x'], request['dys'], .79)
            b = glyph['bounds']
            w, h = max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250))
            for row in candidates:
                x, y = row['x']+w/2, row['y']-b[1]*gap/250
                if any(abs(x-own['x']) < .6*gap and abs(y-own['y']) < .6*gap for own in heads):
                    continue
                if any(abs(x-other['x']) < .45*gap and abs(y-other['y']) < .3*gap for other in neighbors):
                    continue
                neighbors.append(dict(x=x, y=y, bbox=[row['x'], row['y'], row['x']+w, row['y']+h],
                                      contour_score=row['score']))
    return neighbors


def _connector_curve(picture, heads, construct, placement=None):
    """Connected, thin, curved ink must terminate at both measured heads.

    No reference-print X, native spacing, atlas curve or prescribed Bezier
    shape enters the test. Intersections/branches are inconclusive, never
    permission to replace a curve with other notation's ink.
    """
    a, b = heads
    gap = min(a['gap'], b['gap'])
    endpoint_limit = .9
    if b['x']-a['x'] < 1.5*gap:
        return dict(status='unverified', reason='Endpoint silhouettes overlap or leave insufficient separable curve ink')
    pixels = bright(picture).copy()
    stem_tips = []
    for head in heads:
        tips = []
        l, t, r, d = head['bbox']
        # Remove only each endpoint head and the actual vertical stem runs
        # attached to it. Other note/beam ink stays, exposing intersections.
        for x in range(max(0, l-2), min(picture.width, r+2)):
            ys = np.flatnonzero(pixels[max(0, t-round(5*gap)):min(picture.height, d+round(5*gap)), x])
            for run in np.split(ys, np.flatnonzero(np.diff(ys) > 1)+1):
                if len(run) < .8*gap:
                    continue
                top = int(run[0])+max(0, t-round(5*gap))
                bottom = int(run[-1])+max(0, t-round(5*gap))+1
                if top <= d+1 and bottom >= t-1:
                    if top < t-.8*gap:
                        tips.append((x, top))
                    if bottom > d+.8*gap:
                        tips.append((x, bottom-1))
                    pixels[top:bottom, max(0, x-1):min(picture.width, x+2)] = False
        pixels[max(0, t-1):d+1, max(0, l-1):r+1] = False
        stem_tips.append(tips)
    left, right = max(0, round(a['x']-gap)), min(picture.width, round(b['x']+gap))
    top = max(0, round(min(a['y'], b['y'])-5*gap))
    bottom = min(picture.height, round(max(a['y'], b['y'])+5*gap))
    minimum_span = b['x']-a['x']-2*gap
    if construct == 'tie':
        # An endpoint attaches to the visible head rectangle, not its centre.
        # A flagged or wide-head tie can have authentic edge clearances yet
        # fail the centre-based shortcut. This is the admissible horizontal
        # bound implied by the SAME endpoint-distance test below; passing it
        # does not authorize any curve. Slurs can also attach to stem tips.
        minimum_span = b['bbox'][0]-a['bbox'][2]-2*endpoint_limit*gap
    overlap, accepted, rejected, neighbors = False, [], [], None
    for component in _connector_components(pixels[top:bottom, left:right]):
        xy = np.asarray([(x+left, y+top) for y, x in component])
        xs, ys = xy[:, 0], xy[:, 1]
        x0, x1 = int(xs.min()), int(xs.max())
        if x1-x0 < minimum_span:
            continue
        centers, thickness = [], []
        for x in range(x0, x1+1):
            column = ys[xs == x]
            if not len(column):
                break
            centers.append(float(np.median(column)))
            thickness.append(int(column.max()-column.min()+1))
        if len(centers) != x1-x0+1:
            continue
        distances = []
        for head, tips, x, y in ((a, stem_tips[0], x0, centers[0]),
                                  (b, stem_tips[1], x1, centers[-1])):
            l, t, r, d = head['bbox']
            options = [float(np.hypot(max(l-x, 0, x-r), max(t-y, 0, y-d)))]
            if construct == 'slur':
                options += [float(np.hypot(tx-x, ty-y)) for tx, ty in tips]
            distances.append(min(options)/gap)
        if max(distances) > endpoint_limit:
            rejected.append(dict(component_bbox=[x0, int(ys.min()), x1+1, int(ys.max())+1],
                                 endpoint_distances_spaces=[round(d, 4) for d in distances]))
            continue
        if (x0 <= left or x1 >= right-1 or ys.min() <= top or ys.max() >= bottom-1):
            overlap = True
            continue
        if max(thickness) > .8*gap or np.quantile(thickness, .9) > .3*gap:
            overlap = True
            continue
        deviation = np.asarray(centers)-np.linspace(centers[0], centers[-1], len(centers))
        sag = float(np.max(np.abs(deviation)))
        sign = 1 if deviation[np.argmax(np.abs(deviation))] > 0 else -1
        if sag < .16*gap or np.mean(deviation*sign >= .08*gap) < .55:
            continue  # Straight ledgers/beams are not connective curves.
        if float(np.abs(np.diff(deviation)).sum()) > 4*sag+gap:
            overlap = True
            continue
        if ((placement == 'above' and np.median(ys) >= min(a['y'], b['y'])) or
                (placement == 'below' and np.median(ys) <= max(a['y'], b['y']))):
            continue
        if neighbors is None:
            neighbors = _connector_neighbor_heads(picture, heads)
        competing = []
        for own_distance, x, y in ((distances[0], x0, centers[0]), (distances[1], x1, centers[-1])):
            for other in neighbors:
                l, t, r, d = other['bbox']
                distance = float(np.hypot(max(l-x, 0, x-r), max(t-y, 0, y-d)))/gap
                if distance <= own_distance+.1 and distance < endpoint_limit:
                    competing.append(other)
        if competing:
            overlap = True
            rejected.append(dict(reason='Another observed head competes for the curve attachment',
                                 competing_heads=competing))
            continue
        runs = []
        for y in sorted(set(map(int, ys))):
            row = sorted(map(int, xs[ys == y]))
            for part in np.split(row, np.flatnonzero(np.diff(row) > 1)+1):
                runs.append([y, int(part[0]), int(part[-1])+1])
        accepted.append(dict(status='verified', reason='Unique connected thin curve attached to both source endpoints',
                    component_bbox=[x0, int(ys.min()), x1+1, int(ys.max())+1],
                    connected_pixels=len(component), curvature_spaces=round(sag/gap, 4),
                    endpoint_distances_spaces=[round(d, 4) for d in distances],
                    max_thickness_spaces=round(max(thickness)/gap, 4), pixel_runs=runs))
    if len(accepted) == 1:
        return accepted[0]
    if len(accepted) > 1:
        return dict(status='unverified', reason='Multiple attached curves lack unique source ownership')
    return dict(status='unverified' if overlap else 'mismatch', reason=(
        'Overlapping, competing or thick foreground prevents exclusive thin-curve ownership' if overlap else
        'No connected curved ink attaches to both source endpoint heads'),
        rejected_components=rejected[:8])


def verify_connector_pixels(xml: str, folder: Path, *, hand='both', constructs=('tie', 'slur')) -> dict:
    """Per-source-pair observations from XML and retained native PNGs only.

    Onset filenames schedule registration; authentic external font contours
    measure the heads in those PNGs near the public fixed playhead. Their
    positions in a common image are remeasured after pixel-only translation.
    Missing/occluded/offscreen evidence remains in the denominator. No atlas,
    renderer telemetry, density, reference X or supplied reports are read.
    Legacy focused prove_tie_ink/prove_slur_ink interfaces remain unchanged.
    """
    if hand not in ('both', 'left', 'right') or not set(constructs) <= {'tie', 'slur'}:
        raise ValueError('Invalid hand or connector construct')
    written = read_written_score(xml, strict=False)
    pairs = _connector_pairs(xml, written, constructs, hand)
    frames, frame_clocks = {}, {}
    for path in Path(folder).glob('native-*.png'):
        try:
            clock = float(path.stem[7:])
            key = round(clock, 5)
            frames[key], frame_clocks[key] = path, clock
        except ValueError:
            continue
    pictures, shifts, registered = OrderedDict(), {}, {}

    def picture(beat):
        if beat in pictures:
            pictures.move_to_end(beat)
            return pictures[beat]
        with Image.open(frames[beat]) as im:
            decoded = im.convert('RGB')
        if len(pictures) >= 12:
            _, evicted = pictures.popitem(last=False)
            evicted.close()
        pictures[beat] = decoded
        return pictures[beat]

    def head(note, beat, x):
        key = (note['source']['id'], beat, round(x, 2))
        if key not in registered:
            registered[key] = _connector_head(picture(beat), written, note, x)
        return registered[key]

    observations = []
    for pair in pairs:
        notes = pair['notes']
        row = dict(source_ids=[n.get('id') or n['source']['id'] for n in notes],
                   oracle_source_ids=[n['source']['id'] for n in notes],
                   construct=pair['construct'], number=pair.get('number'),
                   status='unverified', evidence={})
        observations.append(row)
        if pair['reason']:
            row['evidence']['reason'] = pair['reason']
            continue
        # Capture filenames have five fractional digits. Keep the exact
        # source fractions for source semantics and common-frame ordering;
        # only PNG lookup uses the capture protocol's rounded clock.
        source_beats = [n['beat'] for n in notes]
        beats = [round(float(beat), 5) for beat in source_beats]
        try:
            if not all(beat in frames for beat in beats):
                raise ValueError('Source endpoint onset PNG missing')
            if any(abs(frame_clocks[beat]-float(source)) > 5e-6+1e-12
                   for beat, source in zip(beats, source_beats)):
                raise ValueError('Source endpoint PNG clock differs by more than five decimal capture precision')
            if beats[0] == beats[1] and source_beats[0] != source_beats[1]:
                raise ValueError('Distinct source endpoints collide at five decimal capture precision')
            if any(not n['visible'] for n in notes) or notes[0]['staff'] != notes[1]['staff']:
                raise ValueError('Invisible or cross-staff endpoints require separate image evidence')
            own = [head(n, beat, picture(beat).width*PLAYHEAD) for n, beat in zip(notes, beats)]
            if any(h is None for h in own):
                raise ValueError('Source endpoint head is unavailable, offscreen or lacks unique contour evidence')
            common = sorted((beat for beat in frames if beats[0] <= beat <= beats[1]),
                            key=lambda beat: abs(beat-float(sum(source_beats)/2)))[:1]
            common += [beat for beat in beats if beat not in common]
            for beat in common:
                heads, correspondence = [], []
                for n, onset, anchor in zip(notes, beats, own):
                    key = (beat, onset)
                    if key not in shifts:
                        shifts[key] = (dict(shift=0, contour_agreement=1.) if beat == onset else
                                       _connector_shift(picture(beat), picture(onset)))
                    shift = shifts[key]
                    if shift is None:
                        break
                    h = head(n, beat, anchor['x']+shift['shift'])
                    if h is None:
                        break
                    heads.append(dict(source_id=n.get('id') or n['source']['id'], **h))
                    correspondence.append(dict(onset_frame=frames[onset].name, **shift))
                if len(heads) != 2:
                    row['evidence'] = dict(reason='Both endpoint heads cannot be uniquely registered in one PNG')
                    continue
                result = _connector_curve(picture(beat), heads, pair['construct'], pair.get('placement'))
                row.update(status=result.pop('status'), evidence=dict(
                    frame=frames[beat].name, heads=heads, correspondence=correspondence, **result))
                if row['status'] == 'verified':
                    break
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            row['evidence']['reason'] = str(exc)
    # One physical contour cannot certify two distinct source pairs.
    used = {}
    for index, row in enumerate(observations):
        if row['status'] != 'verified':
            continue
        evidence = row['evidence']
        support = {(evidence['frame'], y, x) for y, a, b in evidence['pixel_runs'] for x in range(a, b)}
        conflicts = {used[p] for p in support if p in used}
        if conflicts:
            for i in conflicts | {index}:
                observations[i]['status'] = 'unverified'
                observations[i]['evidence']['reason'] = 'Curve ink is shared by distinct source pairs'
        for pixel in support:
            used[pixel] = index
    coverage = dict(expected=len(observations), **{status:sum(r['status'] == status for r in observations)
                    for status in ('verified', 'unverified', 'mismatch')})
    complete = coverage['verified'] == coverage['expected']
    for image in pictures.values():
        image.close()
    return dict(complete=complete, passed=complete, coverage=coverage, observations=observations,
                scope='Independent written source pairs and current-PNG endpoint/connected-curve evidence')
