"""Evidence-integrity regressions; these fixtures are not a passing corpus."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/package_notation_evidence.py"
SOURCE = "tests/fixtures/musical_fidelity/xml_pickup.musicxml"
REVISION = "a" * 40


def packager():
    assert SCRIPT.is_file(), "Phase4 evidence packager has not been implemented"
    spec = importlib.util.spec_from_file_location("phase4_packager", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Authored integrity fixtures use fixed version hashes, not real captures.
    module.capture_dependency_hash = lambda root: "d" * 64
    module.capture_protocol_hash = lambda root: "c" * 64
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def visual_case(tmp_path, *, windows=((1, 2),), raw_prefix="phase3-report"):
    reports, raw, out = (tmp_path / name for name in ("reports", "raw", "out"))
    compact = reports / "phase3-report-7-both"
    full = raw / f"{raw_prefix}-7-both"
    score = {"piece": SOURCE, "hand": "both", "measures_expected": 2,
             "windows": [{"first_bar": first, "last_bar": last,
                          "whole_window_coverage": {"screenshot_count": last-first+1}}
                         for first, last in windows]}
    report = {"schema_version": 1, "verification_kind": "visual", "source_index": 7,
              "source": SOURCE, "source_sha256": digest(ROOT / SOURCE), "hand": "both",
              "passed": False, "complete": False, "scores": [score],
              "environment": {"godot": "fixture-godot"},
              "elements": [{"id": "original:note", "construct": "notehead",
                            "status": "unverified", "source": {"measure_index": 1}}]}
    write_json(compact / "summary.json", report)
    write_json(full / "summary.json", report)
    for window_index, (first, last) in enumerate(windows):
        folder = full / "xml_pickup" / f"measures-{first:03}-{last:03}"
        folder.mkdir(parents=True)
        shutil.copyfile(ROOT / SOURCE, folder / "score.musicxml")
        beats = list(range(first-1, last))
        write_json(folder / "fixture.json", {"model": {"active_hand": "both"},
                   "first_bar": first, "last_bar": last, "hand": "both", "sample_beats": beats,
                   "capture_protocol_sha256": "c" * 64})
        write_json(folder / "independent-pixels.json", {"measured": [], "failures": []})
        write_json(folder / "independent-rests.json", {"measured": [], "failures": []})
        frames = []
        captures = []
        for beat in beats:
            name = f"native-{beat:.5f}.png"
            Image.new("RGB", (120, 80), (16, 41, 35)).save(folder / name)
            captures.append({"file": name, "sha256": digest(folder / name)})
            frames.append({"clock": beat, "file": name})
        write_json(folder / "native-overlay-report.json", {"frames": frames})
        write_json(folder / "capture-manifest.json", {"screenshots": captures,
                   "capture_protocol_sha256": "c" * 64,
                   "renderer_dependencies_sha256": "d" * 64, "godot": "fixture-godot"})
        (folder / "verovio-0.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        Image.new("RGB", (120, 80), "white").save(folder / "verovio-0.png")
        (folder / "godot.log").write_text("capture completed\n")
        write_json(folder / "audit.json", {"source": f"{SOURCE}, measures {first}-{last}, both",
                   "whole_window_coverage": score["windows"][window_index]["whole_window_coverage"]})
    (full / "runner.log").write_text("audit blocked: unverified notation\n")
    return reports, raw, out, compact, full


def selected(manifest, kind="visual", index=7, hand="both"):
    return next(case for case in manifest["cases"] if
                (case["verification_kind"], case["source_index"], case["hand"]) == (kind, index, hand))


def test_missing_reports_still_emit_all_102_required_cases(tmp_path):
    result = packager().package_evidence(tmp_path / "reports", tmp_path / "raw", tmp_path / "out", REVISION)
    assert len(result["cases"]) == 102
    assert not result["complete"]
    assert all(not case["complete"] and case["errors"] for case in result["cases"])
    assert selected(result)["report_sha256"] is None
    assert json.loads((tmp_path / "out/evidence-manifest.json").read_text()) == result


@pytest.mark.parametrize("raw_prefix", ["phase3-report", "phase3-visual-score"])
def test_exact_reports_revision_all_raw_bytes_and_nonverified_rows_retained(tmp_path, raw_prefix):
    reports, raw, out, compact, full = visual_case(tmp_path, raw_prefix=raw_prefix)
    (full / "extra-control.bin").write_bytes(b"do not discard raw evidence")
    result = packager().package_evidence(reports, raw, out, REVISION)
    case = selected(result)
    assert result["schema_version"] == 1 and result["revision"] == REVISION
    assert not result["complete"]  # The other 101 cases are absent.
    assert case["complete"], case["errors"]  # Packaging completeness, not notation certification.
    assert case["report_sha256"] == digest(compact / "summary.json")
    assert case["source_sha256"] == digest(ROOT / SOURCE)
    files = case["files"]
    assert {"report", "original", "generated", "model", "reference_svg", "reference_png",
            "native_png", "independent_pixels", "independent_rests", "capture_manifest", "log"} <= {f["role"] for f in files}
    for entry in files:
        assert not Path(entry["path"]).is_absolute()
        assert digest(out / entry["path"]) == entry["sha256"]
    retained = next(out / f["path"] for f in files if f["role"] == "report")
    assert retained.read_bytes() == (compact / "summary.json").read_bytes()
    assert json.loads(retained.read_text())["elements"][0]["status"] == "unverified"
    assert any((out / f["path"]).read_bytes() == b"do not discard raw evidence"
               for f in files if f["path"].endswith("extra-control.bin"))


@pytest.mark.parametrize("missing, expected", [
    ("verovio-0.svg", "reference_svg"), ("verovio-0.png", "reference_png"),
    ("native-0.00000.png", "native"), ("independent-pixels.json", "independent_pixels"),
    ("independent-rests.json", "independent_rests"), ("capture-manifest.json", "capture_manifest"),
    ("fixture.json", "model"), ("score.musicxml", "generated"), ("godot.log", "log"),
])
def test_unrelated_window_cannot_supply_missing_required_class(tmp_path, missing, expected):
    reports, raw, out, _, full = visual_case(tmp_path, windows=((1, 1), (2, 2)))
    (full / "xml_pickup/measures-002-002" / missing.replace("0.00000", "1.00000")).unlink()
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert "window 2-2" in " ".join(case["errors"])
    assert expected in " ".join(case["errors"])


@pytest.mark.parametrize("field,value", [("source_index", True), ("hand", "left"),
    ("source", "other.musicxml"), ("source_sha256", "0" * 64), ("verification_kind", "semantic")])
def test_report_identity_cannot_override_pinned_case(tmp_path, field, value):
    reports, raw, out, compact, _ = visual_case(tmp_path)
    data = json.loads((compact / "summary.json").read_text()); data[field] = value
    write_json(compact / "summary.json", data)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"] and any("identity" in e or "source_sha256" in e for e in case["errors"])


def test_raw_summary_must_bind_to_exact_compact_report_bytes(tmp_path):
    reports, raw, out, _, full = visual_case(tmp_path)
    path = full / "summary.json"
    path.write_text(path.read_text() + "\n")
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert "report digest" in " ".join(case["errors"])


def test_capture_hash_and_each_expected_frame_are_required(tmp_path):
    reports, raw, out, _, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    Image.new("RGB", (120, 80), "red").save(folder / "native-0.00000.png")
    path = folder / "capture-manifest.json"
    manifest = json.loads(path.read_text()); manifest["screenshots"].pop()
    write_json(path, manifest)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert "hash" in " ".join(case["errors"]) and "native-1.00000.png" in " ".join(case["errors"])


def test_duplicate_json_and_symlink_escape_are_blocked(tmp_path):
    reports, raw, out, compact, full = visual_case(tmp_path)
    p = compact / "summary.json"
    p.write_text(p.read_text()[:-1] + ', "hand": "both"}')
    outside = tmp_path / "secret.txt"; outside.write_text("unrelated secret")
    (full / "escape.log").symlink_to(outside)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert "duplicate" in " ".join(case["errors"]).lower()
    assert "symlink" in " ".join(case["errors"]).lower()
    assert not any(f["path"].endswith("escape.log") for f in case["files"])


def test_semantic_original_and_declared_artifacts_are_hash_validated(tmp_path):
    reports, raw, out = (tmp_path / n for n in ("reports", "raw", "out"))
    folder = reports / "phase3-semantic-report-7-both"; folder.mkdir(parents=True)
    shutil.copyfile(ROOT / SOURCE, folder / "original.musicxml")
    (folder / "generated.musicxml").write_bytes(b"generated")
    write_json(folder / "model.json", {"active_hand": "both"})
    report = {"schema_version": 1, "verification_kind": "semantic", "source_index": 7,
              "source": SOURCE, "source_sha256": digest(ROOT / SOURCE), "hand": "both",
              "artifacts": {k: {"path": name, "sha256": digest(folder / name)} for k, name in
                            (("original", "original.musicxml"), ("generated", "generated.musicxml"), ("native", "model.json"))}}
    write_json(folder / "summary.json", report)
    (folder / "original.musicxml").write_bytes(b"substituted source")
    case = selected(packager().package_evidence(reports, raw, out, REVISION), "semantic")
    assert not case["complete"]
    assert "original" in " ".join(case["errors"]) and "hash" in " ".join(case["errors"])


def test_output_is_immutable_and_cli_rejects_short_revision(tmp_path):
    module = packager()
    with pytest.raises(ValueError, match="revision"):
        module.package_evidence(tmp_path / "reports", tmp_path / "raw", tmp_path / "out", "abc123")
    result = module.package_evidence(tmp_path / "reports", tmp_path / "raw", tmp_path / "out", REVISION)
    with pytest.raises(ValueError, match="empty|immutable"):
        module.package_evidence(tmp_path / "reports", tmp_path / "raw", tmp_path / "out", "b" * 40)
    assert json.loads((tmp_path / "out/evidence-manifest.json").read_text()) == result
    proc = subprocess.run([sys.executable, str(SCRIPT), "--reports", str(tmp_path / "reports"),
                           "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "cli"),
                           "--revision", "abc123"], capture_output=True)
    assert proc.returncode == 2


@pytest.mark.parametrize("mutation", ["bytes", "role", "remove", "report", "revision", "window_role"])
def test_consumer_revalidates_bytes_roles_reports_windows_and_revision(tmp_path, mutation):
    reports, raw, out, compact, _ = visual_case(tmp_path)
    module = packager()
    manifest = module.package_evidence(reports, raw, out, REVISION)
    case = selected(manifest)
    assert case["complete"], case["errors"]
    before = module.validate_manifest(out / "evidence-manifest.json", reports, REVISION)
    assert selected(before)["complete"], selected(before)["errors"]
    entry = next(f for f in case["files"] if f["role"] == "native_png")
    if mutation == "bytes":
        (out / entry["path"]).write_bytes(b"tampered screenshot")
    elif mutation == "role":
        entry["role"] = "reference_png"
    elif mutation == "remove":
        case["files"].remove(entry)
    elif mutation == "window_role":
        entry["path"] = entry["path"].replace("measures-001-002", "measures-999-999")
        replacement = out / entry["path"]; replacement.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80)).save(replacement); entry["sha256"] = digest(replacement)
    elif mutation == "report":
        path = compact / "summary.json"; path.write_text(path.read_text() + "\n")
    else:
        manifest["revision"] = "b" * 40
    manifest["complete"] = True
    manifest["errors"] = []
    for row in manifest["cases"]:
        row["complete"] = True; row["errors"] = []
    write_json(out / "evidence-manifest.json", manifest)
    checked = module.validate_manifest(out / "evidence-manifest.json", reports, REVISION)
    assert not checked["complete"]
    assert checked["errors"]
    if mutation != "revision":
        assert not selected(checked)["complete"], selected(checked)


def test_validator_cannot_accept_omitted_or_duplicate_cases(tmp_path):
    reports, raw, out, _, _ = visual_case(tmp_path)
    module = packager(); manifest = module.package_evidence(reports, raw, out, REVISION)
    case = selected(manifest)
    manifest["cases"] = [case, case]
    manifest["complete"] = True
    write_json(out / "evidence-manifest.json", manifest)
    checked = module.validate_manifest(out / "evidence-manifest.json", reports, REVISION)
    assert len(checked["cases"]) == 102
    assert not checked["complete"]
    assert "duplicate" in " ".join(checked["errors"]).lower()


def diagnostic_captures(folder):
    from io import BytesIO
    import cairosvg
    from piano_teacher.notation.reference_font import reference_glyphs

    folder.mkdir()
    (folder / "score.musicxml").write_text('''<score-partwise><part-list>
      <score-part id="RH"><part-name>Right</part-name></score-part></part-list>
      <part id="RH"><measure number="1"><attributes><divisions>1</divisions>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note id="n"><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>
      <voice>1</voice><type>quarter</type></note>
      <note id="r"><rest/><duration>4</duration><voice>1</voice><type>whole</type></note>
      </measure></part></score-partwise>''')
    bg = Image.new("RGB", (1536, 520), (16, 41, 35))
    draw = ImageDraw.Draw(bg)
    for y in (120, 140, 160, 180, 200, 320, 340, 360, 380, 400):
        draw.line((0, y, 1535, y), fill=(73, 83, 77))
    glyphs = reference_glyphs()
    for beat, name, y in ((0, "head_black", 220), (1, "rest_whole", 160)):
        glyph = glyphs[name]; bounds = glyph["bounds"]
        width, height = round(bounds[2]*20/250), round(bounds[3]*20/250)
        mask = Image.open(BytesIO(cairosvg.svg2png(bytestring=glyph["svg"].encode(),
                         output_width=width, output_height=height))).convert("RGBA")
        image = bg.convert("RGBA")
        image.alpha_composite(mask, (round(1536*.42-width/2), round(y+bounds[1]*20/250)))
        image.convert("RGB").save(folder / f"native-{beat:.5f}.png")
        if beat == 1:
            image.convert("RGB").save(folder / "repeat.png")
            image.convert("RGB").save(folder / "restored.png")
            bg.save(folder / "without.png")
    write_json(folder / "fixture.json", {"assets": {"native_glyphs": {"head_black": "corrupt atlas"}}})
    write_json(folder / "native-overlay-report.json", {"staff_gap": 9999,
               "frames": [{"clock": 0, "noteheads": {"n": [-999, -999]}}],
               "rest_difference_protocol": 2,
               "rest_difference_frames": [{"clock": 1, "repeat_file": "repeat.png", "restored_file": "restored.png"}]})
    write_json(folder / "independent-pixels.json", {"measured": [
        {"source_id": "n", "measure": 1, "beat": 0, "staff": "right", "voice": "1",
         "spelling": ["C", 0, 4], "status": "unverified", "glyph": "head_black"}],
        "failures": ["representative failure"]})
    write_json(folder / "independent-rests.json", {"measured": [
        {"source_id": "r", "measure": 1, "beat": 1, "staff": "right", "voice": "1",
         "required_rest": "whole", "status": "ambiguous", "delta_file": "without.png"}],
        "failures": []})
    return folder


def diagnostics_module():
    path = ROOT / "piano_teacher/notation/release_diagnostics.py"
    assert path.exists(), "symbol diagnostics have not been implemented"
    from piano_teacher.notation import release_diagnostics
    return release_diagnostics


def test_authentic_glyph_diagnostics_ignore_native_atlas_and_keep_original_statuses(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    output = tmp_path / "diagnostics"
    data = diagnostics_module().create_diagnostics(folder, output, hand="both", limit=2)
    assert data["derived"] is True and data["verification_evidence"] is False
    assert len(data["symbols"]) == 2
    assert {r["status"] for r in data["symbols"]} == {"unverified", "ambiguous"}
    assert len(data["exemplars"]) == 2
    assert {r["source_status"] for r in data["exemplars"]} == {"unverified", "ambiguous"}
    for row in data["exemplars"]:
        assert row["diagnostic_status"] == "available", row
        assert row["font"] == "Leipzig"
        assert row["derived"] is True and row["verification_evidence"] is False
        assert row["reference_sha256"] == digest(output / row["reference"])
        assert row["native_sha256"] == digest(folder / row["native"])
        for name in ("reference", "overlay", "delta"):
            assert (output / row[name]).is_file()
    assert json.loads((output / "diagnostics.json").read_text()) == data


def test_missing_or_contaminated_control_never_manufactures_rest_diagnostic_proof(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    (folder / "without.png").unlink()
    data = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", hand="both", limit=1)
    row = data["exemplars"][0]
    assert row["kind"] == "rest"  # The ambiguous failure is selected ahead of a note.
    assert row["source_status"] == "ambiguous"
    assert row["diagnostic_status"] == "unverified"
    assert not row["verification_evidence"]
    assert "delta" not in row


def test_packager_emits_symbol_rows_and_derived_diagnostic_index(tmp_path):
    reports, raw, out, _, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    write_json(folder / "independent-pixels.json", {"measured": [
        {"source_id": "n", "measure": 1, "beat": 0, "staff": "right", "voice": "1",
         "status": "unverified", "reason": "missing silhouette"}], "failures": ["failure"]})
    result = packager().package_evidence(reports, raw, out, REVISION)
    case = selected(result)
    assert any(f["role"] == "diagnostic" and f["path"].endswith("diagnostics.json") for f in case["files"])
    index = next(out / f["path"] for f in case["files"] if f["role"] == "diagnostic" and f["path"].endswith("diagnostics.json"))
    data = json.loads(index.read_text())
    assert data["symbols"][0]["status"] == "unverified"
    assert not data["verification_evidence"]


@pytest.mark.parametrize("mutation", ["dependencies", "protocol", "godot"])
def test_current_capture_code_hashes_and_report_engine_are_required(tmp_path, mutation):
    reports, raw, out, _, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    capture = json.loads((folder / "capture-manifest.json").read_text())
    if mutation == "dependencies":
        capture["renderer_dependencies_sha256"] = "0" * 64
    elif mutation == "protocol":
        capture["capture_protocol_sha256"] = "0" * 64
        fixture = json.loads((folder / "fixture.json").read_text())
        fixture["capture_protocol_sha256"] = "0" * 64
        write_json(folder / "fixture.json", fixture)
    else:
        capture["godot"] = "old-engine"
    write_json(folder / "capture-manifest.json", capture)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert {"dependencies": "current renderer", "protocol": "current capture protocol", "godot": "Godot"}[mutation] in " ".join(case["errors"])


def test_diagnostic_limit_represents_distinct_failure_kinds_and_statuses(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    notes = json.loads((folder / "independent-pixels.json").read_text())
    note = notes["measured"][0]
    notes["measured"] = [{**note, "status": "ambiguous", "source_id": str(i)} for i in range(8)]
    write_json(folder / "independent-pixels.json", notes)
    rests = json.loads((folder / "independent-rests.json").read_text())
    rests["measured"][0]["status"] = "unverified"
    write_json(folder / "independent-rests.json", rests)
    result = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", limit=2)
    assert {(row["kind"], row["source_status"]) for row in result["exemplars"]} == {
        ("notehead", "ambiguous"), ("rest", "unverified")}
    assert len(result["symbols"]) == 9


def test_dark_frame_drift_invalidates_rest_delta_diagnostic(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    with Image.open(folder / "without.png") as image:
        control = image.convert("RGB")
    ImageDraw.Draw(control).rectangle((1000, 100, 1010, 110), fill="black")
    control.save(folder / "without.png")
    result = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", limit=1)
    assert result["exemplars"][0]["diagnostic_status"] == "unverified"
    assert "delta" not in result["exemplars"][0]


def test_consumer_recomputes_current_renderer_version_hash(tmp_path):
    reports, raw, out, _, _ = visual_case(tmp_path)
    module = packager()
    module.package_evidence(reports, raw, out, REVISION)
    module.capture_dependency_hash = lambda root: "0" * 64
    checked = module.validate_manifest(out / "evidence-manifest.json", reports, REVISION)
    assert not selected(checked)["complete"]
    assert "current renderer" in " ".join(selected(checked)["errors"])


@pytest.mark.parametrize("mutation", ["source", "witness", "pixels"])
def test_window_audit_and_independent_json_bind_exact_compact_witness(tmp_path, mutation):
    reports, raw, out, compact, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    audit = json.loads((folder / "audit.json").read_text())
    if mutation == "source":
        audit["source"] = "other.musicxml, measures 1-2, both"
    elif mutation == "witness":
        audit["whole_window_coverage"]["screenshot_count"] = 1
    else:
        report = json.loads((compact / "summary.json").read_text())
        report["scores"][0]["windows"][0]["whole_window_coverage"]["independent_image_pitch"] = {"failures": []}
        write_json(compact / "summary.json", report)
        write_json(full / "summary.json", report)
        audit["whole_window_coverage"] = report["scores"][0]["windows"][0]["whole_window_coverage"]
        write_json(folder / "independent-pixels.json", {"measured": [], "failures": ["substituted proof"]})
    write_json(folder / "audit.json", audit)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert not case["complete"]
    assert "compact" in " ".join(case["errors"]) or "source/window" in " ".join(case["errors"])


def test_outer_source_inventory_need_not_be_present_in_earlier_capture_audit(tmp_path):
    reports, raw, out, compact, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    original_audit = (folder / "audit.json").read_bytes()
    report = json.loads((compact / "summary.json").read_text())
    report["scores"][0]["windows"][0]["whole_window_coverage"]["elements"] = report["elements"]
    write_json(compact / "summary.json", report)
    write_json(full / "summary.json", report)
    case = selected(packager().package_evidence(reports, raw, out, REVISION))
    assert case["complete"], case["errors"]
    retained = next(out / f["path"] for f in case["files"] if f["path"].endswith("raw/xml_pickup/measures-001-002/audit.json"))
    assert retained.read_bytes() == original_audit


@pytest.mark.parametrize("mutation", ["truncate", "duplicate", "status", "pixel"])
def test_consumer_rejects_lost_or_changed_symbol_observations_even_with_updated_hashes(tmp_path, mutation):
    reports, raw, out, compact, full = visual_case(tmp_path)
    folder = full / "xml_pickup/measures-001-002"
    rows = [{"source_id": f"n{i}", "measure": 1, "beat": i, "staff": "right", "voice": "1",
             "status": "unverified", "reason": "missing silhouette"} for i in range(2)]
    summary = {"written_active_noteheads": 2, "image_pitch_verified": 0, "failures": [],
               "coverage": {"expected": 2, "verified": 0, "ambiguous": 0, "unsupported": 0, "unverified": 2, "mismatch": 0}}
    write_json(folder / "independent-pixels.json", {**summary, "measured": rows})
    report = json.loads((compact / "summary.json").read_text())
    window = report["scores"][0]["windows"][0]
    window["whole_window_coverage"]["independent_image_pitch"] = summary
    window["visual_elements"] = [{"evidence": {"pixel": rows[0]}}]
    write_json(compact / "summary.json", report)
    write_json(full / "summary.json", report)
    write_json(folder / "audit.json", {"source": f"{SOURCE}, measures 1-2, both",
               "whole_window_coverage": window["whole_window_coverage"]})
    module = packager(); manifest = module.package_evidence(reports, raw, out, REVISION)
    case = selected(manifest)
    assert case["complete"], case["errors"]
    entry = next(f for f in case["files"] if f["role"] == "independent_pixels")
    path = out / entry["path"]
    proof = json.loads(path.read_text())
    if mutation == "truncate": proof["measured"] = []
    elif mutation == "duplicate": proof["measured"][1] = proof["measured"][0]
    elif mutation == "status": proof["measured"][1]["status"] = "verified"
    else: proof["measured"][0]["reason"] = "changed original observation"
    write_json(path, proof); entry["sha256"] = digest(path)
    write_json(out / "evidence-manifest.json", manifest)
    checked = selected(module.validate_manifest(out / "evidence-manifest.json", reports, REVISION))
    assert not checked["complete"]
    assert "observation" in " ".join(checked["errors"])
