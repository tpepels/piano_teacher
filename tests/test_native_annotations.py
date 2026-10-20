"""Authentic annotation geometry, identity, complete validation and native pixels."""
from __future__ import annotations
import base64
import copy
import gzip
import importlib.util
import json
import os
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def extractor():
    name = "piano_teacher.notation.assets.annotations"
    assert importlib.util.find_spec(name) is not None, "annotation extractor is not implemented"
    from piano_teacher.notation.assets.annotations import annotation_fragments
    return annotation_fragments


def score_model():
    notes = [{"id": f"n{i+1}", "kind": "note", "beat": float(i),
              "staff": "right", "voice": "1", "midi_pitch": [60, 62, 64, 65][i],
              "duration_beats": 1.0} for i in range(4)]
    return {"staff_order": ["right"], "notation_events": notes,
        "measures": [{"start_beat": 0.0, "end_beat": 4.0}],
        "annotations": [{"id": "a-"+kind, "kind": kind, "beat": 0.0,
                         **({"end_beat": end} if end else {}),
                         "staff": "right", "voice": "1",
                         "event_ids": ["n1", "n4"] if end else ["n1"],
                         "attributes": {}}
                        for kind, end in [("dynamic", None), ("hairpin", 3.0),
                            ("articulation", None), ("ornament", None),
                            ("pedal", 3.0), ("volta", 4.0)]],
        "visual_events": [{"id": f"g{i+1}", "kind": "grace", "anchor_id": "n1",
            "beat": 0.0, "staff": "right", "voice": "1", "midi_pitch": pitch,
            "spelling": {"step": step, "octave": 4, "alter": 0},
            "note_type": "16th", "dots": 0, "slash": True, "position": "before"}
            for i, (pitch, step) in enumerate([(62, "D"), (64, "E")])]}


@pytest.fixture(scope="module")
def source_svg():
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "mei", "scale": 80,
        "pageWidth": 1500, "pageHeight": 1000, "breaks": "none", "svgViewBox": True,
        "svgBoundingBoxes": True, "svgContentBoundingBoxes": True})
    assert toolkit.loadData((ROOT / "tests/fixtures/native_annotations.mei").read_text())
    return toolkit.renderToSVG(1)


def test_authentic_groups_keep_all_semantic_ids_and_original_contours(source_svg):
    model = score_model()
    original = copy.deepcopy(model)
    atlas = extractor()([source_svg], model)
    assert set(atlas) == {"a-dynamic", "a-hairpin", "a-articulation", "a-ornament",
                          "a-pedal", "a-volta", "g1", "g2"}
    assert model == original
    original_paths = {n.get("d") for n in ET.fromstring(source_svg).iter() if n.get("d")}
    for ident, item in atlas.items():
        assert item["id"] == ident and item["source"] == "verovio-annotation"
        assert item["units_per_space"] == 250
        assert item["staff"] == "right" and item["voice"] == "1"
        assert item["beat"] == 0.0 and item["origin"] == [0.0, 0.0]
        assert item["parts"]
        for part in item["parts"]:
            assert part["bounds"][2] > 0 and part["bounds"][3] > 0
            image = Image.open(BytesIO(base64.b64decode(part["png_base64"])))
            assert image.getchannel("A").getbbox()
            paths = {n.get("d") for n in ET.fromstring(part["svg"]).iter() if n.get("d")}
            assert paths <= original_paths
    assert atlas["g1"]["group_ids"] == ["g1", "g2"]
    assert atlas["g2"]["anchor_id"] == "n1"
    assert atlas["g1"]["midi_pitch"] == 62 and atlas["g2"]["midi_pitch"] == 64
    assert atlas["a-hairpin"]["end_beat"] == 3.0
    assert atlas["a-hairpin"]["span"] > 250
    assert {p["role"] for p in atlas["a-volta"]["parts"]} == {"fixed", "span"}
    assert {p["role"] for p in atlas["g1"]["parts"]} == {"fixed"}


def test_matching_id_on_child_selects_complete_annotation_group(source_svg):
    root = ET.fromstring(source_svg)
    group = next(n for n in root.iter() if n.get("id") == "a-dynamic")
    group.set("id", "unrelated-group-id")
    next(n for n in group if n.tag.endswith("use")).set("id", "a-dynamic")
    model = score_model(); model["annotations"] = model["annotations"][:1]
    model["visual_events"] = []
    item = extractor()([ET.tostring(root, encoding="unicode")], model)["a-dynamic"]
    assert "unrelated-group-id" in item["parts"][0]["svg"]


def test_projection_kind_names_and_separate_slur_ownership(source_svg):
    model = score_model()
    for annotation in model["annotations"]:
        annotation["kind"] = {"dynamic": "dynamics", "hairpin": "wedge",
            "articulation": "articulations", "ornament": "ornaments"}.get(
                annotation["kind"], annotation["kind"])
    model["annotations"].append({"id": "owned-by-slurs", "kind": "slur"})
    atlas = extractor()([source_svg], model)
    assert "owned-by-slurs" not in atlas
    assert atlas["a-hairpin"]["kind"] == "wedge"


