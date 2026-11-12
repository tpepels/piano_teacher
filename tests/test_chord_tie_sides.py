"""Ties of chord notes bow to the side Verovio gives them.

Verovio splits a chord's ties by note index, bottom to top: the lower half
bows below, the upper half above, the middle note of an odd chord opposite
its stem; a whole chord uses the virtual stem Verovio sets its heads by.
Each case is a lesson prepared through the real import and Verovio
engraving; Verovio's own ties on that lesson's MusicXML are the reference.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from verovio_test_score import prepare_musicxml, score_xml

ROOT = Path(__file__).resolve().parents[1]
_L = "CDEFGAB"
_NUMBER = r"-?\d+(?:\.\d+)?"


def _tied(names: str, kind: str, duration: int, tie: str, stem: str | None = None) -> str:
    out = []
    for index, name in enumerate(names.split()):
        out.append(f"<note>{'<chord/>' if index else ''}<pitch><step>{name[0]}</step>"
                   f"<octave>{name[1:]}</octave></pitch><duration>{duration}</duration>"
                   f"<voice>1</voice><type>{kind}</type>" + (f"<stem>{stem}</stem>" if stem else "")
                   + f'<tie type="{tie}"/><notations><tied type="{tie}"/></notations></note>')
    return "".join(out)


# (measure pairs) the reviewer's whole chord, asymmetric chords with each
# stem, even and odd chords, a middle note on each side of the midpoint.
CASES = [
    ("A3 F5 G5", "whole", 16, None),
    ("C4 D4 E4 C6", "whole", 16, None),
    ("A3 F5 G5 A5", "half", 8, None),
    ("D4 A4 C5", "half", 8, "up"),
    ("D4 A4 C5", "half", 8, "down"),
    ("C4 D4 F4 G4 D5", "half", 8, None),
    ("C4 F4 G4 A4 C5", "half", 8, "up"),
]


def _score() -> str:
    # The import keeps a tied pair as one sustained note; the lesson writes a
    # tie where that note crosses a barline. Each chord therefore ends its
    # bar and continues into the next.
    rest = {"whole": "", "half": '<note><rest/><duration>8</duration><voice>1</voice><type>half</type></note>'}
    right = []
    for names, kind, duration, stem in CASES:
        right += [rest[kind] + _tied(names, kind, duration, "start", stem),
                  _tied(names, kind, duration, "stop", stem) + rest[kind]]
    return score_xml(right)


def _verovio_sides(xml: str) -> dict[str, str]:
    """Start note id -> the side Verovio bows its tie to, on this MusicXML."""
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "pageWidth": 2100, "pageHeight": 60000,
                               "adjustPageHeight": True, "breaks": "none"})
    assert toolkit.loadData(xml)
    mei = toolkit.getMEI()
    starts = {}
    for tag in re.findall(r"<tie [^>]*>", mei):
        ident = re.search(r'xml:id="([^"]+)"', tag)
        start = re.search(r'startid="#([^"]+)"', tag)
        if ident and start:
            starts[ident.group(1)] = start.group(1)
    sides = {}
    for page in range(1, toolkit.getPageCount() + 1):
        for group in ET.fromstring(toolkit.renderToSVG(page)).iter():
            if "tie" in (group.get("class") or "").split() and group.get("id") in starts:
                path = next(p for p in group.iter() if p.tag.endswith("path"))
                ys = [float(v) for v in re.findall(_NUMBER, path.get("d", ""))][1::2]
                sides[starts[group.get("id")]] = "below" if max(ys) > ys[0] + 5 else "above"
    return sides


def test_native_chord_ties_bow_where_verovio_bows_them(tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    prepared = prepare_musicxml(_score(), tmp_path)
    expected = _verovio_sides(prepared["notation_xml"])
    keys = ("native_glyphs", "native_note_templates", "native_tie_templates",
            "native_chord_templates", "native_beam_fragments", "native_tuplet_fragments",
            "native_slur_fragments", "native_required_slur_pairs", "native_slurs_complete",
            "native_required_beam_groups", "native_beams_complete")
    source = tmp_path / "ties.json"
    source.write_text(json.dumps({"layout": {k: prepared["layout"][k] for k in keys},
                                  "model": prepared["model"]}))
    proc = subprocess.run([binary, "--headless", "--path", str(ROOT / "godot"), "--script",
                           str(ROOT / "tests/godot/chord_tie_sides.gd"), "--", str(source)],
                          capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"})
    line = next((l for l in proc.stdout.splitlines() if l.startswith("TIE_SIDES:")), None)
    assert line, proc.stdout[-3000:] + proc.stderr[-2000:]
    native = json.loads(line.split(":", 1)[1])
    names = {e["id"]: f"m{e['measure']} {e['spelling']['step']}{e['spelling']['octave']}"
             for e in prepared["model"]["notation_events"] if e["kind"] == "note"}
    assert len(native) >= sum(len(c[0].split()) for c in CASES)
    mismatched = {names[i]: (side, expected.get(i)) for i, side in native.items()
                  if side != expected.get(i)}
    assert not mismatched, mismatched
