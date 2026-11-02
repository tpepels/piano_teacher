"""All independent MIDI fixtures: every emitted stage has traceable source notes."""
import json
from pathlib import Path
import pytest

from piano_teacher.music import load_midi
from piano_teacher.research.coda_live_note_audit import audit_coda_midi

ROOT=Path(__file__).parent/"fixtures/musical_fidelity"
MANIFEST=json.loads((ROOT/"manifest.json").read_text())
MIDI=[row["file"] for row in MANIFEST["supported"]
      if row["file"].lower().endswith((".mid",".midi"))]


@pytest.mark.parametrize("name",MIDI,ids=MIDI)
def test_every_production_coda_stage_has_exact_source_and_grading_clock(name):
    piece=load_midi(ROOT/name)
    audit=audit_coda_midi(piece)
    assert audit.all_source_attacks_in_final
    assert audit.source_attacks==len(piece.notes)
    assert audit.stages
    assert sum(s.written_attacks for s in audit.stages)>0
    assert "original" in audit.categories
    for stage in audit.stages:
        assert 0<stage.written_attacks<=stage.source_attacks
        assert stage.changed_attacks<=stage.written_attacks
        assert stage.total_seconds>0
    assert all("source" in item and "attacks" in item
               for item in ({"source":s.key,"attacks":s.written_attacks}
                            for s in audit.stages))
    assert audit.as_dict()["note_level_meaning"].endswith(
        "not original MusicXML parity")


def test_negative_duplicate_source_ids_do_not_pass_audit():
    from dataclasses import replace
    p=load_midi(ROOT/"midi_four_four.mid")
    bad=replace(p,notes=(p.notes[0],replace(p.notes[1],
        source_id=p.notes[0].source_id))+p.notes[2:])
    with pytest.raises(ValueError,match="[Dd]uplicate"):
        audit_coda_midi(bad)


def test_source_is_not_claimed_to_have_original_written_parity():
    p=load_midi(ROOT/"midi_three_four.mid")
    report=audit_coda_midi(p).as_dict()
    assert "not original MusicXML parity" in report["note_level_meaning"]
    assert "dotted" in report["categories"] or "slowed" in report["categories"]
