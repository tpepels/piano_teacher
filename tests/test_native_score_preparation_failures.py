"""Native score preparation cannot substitute empty fragments for failed ink.

Pure injection of the exact asset-module imports keeps this safety test
independent of heavyweight Verovio, Pillow, music21 and a desktop renderer.
"""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from piano_teacher.application.score_preparation import (
    NativeScorePreparationError, assemble_layout,
)


ASSETS = {
    "glyphs": ("native_glyphs", "preparation_symbols"),
    "notes": ("note_templates",),
    "ties": ("tie_templates",),
    "beams": ("beam_fragments", "expected_beam_groups"),
    "chords": ("chord_templates",),
    "tuplets": ("tuplet_fragments",),
    "slurs": ("slur_fragments", "slur_pairs_from_xml"),
}


def _stub_assets(monkeypatch, failed=None):
    for module, exports in ASSETS.items():
        fake = ModuleType(f"piano_teacher.notation.assets.{module}")
        for name in exports:
            def routine(*_args, _name=name, **_kwargs):
                if _name == failed:
                    raise RuntimeError(f"injected {_name} failure")
                return () if _name in {"expected_beam_groups", "slur_pairs_from_xml"} else {}
            setattr(fake, name, routine)
        monkeypatch.setitem(sys.modules, fake.__name__, fake)


@pytest.mark.parametrize(("module", "function", "stage"), [
    ("ties", "tie_templates", "tie templates"),
    ("beams", "expected_beam_groups", "beam fragments"),
    ("beams", "beam_fragments", "beam fragments"),
    ("chords", "chord_templates", "chord templates"),
    ("tuplets", "tuplet_fragments", "tuplet fragments"),
    ("slurs", "slur_pairs_from_xml", "slur fragments"),
    ("slurs", "slur_fragments", "slur fragments"),
])
def test_fragment_failure_is_actionable_and_never_returns_partial_score(
        monkeypatch, module, function, stage):
    _stub_assets(monkeypatch, failed=function)
    source = SimpleNamespace(layout={"source": "unchanged"}, pages=("<svg/>",))
    with pytest.raises(NativeScorePreparationError,
                       match=stage + " preparation failed") as error:
        assemble_layout(source, native_model={"notation_events": []},
                        notation_xml="<score-partwise/>", revision=17)
    assert "injected " + function + " failure" in str(error.value)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert source.layout == {"source": "unchanged"}


def test_complete_fragments_can_publish_empty_sets_when_no_symbols_are_required(
        monkeypatch):
    _stub_assets(monkeypatch)
    source = SimpleNamespace(layout={"source": "unchanged"}, pages=("<svg/>",))
    result = assemble_layout(source, native_model={"notation_events": []},
                             notation_xml="<score-partwise/>", revision=17)
    assert result["revision"] == 17
    assert result["native_beams_complete"] is True
    assert result["native_slurs_complete"] is True
    assert result["native_beam_fragments"] == {}
    assert result["native_tuplet_fragments"] == {}
    assert source.layout == {"source": "unchanged"}
