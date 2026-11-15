"""Cross-component musical spacing and forward tempo acceptance in actual Godot.

This catches different components introducing their own pixels-per-beat,
lookahead or staff-size defaults while retaining source-note beat identity.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 not installed")
def test_timing_geometry_scales_uniformly_through_mixed_meter_and_tempo():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/timing_geometry_contract.gd")],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    assert "TIMING_GEOMETRY_FAILURES:0" in output, output


def test_spacing_policy_remains_a_pure_constant_owner():
    """No renderer, clock, or MIDI control belongs in the tuning constants."""
    source = (ROOT / "godot/notation/shared/spacing_policy.gd").read_text()
    assert source.startswith("extends RefCounted\n")
    assert "preload(" not in source and "func " not in source
    assert "var " not in source and "signal " not in source
    import re
    default = re.search(r"const DEFAULT_PIXELS_PER_BEAT := ([0-9.]+)", source)
    assert default is not None and 24 <= float(default.group(1)) <= 480
    for name in ("MAX_STAFF_GAP", "MIN_READABLE_STAFF_GAP",
                 "MIN_LOOKAHEAD_BEATS"):
        assert f"const {name} :=" in source


def test_no_independent_numeric_copies_of_shared_spacing_limits():
    """A new renderer must consume the shared policy instead of cloning it."""
    import re

    godot = ROOT / "godot"
    shared = godot / "notation/shared/spacing_policy.gd"
    names = ("DEFAULT_PIXELS_PER_BEAT", "MAX_STAFF_GAP",
             "MIN_READABLE_STAFF_GAP", "MIN_LOOKAHEAD_BEATS",
             "MIN_READING_BEATS")
    numeric_definition = re.compile(
        r"^\s*const\s+(" + "|".join(names) + r")\s*:=\s*[-+]?[0-9]",
        re.MULTILINE,
    )
    duplicates = []
    for path in godot.rglob("*.gd"):
        if path == shared or "addons" in path.parts:
            continue
        if numeric_definition.search(path.read_text()):
            duplicates.append(path.relative_to(ROOT).as_posix())
    assert not duplicates, "Independent timing/spacing policy copies: " + ", ".join(duplicates)


def test_header_clearance_is_derived_from_the_actual_header_painter():
    view = (ROOT / "godot/notation/native/view.gd").read_text()
    painter = (ROOT / "godot/notation/native/context_painter.gd").read_text()
    assert view.count("ContextPainter.clef_lead_pixels(") == 2
    assert "clef_lead_pixels(key_columns,gap)" in painter
    assert "HEADER_KEY_COLUMN_UNITS" in painter


def test_first_party_godot_cannot_reimplement_bpm_second_arithmetic():
    """The cross-language presentation client has one beat-unit conversion."""
    from runpy import run_path

    audit = run_path(str(ROOT / "scripts/audit-musical-scheduler.py"))
    scan = audit["_gd_direct_bpm_conversions"]
    assert scan("var beat = elapsed * bpm / 60000.0") == [1]
    assert scan("var seconds = pulse*60.0/plan_bpm") == [1]
    assert scan("var ticks = milliseconds * next_bpm / 60000") == [1]
    assert scan('var bpm = float(state.get("bpm",60.0))') == []
    assert scan("const PEER_MARGIN_PX := 60.0") == []
    for path in (ROOT / "godot").rglob("*.gd"):
        if "addons" in path.parts or path.name == "tempo_timeline.gd":
            continue
        assert scan(path.read_text()) == [], (
            f"Independent beat-time conversion: {path.relative_to(ROOT)}")


def test_staff_and_ledger_rails_share_painter_metrics():
    view = (ROOT / "godot/notation/native/view.gd").read_text()
    painter = (ROOT / "godot/notation/native/symbol_painter.gd").read_text()
    assert "const STAFF_LINE_WIDTH := 1.15" in painter
    assert "const STAFF_LINE_ALPHA := .48" in painter
    assert view.count("SymbolPainter.STAFF_LINE_WIDTH") >= 2
    assert "SymbolPainter.STAFF_LINE_ALPHA if selected else .28" in view


def test_future_engraving_queue_and_lookahead_have_one_capacity():
    from piano_teacher.application.future_score import MAX_LOOKAHEAD, MAX_QUEUED

    assert MAX_QUEUED == MAX_LOOKAHEAD
    assert MAX_LOOKAHEAD > 0