def projected_source(name="xml_expressions.musicxml"):
    import verovio
    from piano_teacher.importing.musicxml import load_musicxml
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model
    from piano_teacher.music import Phrase
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    piece = load_musicxml(ROOT/"tests/fixtures/musical_fidelity"/name, bpm=80)
    score = build_lesson_score(Phrase(1, 1, len(piece.bar_boundaries)-1,
        0, piece.bar_boundaries[-1], piece.notes),
        boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
        clef_changes=piece.clef_changes, barlines=piece.barlines, source_notation=piece.source_notation)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "svgViewBox": True,
        "svgBoundingBoxes": True, "svgContentBoundingBoxes": True, "breaks": "none"})
    assert toolkit.loadData(score.musicxml)
    return toolkit, model, score.musicxml


def test_actual_importer_projection_span_uses_exact_model_timing():
    toolkit, model, _ = projected_source()
    model["annotations"] = [a for a in model["annotations"] if a["kind"] == "wedge"]
    source = model["annotations"][0]
    item = extractor()([toolkit.renderToSVG(1)], model)[source["id"]]
    assert item["beat"] == 0.0 and item["end_beat"] == 8.0
    assert item["end_id"] == source["end_id"]
    assert item["voice"] == "xml-p0-s1-v1"
    assert item["parts"][0]["role"] == "span"


def test_actual_projection_all_annotation_ids_can_be_restored_before_engraving():
    toolkit, model, _ = projected_source()
    timemap = toolkit.renderToTimemap()
    import piano_teacher.notation.assets.annotations as annotations
    assert hasattr(annotations, "restore_annotation_ids"), "Verovio importer ID bridge is missing"
    assert annotations.restore_annotation_ids(toolkit, model) == len(model["annotations"])
    assert toolkit.renderToTimemap() == timemap
    atlas = annotations.annotation_fragments([toolkit.renderToSVG(1)], model)
    assert set(atlas) == {a["id"] for a in model["annotations"]}
    assert {item["kind"] for item in atlas.values()} == {
        "dynamics", "pedal", "wedge", "articulations", "ornaments"}
    for annotation in model["annotations"]:
        item = atlas[annotation["id"]]
        for key, value in annotation.items():
            assert item[key] == value


def test_musicxml_volta_and_grace_source_id_bridge():
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.annotations import restore_annotation_ids
    toolkit = _create_verovio_toolkit(verovio)
    toolkit.setOptions({"inputFrom": "xml", "svgViewBox": True, "breaks": "none"})
    assert toolkit.loadData((ROOT/"tests/fixtures/native_annotations.musicxml").read_text())
    model = score_model()
    timemap = toolkit.renderToTimemap()
    restore_annotation_ids(toolkit, model)
    assert toolkit.renderToTimemap() == timemap
    atlas = extractor()([toolkit.renderToSVG(1)], model)
    assert set(atlas) == {"a-dynamic", "a-hairpin", "a-pedal", "a-articulation",
                          "a-ornament", "a-volta", "g1", "g2"}


def test_paired_pedal_keeps_original_release_glyph_at_end_anchor(tmp_path):
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    mei = (ROOT/"tests/fixtures/native_annotations.mei").read_text()
    # Use the same real source as the contour test, with authentic Ped/*
    # symbols rather than a continuous pedal line.
    mei = mei.replace('form="line"', 'form="pedstar"')
    root = ET.fromstring(mei)
    xml_id = "{http://www.w3.org/XML/1998/namespace}id"
    release = next(n for n in root.iter() if n.tag.endswith("pedal") and n.get("dir") == "up")
    release.set(xml_id, "a-pedal-end")
    ET.register_namespace("", "http://www.music-encoding.org/ns/mei")
    toolkit = _create_verovio_toolkit(verovio)
    toolkit.setOptions({"inputFrom": "mei", "svgViewBox": True, "breaks": "none"})
    assert toolkit.loadData(ET.tostring(root, encoding="unicode"))
    model = score_model(); model["visual_events"] = []
    model["annotations"] = [a for a in model["annotations"] if a["kind"] == "pedal"]
    model["annotations"][0]["end_id"] = "a-pedal-end"
    atlas = extractor()([toolkit.renderToSVG(1)], model)
    item = atlas["a-pedal"]
    assert len(item["parts"]) == 2
    assert {part["role"] for part in item["parts"]} == {"fixed"}
    ending = next(p for p in item["parts"] if p.get("anchor") == 1.0)
    assert "a-pedal-end" in ending["svg"]
    assert_native_pixels(model, atlas, tmp_path)


