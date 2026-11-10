"""Consumers of canonical curriculum assets and the native application smoke."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import check_native_verovio_overlay as audit
from scripts.audits import case_catalog, case_inputs
from piano_teacher.importing.pieces import import_piece

ROOT = Path(__file__).resolve().parents[1]


def test_ala_measure_nine_curriculum_uses_canonical_native_assets():
    path, = case_catalog.library_sources(only="Ala")
    piece, _ = import_piece(path)
    cases = [(case, source, variant)
             for case, source, variant in case_catalog.curriculum_cases(path, piece)
             if case.name.startswith("learn-") and source.first_bar <= 9 <= source.last_bar]
    stages = {(case.hand, variant.level) for case, _, variant in cases}
    assert stages == {("right", "original"), ("left", "skeleton"),
                      ("left", "original"), ("both", "original")}
    for case, source, variant in cases:
        assert not case_inputs.variant_errors(source, variant)
        payload, _ = audit.fixture(case, piece=piece, phrase=variant.phrase)
        assert not payload["source_errors"]
        assert payload["model"]["active_hand"] == case.hand
        assert payload["model"]["notes"]
        assert payload["assets"]["native_glyphs"]
        assert payload["assets"]["native_note_templates"]


def test_peace_piece_cross_bar_attack_keeps_exact_canonical_source_timing():
    path, = case_catalog.library_sources(only="Peace_Piece")
    piece, _ = import_piece(path)
    case, source, variant = next(
        (case, source, variant)
        for case, source, variant in case_catalog.curriculum_cases(path, piece)
        if case.name.startswith("learn-") and source.first_bar <= 57 <= source.last_bar
        and case.hand == "both" and variant.level == "original")
    assert not case_inputs.variant_errors(source, variant)
    payload, _ = audit.fixture(case, piece=piece, phrase=variant.phrase)
    assert not payload["source_errors"]
    attack, = [n for n in payload["model"]["notes"] if n["id"] == "midi-t0-e2015"]
    # Source measure 57 ends at beat 4; this attack must not snap to that barline.
    assert attack["onset_beats"] == pytest.approx(3.99375, abs=1e-8)
    assert attack["duration_beats"] == pytest.approx(.00625, abs=1e-8)
