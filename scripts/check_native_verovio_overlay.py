#!/usr/bin/env python3
"""Canonical source/Verovio/native notation test for the entire MIDI library.

Loads the production native view.gd with the selected source and curriculum
scores. Independent MIDI/XML readers and actual framebuffer checks account
for source events, notation features and relative musical relationships.
Unresolved symbols fail explicitly; diagnostic PNGs remain beside failures.
--case retains the existing focused Verovio/native overlay regressions.

This is intentionally NOT a raw full-page pixel equality check: native
practice uses constant beats-per-pixel, whereas Verovio print spacing is
optical. Registration is by original source note ID, not an invented warp of
the score or a requirement that notation moves at varying speeds.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from bisect import bisect_right
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess
import sys
import hashlib

from PIL import Image, ImageDraw

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.music import Phrase, source_note_id
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from piano_teacher.raster import rasterize_score
from piano_teacher.score import import_piece, render_layout

ROOT = Path(__file__).resolve().parents[1]
AUTUMN_FILE = "Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi"
# Preserve the regression threshold that would have caught the 438px/beat
# user screenshot. More complex pieces use independently specified budgets.
MAX_AUTUMN_DENSITY = 400.0


@dataclass(frozen=True)
class AuditCase:
    name: str
    filename: str
    first_bar: int
    last_bar: int
    hand: str = "both"
    max_density: float = 640.0
    max_tiny_rests: int = 8
    max_dots: int = 2
    features: tuple[str, ...] = ()
    min_lookahead_beats: float = 0.0


# Explicit, pinned real MIDI corpus. Case changes require an intentional
# review: CI must never silently drop a hard score or select easy passages.
CASES = (
    AuditCase("autumn-7-8-both", AUTUMN_FILE, 7, 8,
              max_density=MAX_AUTUMN_DENSITY, max_tiny_rests=2,
              features=("aligned_swing",)),
    AuditCase("autumn-1-2-right", AUTUMN_FILE, 1, 2, "right"),
    AuditCase("ala-1-2-left", "Ala_–_Joep_Beving.midi", 1, 2, "left"),
    AuditCase("chopin-1-2-right",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 1, 2, "right"),
    AuditCase("chopin-5-6-both",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 5, 6,
              min_lookahead_beats=1.75, features=("triplet_turn",)),
    AuditCase("danny-boy-1-2-both", "Danny_Boy(Bill_Evans_Ver_).midi", 1, 2),
    AuditCase("merry-go-round-1-2-both", "Merry-Go-Round-of-Life.midi", 1, 2),
    AuditCase("peace-piece-1-2-both", "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", 1, 2),
    AuditCase("waltz-1-2-both", "Waltz_for_Debby.midi", 1, 2),
    AuditCase("fidelity-chord-ties",
              "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml",
              1, 2, features=("chords","ties")),
    AuditCase("fidelity-quintuplets",
              "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml",
              1, 1, "right", features=("tuplets",)),
    AuditCase("fidelity-grandstaff",
              "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml",
              1, 1, features=("grandstaff",)),
    AuditCase("fidelity-key-change",
              "tests/fixtures/musical_fidelity/xml_keys_spelling.musicxml",
              1, 2, "right", features=("key_change",)),
    AuditCase("fidelity-sparse-rests",
              "tests/fixtures/musical_fidelity/midi_sparse_rests.mid",
              1, 2, "right", features=("rests",)),
    AuditCase("fidelity-midi-triplets",
              "tests/fixtures/musical_fidelity/midi_triplets.mid",
              1, 1, "right", features=("tuplets",)),
)



def selected_cases(only: str | None = None) -> tuple[AuditCase, ...]:
    matches = tuple(c for c in CASES if not only or only.lower() in c.name.lower()
                    or only.lower() in c.filename.lower())
    if not matches:
        raise ValueError(f"No native overlay cases match {only!r}")
    return matches


def library_sources(directory: Path = ROOT / "midi", *, only: str = "") -> tuple[Path, ...]:
    """Discover the complete source library, including future bundled files."""
    sources = tuple(sorted((p for p in directory.iterdir()
                            if p.is_file() and p.suffix.casefold() in {".mid", ".midi"}),
                           key=lambda p: p.name.casefold()))
    if not sources:
        raise ValueError(f"No MIDI files in {directory}")
    selected = tuple(p for p in sources if only.casefold() in p.name.casefold())
    if not selected:
        raise ValueError(f"No MIDI files match {only!r}")
    return selected


def variant_errors(source: Phrase, variant) -> list[str]:
    """A learning stage may select source attacks, never change or invent them."""
    indices = variant.source_indices
    if len(indices) != len(set(indices)):
        return ["Learning variant duplicates a source note"]
    if any(not isinstance(i, int) or not 0 <= i < len(source.notes) for i in indices):
        return ["Learning variant has an unknown source note index"]
    if tuple(source.notes[i] for i in indices) != variant.phrase.notes:
        return ["Learning variant changes or invents source pitch, timing or identity"]
    if (source.start, source.end, source.first_bar, source.last_bar) != (
            variant.phrase.start, variant.phrase.end,
            variant.phrase.first_bar, variant.phrase.last_bar):
        return ["Learning variant changes its source measure boundaries"]
    return []


def selected_source_errors(phrase: Phrase, model: dict) -> list[str]:
    """Bind the exact rendered payload to immutable selected source events."""
    expected = {}
    for i, note in enumerate(phrase.notes):
        expected[source_note_id(note, i)] = {
            "midi_pitch": note.pitch, "hand": note.hand,
            "track": note.track, "channel": note.channel, "velocity": note.velocity,
            "onset_beats": round(note.start-phrase.start, 8),
            "duration_beats": round(min(note.end, phrase.end)-note.start, 8)}
    errors = []
    actual = {note.get("id"): note for note in model.get("notes", [])}
    if len(actual) != len(model.get("notes", [])) or actual.keys() != expected.keys():
        errors.append("Captured payload has missing, duplicate or invented source-note identities")
    for ident, fields in expected.items():
        for field, value in fields.items():
            if actual.get(ident, {}).get(field) != value:
                errors.append(f"Source note {ident} {field}: expected {value}, "
                              f"observed {actual.get(ident, {}).get(field)}")
    active = {ident for ident, note in expected.items()
              if model.get("active_hand") in ("both", note["hand"])}
    if (set(model.get("active_note_ids", [])) != active or
            len(model.get("active_note_ids", [])) != len(active)):
        errors.append("Captured payload has an incorrect active-hand source-note set")
    return errors


def context_first_bar(piece, first_bar: int) -> int:
    """Keep incoming ties by including their real attacks, without inventing one."""
    while first_bar > 1:
        start = piece.bar_boundaries[first_bar - 1]
        incoming = [note.start for note in piece.notes
                    if note.start < start - 1e-7 and note.end > start + 1e-7]
        if not incoming:
            break
        earlier = max(1, bisect_right(piece.bar_boundaries, min(incoming) + 1e-7))
        if earlier >= first_bar:
            break
        first_bar = earlier
    return first_bar


def original_cases(path: Path, piece, *, max_bars: int = 4):
    if max_bars < 1:
        raise ValueError("Window size must be positive")
    count = len(piece.bar_boundaries) - 1
    for first in range(1, count + 1, max_bars):
        last = min(first + max_bars - 1, count)
        context = context_first_bar(piece, first)
        for hand in ("right", "left", "both"):
            yield AuditCase(f"original-{first:04d}-{last:04d}-{hand}",
                            str(path), context, last, hand)


def feature_evidence_errors(report: dict) -> list[str]:
    """Inspect each observation; aggregate pass flags never authorize a glyph."""
    errors = []
    for row in report.get("measured", []):
        for feature, observation in row.get("features", {}).items():
            if observation.get("status") != "verified":
                errors.append(f"measure {row.get('measure')} {row.get('staff')} "
                              f"voice {row.get('voice')} {row.get('source_id')} "
                              f"{feature}: {observation.get('status', 'unverified')} "
                              f"{observation.get('reason', 'no independent pixel evidence')}")
    if not report.get("complete", False) and not errors:
        errors.append("Incomplete note-feature pixel accounting")
    return errors


def absence_evidence_errors(report: dict) -> list[str]:
    """Reject observed extra glyphs and missing capture evidence.

    The independent detector deliberately does NOT claim global absence of
    extra ink: headers, antialiasing and crossing glyphs leave residual pixels.
    Those pixels remain explicitly unverified in its evidence, not positive
    proof of invented notes or a reason every valid score must fail.
    """
    rows = [row for row in report.get('measured', []) if row.get('region') == 'viewport']
    errors = [f"Unexpected-symbol check {row.get('frame')} beat {row.get('clock')}: "
              f"{row.get('reason', 'unexpected glyph')}"
              for row in rows if row.get('status') == 'mismatch']
    coverage = report.get('coverage', {})
    if not rows:
        errors.append('No framebuffer observations for unexpected symbols')
    if any(row.get('status') not in ('verified', 'unverified', 'mismatch')
           for row in rows):
        errors.append('Unexpected-symbol detector returned an invalid status')
    if any('evidence' not in row for row in rows):
        errors.append('Unexpected-symbol observation has no pixel evidence')
    if coverage.get('measured_frames') != coverage.get('frames') or not coverage.get('frames'):
        errors.append('Incomplete actual framebuffer capture for unexpected symbols')
    if not coverage.get('initial_viewport') or not coverage.get('terminal_viewport'):
        errors.append('Missing opening or ending framebuffer coverage')
    if coverage.get('motion_status') != 'verified':
        errors.append('Unverified movement between sampled source positions')
    if (coverage.get('clock_gaps') or coverage.get('motion_errors')
            or coverage.get('missing_source_clocks') or coverage.get('binding_errors')):
        errors.append('Incomplete source clock or glyph tracking evidence')
    for kind in ('heads', 'rests'):
        if (not isinstance(coverage.get('expected_'+kind), int)
                or coverage.get('bound_'+kind) != coverage['expected_'+kind]):
            errors.append(f'Incomplete independent {kind} ownership')
    # Residual pixels and unresolved overprinting remain in the returned
    # evidence as unverified. Never turn them into an all-clear assertion.
    return errors


def symbol_error(row: dict) -> str:
    source = row.get("source", {})
    return (f"measure {source.get('measure')} {source.get('staff')} "
            f"voice {source.get('voice')} {source.get('id')} {row['construct']}: "
            f"{row['status']} {row.get('reason', row.get('differences', 'no independent evidence'))}")


def capture_clocks(xml: str) -> list[float]:
    from piano_teacher.notation.proof import read_written_score
    written = read_written_score(xml)
    clocks = {round(float(e["beat"]), 8) for e in written.symbols}
    clocks.update(round(float(beat), 8) for beat in written.bars)
    step = min(.0625, float(written.bars[-1])/4)
    clocks.update((0.0, round(step, 8), round(2*step, 8)))
    for boundary in written.bars[1:-1]:
        # Equal musical steps on either side expose a jump or freeze at a
        # measure join without prescribing the renderer's horizontal spacing.
        clocks.update((round(float(boundary)-step, 8),
                       round(float(boundary)+step, 8)))
    return sorted(clocks)


def fixture(case: AuditCase = CASES[0], *, piece=None,
            phrase: Phrase | None = None, cache=None) -> tuple[dict, object]:
    source = ROOT / (case.filename if "/" in case.filename
                     else "midi/" + case.filename)
    if piece is None:
        piece, _ = import_piece(source)
    assert 1 <= case.first_bar <= case.last_bar < len(piece.bar_boundaries)
    first = piece.bar_boundaries[case.first_bar - 1]
    end = piece.bar_boundaries[case.last_bar]
    notes = tuple(n for n in piece.notes if first <= n.start < end)
    original = phrase is None
    if phrase is None:
        phrase = Phrase(1, case.first_bar, case.last_bar, first, end, notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        default_clefs=None if piece.source_musicxml else infer_piece_clefs(piece.notes),
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
    )
    model = build_score_model(score, boundaries=piece.bar_boundaries,
                              hand=case.hand)
    compact = (phrase.last_bar-phrase.first_bar+1 <= 12 and phrase.end-phrase.start <= 48)
    engraving = render_layout(score, case.first_bar, case.last_bar, case.hand,
                              total_beats=end-first, bpm=piece.bpm, continuous=compact)
    key = cache.key("native-comparison-art", score.musicxml, case.hand,
                    piece.bpm, compact) if cache is not None else ""
    atlas = assemble_layout(engraving, native_notes=True, native_model=model,
                            notation_xml=score.musicxml, cache=cache, cache_key=key)
    return {
        "model": model,
        "assets": {key: atlas[key] for key in (
            "native_glyphs", "native_note_templates", "native_tie_templates",
            "native_chord_templates", "native_beam_fragments",
            "native_tuplet_fragments", "native_slur_fragments",
            "native_required_slur_pairs", "native_slurs_complete",
            "native_required_beam_groups", "native_beams_complete")},
        "first_bar": case.first_bar, "last_bar": case.last_bar,
        "sample_beats": [round(i * (end-first) / 4, 8) for i in range(4)],
        "hand": case.hand,
        "xml": score.musicxml,
        "original_xml": piece.source_musicxml if original else "",
        "source_errors": selected_source_errors(phrase, model),
    }, engraving


def visible_ink(image: Image.Image, x: float, y: float, radius: int = 11) -> int:
    """Count actual pale notation pixels, excluding dark/grey staff lines."""
    image = image.convert("RGB")
    px = image.load()
    matches = 0
    for yy in range(max(0, round(y)-radius),
                    min(image.height,round(y)+radius+1)):
        for xx in range(max(0, round(x)-radius),
                        min(image.width,round(x)+radius+1)):
            r, g, b = px[xx, yy]
            if r > 154 and g > 165 and b > 150:
                matches += 1
    return matches


def feature_errors(model: dict, case: AuditCase) -> list[str]:
    """Independently assert that each named challenging fixture tests its goal."""
    if not case.features:
        return []
    events = model["notation_events"]
    notes = [e for e in events if e["kind"] == "note"]
    from collections import Counter
    simultaneous = Counter((e.get("staff"), e.get("beat"), e.get("voice"))
                           for e in notes)
    measures = model.get("measures", [])
    pitched = sorted((e for e in notes if e.get("staff") == "right"),
                     key=lambda e:float(e.get("beat",0)))
    def matched_turn():
        for i in range(len(pitched)-2):
            group = pitched[i:i+3]
            if not all(e.get("note_type") == "32nd" and
                       (e.get("time_modification") or {}).get("actual") == 3 and
                       (e.get("time_modification") or {}).get("normal") == 2
                       for e in group):
                continue
            if all(abs(float(group[j+1]["beat"])-float(group[j]["beat"])
                       -1.0/12.0) < 2e-6 for j in (0,1)):
                return True
        return False
    source_onsets = {e["id"]:float(e.get("onset_beats",0.0))
                     for e in model.get("notes",[])}
    swung = sum(1 for e in notes if e.get("is_attack") and
                e.get("source_id") in source_onsets
                and abs((source_onsets[e["source_id"]] % 1.0)-.6)<.015
                and abs(float(e.get("beat",0.0))-
                        source_onsets[e["source_id"]]) < .004)
    observed = {
        "aligned_swing": swung >= 2,
        "chords": any(count > 1 for count in simultaneous.values()),
        "ties": any(not e.get("is_attack", True) for e in notes),
        "tuplets": any(e.get("time_modification") for e in notes),
        "grandstaff": {"left", "right"} <= {e.get("staff") for e in notes},
        "key_change": len({tuple(sorted(m["keys"].items())) for m in measures}) > 1,
        "rests": sum(e["kind"] == "rest" for e in events) >= 2,
        "triplet_turn": matched_turn() if "triplet_turn" in case.features else False,
    }
    return [f"{case.name} stopped exercising required {feature} notation"
            for feature in case.features if not observed.get(feature, False)]


# The generic readability checks must also work with tiny synthetic unit-test
# models; feature-presence requirements belong only to explicitly selected
# real passages, not to every call of the shared checker.
GENERIC_CASE = AuditCase("generic", AUTUMN_FILE, 7, 8,
                         max_density=MAX_AUTUMN_DENSITY, max_tiny_rests=2)


def readability_errors(model: dict, diagnostics: dict,
                       case: AuditCase = GENERIC_CASE) -> list[str]:
    """Fail on known engraving defects, with explicit per-passage budgets."""
    errors = feature_errors(model, case)
    if diagnostics["density"] > case.max_density:
        errors.append(f"{case.name} inflated to {diagnostics['density']:.1f} "
                      f"px/beat (max {case.max_density:.1f})")
    if case.min_lookahead_beats:
        available = float(diagnostics.get("density_witness", {}).get(
            "available_lookahead_beats", 0.0))
        if available + 1e-5 < case.min_lookahead_beats:
            errors.append(f"{case.name}: only {available:.2f} beats ahead "
                          f"(minimum {case.min_lookahead_beats:.2f})")
    if diagnostics["unavoidable_rest_overlaps"]:
        errors.append("Native rests collide with other voice ink")
    events = model["notation_events"]
    tiny_rests = [n for n in events if n["kind"] == "rest" and
                  n["note_type"] in {"32nd","64th","128th"}]
    if len(tiny_rests) > case.max_tiny_rests:
        errors.append("Excessive tiny printed rests in %s (%d; maximum %d)" %
                      (case.name, len(tiny_rests), case.max_tiny_rests))
    gap = float(diagnostics.get("staff_gap", 0.0))
    if gap <= 0.0:
        errors.append("Native staff has no valid layout scale")
    else:
        centers = diagnostics.get("staff_centers", {})
        for frame in diagnostics.get("frames", []):
            for rest in frame.get("rests", []):
                staff = str(rest.get("hand", ""))
                if staff not in centers:
                    errors.append("Rest has no native staff: "+str(rest["id"]))
                    continue
                if abs(float(rest["y"])-float(centers[staff])) > 3.2*gap:
                    errors.append("Rest displaced too far from its staff: "+
                                  str(rest["id"]))
    if any(n["kind"] == "note" and n["dots"] > case.max_dots for n in events):
        errors.append("Unconventional triple/quadruple-dot notation returned "
                      f"in {case.name}")
    note_ids = {n["id"] for n in events if n["kind"] == "note"}
    source_ids = {n["id"] for n in model["notes"]}
    graded = {n["source_id"] for n in events
              if n["kind"] == "note" and n["is_attack"]}
    if source_ids != graded:
        errors.append("Source MIDI attacks differ from visible score attacks")
    if not note_ids:
        errors.append("No native note identities found")
    return errors


def draw_overlay(reference: Image.Image, native: Image.Image,
                 verovio_notes: list[dict], heads: dict,
                 output: Path) -> int:
    """Color-register reference notehead crops by *source ID*, not print X.

    The reference (red) is overlaid on native pixels (mint) at the same
    musical note identity. Keep the full reference next to the local native
    view because rests and spacing differences can require expert review.
    """
    native = native.convert("RGBA")
    panel = native.convert("RGB")
    overlay = Image.new("RGBA", native.size, (0, 0, 0, 0))
    n = 0
    for note in verovio_notes:
        ident = str(note["id"])
        if ident not in heads or int(note.get("page",0)) != 0:
            continue
        x, y = heads[ident]
        if not (30 <= x < native.width-30 and 28 <= y < native.height-28):
            continue
        rx = round(float(note["x"]) * reference.width)
        ry = round(float(note["y"]) * reference.height)
        half = 12
        crop = reference.convert("RGBA").crop(
            (rx-half,ry-half,rx+half+1,ry+half+1))
        ink = crop.getchannel("A")
        # Reference raster may have an opaque background; compare ink alone.
        # Cairo's rendered Verovio ink has lower luminance than a white page.
        if ink.getextrema() == (255,255):
            grey = crop.convert("L")
            ink = grey.point(lambda p: 220 if p < 155 else 0)
        red = Image.new("RGBA",crop.size,(245,91,96,0))
        red.putalpha(ink.point(lambda a: round(a*.46)))
        overlay.alpha_composite(red, (round(x)-half,round(y)-half))
        n += 1
    composited = Image.alpha_composite(native,overlay).convert("RGB")
    pen = ImageDraw.Draw(composited)
    pen.text((34,14),"NATIVE + VEROVIO NOTE-ANCHOR OVERLAY (red = Verovio)",fill="white")
    composited.save(output)
    # Accompany overlay with the unwarped optical source and full native score.
    reference.thumbnail((native.width, native.height), Image.Resampling.LANCZOS)
    comparison = Image.new("RGB",(native.width,native.height*2),(19,44,35))
    comparison.paste(reference.convert("RGB"),(0,0))
    comparison.paste(panel,(0,native.height))
    comparison.save(output.with_name(output.stem+"-side-by-side.png"))
    return n


def capture_dependency_hash(root: Path = ROOT) -> str:
    """Include shared theme/resources as well as notation-specific scripts."""
    sources=[root/"tests/godot/native_verovio_overlay.gd"]
    sources.extend(p for p in (root/"godot").rglob("*")
                   if p.is_file() and ".godot" not in p.relative_to(root/"godot").parts
                   and p.suffix in {".gd",".gdshader",".gdshaderinc",".tscn",".tres",".godot",
                                    ".ttf",".otf",".woff",".woff2",".png",".svg"})
    digest=hashlib.sha256()
    for path in sorted(sources):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_capture_manifest(folder: Path, *, dependency_hash: str, godot_version: str) -> None:
    manifest=json.loads((folder/"capture-manifest.json").read_text())
    if manifest.get("renderer_dependencies_sha256")!=dependency_hash:
        raise AssertionError("Cached renderer dependencies changed or are unrecorded")
    if manifest.get("godot")!=godot_version:
        raise AssertionError("Cached Godot engine version differs from the current engine")
    captures=manifest.get("screenshots")
    if not isinstance(captures,list) or not captures:
        raise AssertionError("Cached capture manifest has no actual screenshot hashes")
    observed={path.name for pattern in ('native-*.png','rest-without-*.png','repeat-*.png','restored-*.png')
              for path in folder.glob(pattern)}
    recorded=[entry.get('file') for entry in captures]
    if len(set(recorded))!=len(recorded) or set(recorded)!=observed:
        raise AssertionError('Cached screenshot inventory differs from this capture manifest')
    for entry in captures:
        if hashlib.sha256((folder/entry["file"]).read_bytes()).hexdigest()!=entry["sha256"]:
            raise AssertionError(f"Cached actual screenshot changed: {entry['file']}")


def verification_inputs_hash(sources) -> str:
    """A long sweep must finish against the inputs and code it started with."""
    paths=[*sources,ROOT/'scripts/check_native_verovio_overlay.py',
           *sorted((ROOT/'piano_teacher').rglob('*.py')),
           ROOT/'tests/fixtures/musical_fidelity/manifest.json']
    digest=hashlib.sha256(capture_dependency_hash().encode())
    for path in sorted(paths):
        digest.update(str(path).encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


def run(out: Path, godot: str, case: AuditCase = CASES[0],
        *, all_symbols: bool = False, strict: bool = True,
        reuse_captures: bool = False, prepared=None) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    data, engraving = fixture(case) if prepared is None else prepared
    data = dict(data)
    model = data["model"]
    if all_symbols:
        # Every score symbol is positioned at the playhead in at least one
        # actual native frame. Every measure is also sampled even if silent.
        # No best-effort subset or fixed four-frame sampling is permitted.
        data["sample_beats"] = capture_clocks(data["xml"])
        data["phase3_full"] = True
        data["full_symbol_inventory"] = True
        if not data["sample_beats"]:
            raise AssertionError("Full-score witness has no sample clocks")
        if len({f"{at:.5f}" for at in data["sample_beats"]}) != len(data["sample_beats"]):
            raise AssertionError("Distinct source onsets would overwrite a screenshot filename")
    # Preserve the actual lesson MusicXML as the single reference score.
    xml=data.pop("xml")
    capture_sources=[ROOT/"tests/godot/native_verovio_overlay.gd",
                     *sorted((ROOT/"godot/notation").rglob("*.gd"))]
    data["capture_protocol_sha256"]=hashlib.sha256(b"".join(
        p.relative_to(ROOT).as_posix().encode()+p.read_bytes()
        for p in capture_sources)).hexdigest()
    dependencies = capture_dependency_hash()
    if reuse_captures:
        if json.loads((out/"fixture.json").read_text()) != data or (
                (out/"score.musicxml").read_text()!=xml):
            raise AssertionError("Cached capture provenance does not match current source/layout/protocol")
        validate_capture_manifest(out,dependency_hash=dependencies,
            godot_version=subprocess.check_output([godot,"--version"],text=True).strip())
    else:
        # A fresh producer must never inherit pixels or reference pages from
        # an older, longer score. Keep unrelated user files in the output dir.
        for pattern in ('native-*.png','rest-without-*.png','repeat-*.png',
                        'restored-*.png','verovio-*.svg','verovio-*.png',
                        'capture-manifest.json','native-overlay-report.json'):
            for artifact in out.glob(pattern):
                artifact.unlink()
    (out/"score.musicxml").write_text(xml,encoding="utf-8")
    (out/"fixture.json").write_text(json.dumps(data))
    for page, svg in enumerate(engraving.pages):
        (out/f"verovio-{page}.svg").write_text(svg)
        if not all_symbols:
            (out/f"verovio-{page}.png").write_bytes(rasterize_score(svg,width=2400))
    if not reuse_captures:
        result = subprocess.run([
            godot, "--path",str(ROOT/"godot"),"--rendering-method","gl_compatibility",
            "--windowed", "--resolution", "16x16", "--position", "-16384,-16384",
            "--disable-vsync", "--max-fps", "0",
            "--audio-driver", "Dummy",
            "--script",str(ROOT/"tests/godot/native_verovio_overlay.gd"),
            "--",str(out/"fixture.json"),str(out)],
            capture_output=True,text=True,timeout=max(180, 2*len(data["sample_beats"])))
        (out/"godot.log").write_text(result.stdout+result.stderr)
        if capture_dependency_hash() != dependencies:
            raise AssertionError("Renderer dependencies changed during actual capture; rerun the passage")
        assert result.returncode == 0 and "NATIVE_VEROVIO_OVERLAY_FAILURES:0" in result.stdout, (
            "Actual native renderer failed:\n"+(result.stdout+result.stderr)[-9000:])
        import platform
        import verovio
        captures=[{"file":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
                  for pattern in ("native-*.png","rest-without-*.png","repeat-*.png","restored-*.png")
                  for p in sorted(out.glob(pattern))]
        manifest={"capture_protocol_sha256":data["capture_protocol_sha256"],
                  "renderer_dependencies_sha256":dependencies,
                  "python":platform.python_version(),
                  "verovio":verovio.toolkit().getVersion(),
                  "godot":subprocess.check_output([godot,"--version"],text=True).strip(),
                  "screenshots":captures}
        (out/"capture-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    report = json.loads((out/"native-overlay-report.json").read_text())
    legacy_diagnostics = readability_errors(model, report, case)
    # The older editorial audit uses renderer geometry and per-passage
    # readability budgets. Those are diagnostics, not independent evidence
    # that legitimate full-piece notation is incorrect.
    errors = list(data.get("source_errors", []))
    if not all_symbols:
        errors.extend(legacy_diagnostics)
    reference = Image.open(out/"verovio-0.png") if not all_symbols else None
    refnotes = engraving.layout["notes"]
    printed_ids = {n["id"] for n in model["notation_events"] if n["kind"] == "note"}
    reference_ids = {n["id"] for n in refnotes}
    if reference_ids != printed_ids:
        errors.append(f"{case.name}: Verovio/native note IDs differ: "
                      f"{len(reference_ids)} reference, {len(printed_ids)} native")
    checked = 0
    rendered_ids = set()
    registered_ids = set()
    active_pixel_samples = 0
    note_staff = {e["id"]:e["staff"] for e in model["notation_events"]
                  if e["kind"] == "note"}
    active_hand = model["active_hand"]

    def is_active(staff: str) -> bool:
        return active_hand == "both" or active_hand == staff

    for frame in report["frames"]:
        screenshot = Image.open(out/frame["file"])
        heads = frame["noteheads"]
        expected = frame.get("expected_noteheads", {})
        for ident, expected_x in expected.items():
            if ident not in heads:
                errors.append(f"{case.name}: Native omitted visible note {ident} "
                              f"at {frame['clock']:.3f}")
            elif abs(heads[ident][0] - expected_x) > 2.4 * report["staff_gap"]:
                errors.append(f"{case.name}: Printed onset drift for {ident} "
                              f"at {frame['clock']:.3f}")
        for ident, (x,y) in heads.items():
            if 20 < x < screenshot.width-20 and 20 < y < screenshot.height-20:
                rendered_ids.add(ident)
                checked += 1
                if is_active(note_staff.get(ident, "")):
                    active_pixel_samples += 1
                if is_active(note_staff.get(ident, "")) and visible_ink(screenshot,x,y) < 5:
                    errors.append(f"Missing rendered native notehead {ident} "
                                  f"at beat {frame['clock']}")
        for rest in frame["rests"]:
            if (is_active(rest["hand"]) and
                    30 < rest["x"] < screenshot.width-30):
                if visible_ink(screenshot,rest["x"],rest["y"],26) < 7:
                    errors.append("Missing native rest pixels: "+str(rest["id"]))
        # Hundreds of full-score frames do not require hundreds of mostly
        # redundant overlay PNGs. Phase 2 retains the full editorial overlays.
        if not all_symbols:
            frame["reference_notes_overlaid"] = draw_overlay(
                reference.copy(),screenshot,refnotes,heads,
                out/f"overlay-{frame['clock']:.2f}.png")
        registered_ids.update(set(heads) & reference_ids)
    full_coverage = None
    if all_symbols:
        all_notes = {str(e["id"]) for e in model["notation_events"]
                     if e["kind"] == "note"}
        all_rests = {str(e["id"]) for e in model["notation_events"]
                     if e["kind"] == "rest"}
        registered_rests = {str(rest["id"]) for frame in report["frames"]
                            for rest in frame["rests"]}
        missed_notes = sorted(all_notes - rendered_ids)
        missed_rests = sorted(all_rests - registered_rests)
        unexpected_notes = sorted(rendered_ids - all_notes)
        unexpected_rests = sorted(registered_rests - all_rests)
        sampled_measures = set()
        for measure in model["measures"]:
            start = float(measure["start_beat"])
            if any(abs(float(frame["clock"]) - start) <= 0.0000001
                   for frame in report["frames"]):
                sampled_measures.add(int(measure["number"]))
        missed_measures = sorted(
            {int(m["number"]) for m in model["measures"]} - sampled_measures)
        full_coverage = {
            "measure_count": len(model["measures"]),
            "sampled_measures": len(sampled_measures),
            "source_noteheads": len(all_notes),
            "unique_rendered_noteheads": len(rendered_ids),
            "source_rests": len(all_rests),
            "unique_rendered_rests": len(registered_rests),
            "screenshot_count": len(report["frames"]),
            "missing_notes": missed_notes,
            "missing_rests": missed_rests,
            "missing_measure_starts": missed_measures,
            "unexpected_notes": unexpected_notes,
            "unexpected_rests": unexpected_rests,
            "witness_type": "Godot identity + per-note/rest ink proximity; "
                "not yet independent whole-piece symbol-classification",
        }
        if any((missed_notes, missed_rests, missed_measures,
                unexpected_notes, unexpected_rests)):
            errors.append(f"{case.name}: incomplete whole-window coverage: "
                          + json.dumps(full_coverage,sort_keys=True))
    if all_symbols:
        # Unlike the legacy overlay, this check reads the WRITTEN pitches
        # from MusicXML, then extracts staff lines and notehead positions
        # directly from PNG pixels. No Godot head/staff Y is permitted.
        from piano_teacher.notation.phase3_pixels import (
            verify_all_notehead_pixels, verify_all_rest_pixels, verify_scroll_pixels)
        engraving_xml=(out/"score.musicxml").read_text(encoding="utf-8")
        independent = verify_all_notehead_pixels(
            engraving_xml,out,hand=case.hand)
        rests_independent = verify_all_rest_pixels(
            engraving_xml,out,hand=case.hand)
        motion = verify_scroll_pixels(engraving_xml, out)
        (out/"independent-motion.json").write_text(json.dumps(motion,indent=2)+"\n")
        for row in motion["measured"]:
            if not row["passed"]:
                errors.append(f"measure transition at beat {row['clock']}: "
                              f"{row['reason']} {row.get('pixel_steps', [])}")
        full_coverage["independent_motion"] = motion
        full_coverage["independent_image_rests"] = {
            key:value for key,value in rests_independent.items()
            if key!="measured"
        }
        (out/"independent-rests.json").write_text(
            json.dumps(rests_independent,indent=2)+"\n")
        if not rests_independent["passed"]:
            errors.extend(f"Independent rest glyph: {message}"
                          for message in rests_independent["failures"][:30])
            if len(rests_independent["failures"])>30:
                errors.append(f"And {len(rests_independent['failures'])-30} "
                              "more rest image failures (see independent-rests.json)")
        full_coverage["independent_image_pitch"] = {
            key:value for key,value in independent.items() if key!="measured"
        }
        (out/"independent-pixels.json").write_text(
            json.dumps(independent,indent=2)+"\n")
        if not independent["passed"]:
            errors.extend(f"Independent native pixel check: {message}"
                          for message in independent["failures"][:30])
            if len(independent["failures"])>30:
                errors.append(f"And {len(independent['failures'])-30} more independent "
                              "pixel errors (see independent-pixels.json)")
        # A detector's 'passed' means no established mismatch. It must not
        # turn an ambiguous or unavailable symbol witness into a visual pass.
        for kind, proof in (("notehead", independent), ("rest", rests_independent)):
            for row in proof.get("measured", []):
                if row.get("status") != "verified":
                    errors.append(f"measure {row.get('measure')} {row.get('staff')} "
                                  f"voice {row.get('voice')} {row.get('source_id')} "
                                  f"{kind}: {row.get('status', 'unverified')} "
                                  f"{row.get('reason', 'incomplete independent image evidence')}")
        from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels
        from piano_teacher.notation.connector_pixels import verify_beam_pixels, verify_tuplet_pixels
        connectors=verify_connector_pixels(engraving_xml,out,hand=case.hand)
        beams=verify_beam_pixels(engraving_xml,out,hand=case.hand)
        tuplets=verify_tuplet_pixels(engraving_xml,out,hand=case.hand)
        by_id={event['id']:event for event in model['notation_events']}
        for label,proof in (('connectors',connectors),('beams',beams),('tuplets',tuplets)):
            (out/f'independent-{label}.json').write_text(json.dumps(proof,indent=2)+'\n')
            full_coverage[f'independent_{label}']=proof['coverage']
            for observation in proof.get('observations',proof.get('measured',[])):
                if observation.get('graphical',True) and observation['status']!='verified':
                    ids=observation.get('event_ids',observation.get('source_ids',[]))
                    source=next((by_id[identity] for identity in ids if identity in by_id),observation)
                    errors.append(symbol_error(dict(construct=observation['construct'],
                        source=dict(source,id='|'.join(str(i) for i in ids)),status=observation['status'],
                        reason=observation.get('reason') or observation.get('evidence',{}).get('reason','No independent connector evidence'))))
        from piano_teacher.notation.feature_pixels import verify_note_feature_pixels, verify_structure_pixels, verify_ledger_pixels
        features = verify_note_feature_pixels(engraving_xml, out, hand=case.hand)
        ledgers=verify_ledger_pixels(engraving_xml,out,hand=case.hand)
        (out/'independent-ledgers.json').write_text(json.dumps(ledgers,indent=2)+'\n')
        errors.extend(feature_evidence_errors(ledgers))
        full_coverage['independent_ledgers']=ledgers['coverage']
        (out/"independent-features.json").write_text(json.dumps(features,indent=2)+"\n")
        errors.extend(feature_evidence_errors(features))
        full_coverage["independent_note_features"] = features["coverage"]
        from piano_teacher.notation.semantic_contract import verify_generated_contract
        semantics = verify_generated_contract(engraving_xml, model)
        (out/"semantics.json").write_text(json.dumps(semantics,indent=2)+"\n")
        for row in semantics["elements"]:
            if row["status"] != "verified":
                errors.append("Generated/native " + symbol_error(row))
        from piano_teacher.notation.visual_coverage import visual_elements, coverage_counts
        elements = visual_elements(data.get("original_xml") or None,
            engraving_xml, independent, rests_independent, hand=case.hand,
            first_bar=case.first_bar, last_bar=case.last_bar,
            source_name=case.filename, feature_report=features,connector_report=connectors,
            beam_report=beams,tuplet_report=tuplets,ledger_report=ledgers,
            semantic_report=semantics)
        structures = verify_structure_pixels(engraving_xml, out, elements,
                                              hand=case.hand, first_bar=case.first_bar)
        structural = {row["id"]: row for row in structures}
        for row in elements:
            if row["id"] in structural and row["status"] != "mismatch":
                observation = structural[row["id"]]
                row.update({key: observation[key] for key in ("status", "reason", "evidence")})
        (out/"independent-structure.json").write_text(json.dumps(structures,indent=2)+"\n")
        # MIDI has no unique authored spelling. That is an interpretation
        # limit, separate from checking every symbol of its chosen score.
        required = [row for row in elements if row["construct"] != "midi_written_transcription"]
        (out/"independent-symbols.json").write_text(json.dumps(elements,indent=2)+"\n")
        full_coverage["symbols"] = coverage_counts(required)
        for row in required:
            if row["status"] != "verified":
                errors.append(symbol_error(row))
        from piano_teacher.notation.extra_symbol_pixels import verify_extra_symbol_pixels
        absence = verify_extra_symbol_pixels(engraving_xml, out, hand=case.hand)
        (out/'independent-unexpected-symbols.json').write_text(json.dumps(absence,indent=2)+'\n')
        full_coverage['unexpected_symbols'] = absence['coverage']
        errors.extend(absence_evidence_errors(absence))
    if checked == 0 and printed_ids:
        errors.append("No on-screen native noteheads were checked")
    active_written_notes = sum(
        1 for event in model["notation_events"]
        if event["kind"] == "note" and is_active(event["staff"]))
    if active_pixel_samples == 0 and active_written_notes:
        errors.append("No active-hand noteheads were pixel-verified")
    # A hand with no written notes is a valid silent practice mode, not
    # evidence of missing pixels. Its rests still require screenshot coverage.
    if not registered_ids and reference_ids:
        errors.append("Original Verovio identities never aligned with native frames")
    if rendered_ids - reference_ids:
        errors.append(f"Native rendered {len(rendered_ids-reference_ids)} "
                      "notes absent from Verovio")
    summary = {
        "source":f"{case.filename}, measures {case.first_bar}-{case.last_bar}, {case.hand}",
        "case":case.name,
        "density":report["density"],
        "density_witness":report.get("density_witness", {}),
        "native_notehead_samples":checked,
        "reference_source_note_count":len(refnotes),
        "distinct_native_noteheads":len(rendered_ids),
        "active_notehead_pixel_samples":active_pixel_samples,
        "registered_noteheads":len(registered_ids),
        "tiny_rests":sum(1 for n in model["notation_events"] if
                         n["kind"] == "rest" and n["note_type"] in
                         {"32nd","64th","128th"}),
        "maximum_dots":max((n["dots"] for n in model["notation_events"]
                            if n["kind"] == "note"), default=0),
        "rest_overlap_count":report["unavoidable_rest_overlaps"],
        "errors":errors,
        "passed":not errors,
        "legacy_renderer_diagnostics":legacy_diagnostics,
        "whole_window_coverage":full_coverage,
        "nonverified_symbols": (dict(Counter(
            f"{row['construct']}:{row['status']}" for row in required
            if row['status'] != 'verified')) if all_symbols else {}),
    }
    (out/"audit.json").write_text(json.dumps(summary,indent=2)+"\n")
    if errors and strict:
        raise AssertionError("\n".join(errors))
    return summary


def curriculum_cases(path: Path, piece):
    """Enumerate the actual production curriculum, including dense focus stages."""
    from piano_teacher.learning import LearningPlan
    plan = LearningPlan(piece)
    for index, exercise in enumerate(plan.exercises):
        plan.select(index)
        for hand in plan.hands:
            plan.set_hand(hand)
            for variant in plan.variants:
                case = AuditCase(f"{exercise.kind}-{index:04d}-{hand}-{variant.level}",
                                 str(path), variant.phrase.first_bar,
                                 variant.phrase.last_bar, hand)
                yield case, exercise.phrase, variant


@lru_cache(maxsize=32)
def _library_piece(path: str):
    return import_piece(Path(path))[0]


def _library_job(case, source_phrase, variant, directory, godot, reuse_captures=False,
                 focused=False):
    """One native/Verovio worker; named editorial regressions share the renderer."""
    try:
        if variant is not None:
            problems = variant_errors(source_phrase, variant)
            if problems:
                raise AssertionError("; ".join(problems))
        piece = _library_piece(case.filename)
        from piano_teacher.preprocessing_cache import PreprocessingCache
        cache = PreprocessingCache(directory.parent.parent/"cache")
        prepared = fixture(case, piece=piece,
                           phrase=variant.phrase if variant is not None else None, cache=cache)
        result=None
        if reuse_captures and (directory/'capture-manifest.json').is_file():
            try:
                result=run(directory,godot,case,all_symbols=not focused,strict=False,
                           prepared=prepared,reuse_captures=True)
            except (AssertionError,OSError,ValueError) as exc:
                print(f'RECAPTURE {case.name}: {exc}',flush=True)
        if result is None:
            result=run(directory,godot,case,all_symbols=not focused,strict=False,prepared=prepared)
        if not result["errors"]:
            for picture in directory.glob("*.png"):
                picture.unlink()
        return {"errors": result["errors"][:25], "error_count": len(result["errors"]),
                "captured": True,
                "nonverified_symbols": result["nonverified_symbols"],
                "symbols": (result["whole_window_coverage"] or {}).get("symbols", {})}
    except Exception as exc:
        return {"errors": [f"{type(exc).__name__}: {exc}"], "error_count": 1,
                "captured": False, "symbols": {}}


def audit_library(out: Path, godot: str, *, only: str = "", max_bars: int = 4,
                  include_fixtures: bool = True, workers: int = 4,
                  reuse_captures: bool = False) -> dict:
    """One source/Verovio/native test; no second renderer or certification stack."""
    def discover_sources():
        discovered=list(library_sources(only=only))
        if include_fixtures and not only:
            manifest_dir=ROOT/'tests/fixtures/musical_fidelity'
            manifest=json.loads((manifest_dir/'manifest.json').read_text())
            discovered.extend(manifest_dir/entry['file'] for entry in manifest['supported'])
        return discovered
    sources=discover_sources()
    inputs_hash=verification_inputs_hash(sources)
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary = {"passed": False, "sources_expected": len(sources),
               "inputs_sha256": inputs_hash,
               "sources_checked": 0, "cases_expected": 0, "cases_checked": 0,
               "measures_expected": 0, "measures_checked": 0,
               "failures": [], "nonverified_symbols": {}}
    from piano_teacher.notation.semantic_contract import (
        verify_midi_performance, verify_musicxml_contract)
    plans=[]
    for source_index, path in enumerate(sources):
        try:
            piece = _library_piece(str(path))
            whole = Phrase(1, 1, len(piece.bar_boundaries)-1,
                           piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
            score = build_lesson_score(whole, boundaries=piece.bar_boundaries,
                time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
                clef_changes=piece.clef_changes, barlines=piece.barlines,
                source_musicxml=piece.source_musicxml,
                default_clefs=None if piece.source_musicxml else infer_piece_clefs(piece.notes))
            model = build_score_model(score, boundaries=piece.bar_boundaries, hand="both")
            if path.suffix.casefold() in {".mid", ".midi"}:
                model["import_warnings"] = list(piece.import_warnings)
                semantics = verify_midi_performance(path, model, generated_xml=score.musicxml)
            else:
                semantics = verify_musicxml_contract(path.read_text(), score.musicxml, model)
            for row in semantics["elements"]:
                if row["status"] in {"mismatch", "unverified"}:
                    summary["failures"].append(f"{path.name}: " + symbol_error(row))
            originals = tuple(original_cases(path, piece, max_bars=max_bars))
            stages = tuple(curriculum_cases(path, piece))
            # The named hard passages enforce editorial constraints (notably
            # the user's Autumn Leaves density and Chopin triplet turn) that
            # are not checked by the full-symbol pixel comparisons alone.
            focused = tuple((case,None,None) for case in CASES
                if (ROOT / (case.filename if "/" in case.filename
                            else "midi/" + case.filename)).resolve() == path.resolve())
            summary["cases_expected"] += len(originals) + len(stages) + len(focused)
            summary["measures_expected"] += len(piece.bar_boundaries)-1
            plans.append((source_index,path,[(case,None,None) for case in originals],
                          list(stages),list(focused)))
            directory=out/f"{source_index:02d}-{path.stem}"
            directory.mkdir(parents=True,exist_ok=True)
            (directory/"source-semantics.json").write_text(json.dumps(semantics,indent=2)+"\n")
        except Exception as exc:
            message = f"{path.name}: {type(exc).__name__}: {exc}"
            summary["failures"].append(message)
            print("FAIL " + message, flush=True)
    # Freeze all denominators before capture. Cover every original measure,
    # then the named hard passages, then the generated learning curriculum.
    completed=Counter()
    visited={index:set() for index,_,_,_,_ in plans}
    totals={index:len(originals)+len(stages)+len(focused)
            for index,_,originals,stages,focused in plans}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for phase in (2,4,3):
            submitted = {}
            for plan in plans:
                source_index,path=plan[:2]
                for case,source_phrase,variant in plan[phase]:
                    directory=out/f"{source_index:02d}-{path.stem}"/case.name
                    future=pool.submit(_library_job,case,source_phrase,variant,
                                       directory,godot,reuse_captures,phase==4)
                    submitted[future]=(source_index,path,case,variant,directory)
            for future in as_completed(submitted):
                source_index,path,case,variant,directory=submitted[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"errors": [f"Worker failed: {exc}"], "captured": False}
                if result["errors"]:
                    message = f"{path.name} {case.name}: {result['errors'][0]}"
                    summary["failures"].append(message)
                    print("FAIL " + message + f" (details: {directory})", flush=True)
                else:
                    print(f"PASS {path.name} {case.name}", flush=True)
                for kind, count in result.get("nonverified_symbols", {}).items():
                    summary["nonverified_symbols"][kind] = summary["nonverified_symbols"].get(kind, 0)+count
                if phase == 2 and result["captured"]:
                    visited[source_index].update(range(case.first_bar, case.last_bar+1))
                summary["cases_checked"] += 1
                completed[source_index]+=1
                if completed[source_index]==totals[source_index]:
                    summary["sources_checked"]+=1
                summary["measures_checked"]=sum(map(len,visited.values()))
                if summary["cases_checked"]%25==0 or completed[source_index]==totals[source_index]:
                    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    from piano_teacher.preprocessing_cache import PreprocessingCache
    PreprocessingCache(out/"cache").prune()
    try:
        current_sources=discover_sources()
        if current_sources!=sources:
            summary['failures'].append('Source membership changed during this audit; rerun the complete check')
        elif verification_inputs_hash(sources)!=inputs_hash:
            summary['failures'].append('Source inputs or verification code changed during this audit; rerun the complete check')
    except (OSError,ValueError) as exc:
        summary['failures'].append(f'Source membership changed or became unreadable during this audit: {exc}')
    summary["passed"] = (not summary["failures"] and
                         summary["sources_checked"] == summary["sources_expected"] and
                         summary["cases_checked"] == summary["cases_expected"] and
                         summary["measures_checked"] == summary["measures_expected"])
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,
                        default=Path("/tmp/piano-native-verovio-overlay"))
    parser.add_argument("--only", default="", help="MIDI filename substring (focused diagnosis)")
    parser.add_argument("--case", help="Run one existing focused regression case")
    parser.add_argument("--window-bars", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4,
                        help="Independent Godot capture processes (default: 4)")
    parser.add_argument("--reuse-captures",action="store_true",
                        help="Recheck unchanged retained PNGs; changed or missing captures are rendered again")
    a=parser.parse_args()
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Actual Godot 4 renderer is required")
    if a.window_bars < 1:
        parser.error("--window-bars must be positive")
    if a.workers < 1:
        parser.error("--workers must be positive")
    if not a.case:
        try:
            summary = audit_library(a.out, godot, only=a.only, max_bars=a.window_bars,
                                    workers=a.workers,reuse_captures=a.reuse_captures)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Native notation: {summary['sources_checked']}/{summary['sources_expected']} sources, "
              f"{summary['measures_checked']}/{summary['measures_expected']} measures, "
              f"{summary['cases_checked']}/{summary['cases_expected']} cases, "
              f"{len(summary['failures'])} failures; {a.out}", flush=True)
        return int(not summary["passed"])
    cases = selected_cases(a.case)
    results = []
    errors = []
    for case in cases:
        directory = a.out / case.name
        try:
            summary = run(directory, godot, case)
            results.append(summary)
            print(f"PASS {case.name}: {summary['native_notehead_samples']} pixels "
                  f"checked; {summary['density']:.1f} px/beat; limiting ink: "
                  + json.dumps(summary["density_witness"],sort_keys=True),
                  flush=True)
        except Exception as exc:
            errors.append({"case":case.name,"error":str(exc)})
            print(f"FAIL {case.name}: {exc}",file=sys.stderr,flush=True)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"summary.json").write_text(json.dumps({
        "passed":len(results),"failed":len(errors),"results":results,
        "failures":errors},indent=2)+"\n")
    print(f"Native Verovio overlay: {len(results)} passed, "
          f"{len(errors)} failed",flush=True)
    return 1 if errors else 0


if __name__=="__main__":
    sys.exit(main())