@pytest.mark.parametrize("broken", ["missing", "empty", "duplicate", "anchor"])
def test_required_annotation_never_silently_disappears(source_svg, broken):
    model = score_model()
    root = ET.fromstring(source_svg)
    group = next(n for n in root.iter() if n.get("id") == "a-dynamic")
    if broken == "missing": group.set("id", "missing")
    if broken == "empty": group.clear(); group.set("id", "a-dynamic")
    if broken == "duplicate": root.append(copy.deepcopy(group))
    if broken == "anchor": model["visual_events"][0]["anchor_id"] = "unknown-source-note"
    with pytest.raises(ValueError):
        extractor()([ET.tostring(root, encoding="unicode")], model)


def test_cache_reuses_art_and_rejects_missing_required_fragment(source_svg, tmp_path):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    cache = PreprocessingCache(tmp_path)
    model = score_model()
    atlas = extractor()([source_svg], model, cache, "fixture")
    assert extractor()([source_svg], model, cache, "fixture") == atlas
    files = list(tmp_path.rglob("*.json.gz"))
    assert files
    for file in files:
        payload = json.loads(gzip.decompress(file.read_bytes()))
        if "a-dynamic" in payload["payload"]:
            del payload["payload"]["a-dynamic"]
            file.write_bytes(gzip.compress(json.dumps(payload).encode()))
    assert extractor()([source_svg], model, cache, "fixture") == atlas
    changed = copy.deepcopy(model); changed["annotations"][0]["beat"] = .25
    assert extractor()([source_svg], changed, cache, "fixture")["a-dynamic"]["beat"] == .25


def test_cache_rejects_corrupted_semantic_identity(source_svg, tmp_path):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    cache = PreprocessingCache(tmp_path)
    model = score_model()
    atlas = extractor()([source_svg], model, cache, "semantic-corruption")
    for file in tmp_path.rglob("*.json.gz"):
        payload = json.loads(gzip.decompress(file.read_bytes()))
        payload["payload"]["g2"]["midi_pitch"] = 127
        file.write_bytes(gzip.compress(json.dumps(payload).encode()))
    assert extractor()([source_svg], model, cache, "semantic-corruption") == atlas


def test_native_annotation_pixels_and_validation(source_svg, tmp_path):
    model = score_model()
    atlas = extractor()([source_svg], model)
    assert_native_pixels(model, atlas, tmp_path)


def test_actual_projection_native_pixels(tmp_path):
    toolkit, model, _ = projected_source()
    from piano_teacher.notation.assets.annotations import restore_annotation_ids
    restore_annotation_ids(toolkit, model)
    atlas = extractor()([toolkit.renderToSVG(1)], model)
    assert_native_pixels(model, atlas, tmp_path)


def test_advanced_projection_ending_and_single_grace_native_pixels(tmp_path):
    toolkit, model, _ = projected_source("xml_advanced.musicxml")
    from piano_teacher.notation.assets.annotations import restore_annotation_ids
    restore_annotation_ids(toolkit, model)
    atlas = extractor()([toolkit.renderToSVG(1)], model)
    assert {a["kind"] for a in atlas.values()} == {"ending", "grace"}
    assert len(atlas) == 2
    assert_native_pixels(model, atlas, tmp_path)


def test_native_annotation_interval_culling_with_many_marks_and_long_span(source_svg, tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot unavailable")
    atlas = extractor()([source_svg], score_model())
    fixture = tmp_path/"culling.json"
    fixture.write_text(json.dumps({"annotation_fragments": atlas}))
    result = subprocess.run([binary, "--windowed", "--resolution", "1000x700",
        "--rendering-method", "gl_compatibility", "--path", str(ROOT/"godot"),
        "--script", str(ROOT/"tests/godot/native_annotations_culling.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION":"1",
             "PIANO_TEACHER_ANNOTATIONS_FIXTURE":str(fixture)},
        text=True, capture_output=True, timeout=60)
    output = result.stdout+result.stderr
    for line in output.splitlines():
        if line.startswith("NATIVE_ANNOTATION_CULL_"):
            print(line)
    assert result.returncode == 0, output
    assert "NATIVE_ANNOTATION_CULL_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output


def assert_native_pixels(model, atlas, tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary: pytest.skip("Godot unavailable")
    fixture = tmp_path / "annotations.json"
    fixture.write_text(json.dumps({"model": model, "annotation_fragments": atlas}))
    result = subprocess.run([binary, "--path", str(ROOT/"godot"), "--windowed",
        "--resolution", "1100x700", "--rendering-method", "gl_compatibility",
        "--script", str(ROOT/"tests/godot/native_annotations_pixels.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
             "PIANO_TEACHER_ANNOTATIONS_FIXTURE": str(fixture)},
        text=True, capture_output=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_ANNOTATION_PIXEL_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
