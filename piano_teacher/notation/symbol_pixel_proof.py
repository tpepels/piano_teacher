"""Phase 2 image-space symbol proof using independently read MusicXML and ink.

This module never reads Godot's reported coordinates to decide where or
which symbol to accept. It reads actual native PNG pixels, recovers the five-
line staves, and checks expected glyph silhouettes (against original Verovio
font outlines) and connective ink from source beam/tie declarations.
A semantic preflight rejects symbols lost before rendering.
"""
from __future__ import annotations

from collections import Counter
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
        _check_match(f"rhythm beat {beat}",expected_glyph,ranked,errors,records)
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
