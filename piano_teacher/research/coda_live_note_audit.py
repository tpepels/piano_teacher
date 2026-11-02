"""Audit EVERY emitted production Coda-MIDI stage against original MIDI.

This is *note ownership and executable timing* evidence, NOT evidence that
the author produced identical MusicXML. Some author-generated notation is
known to be unsafe or uses a different written-time representation.

The audit is intentionally independent of Coda generation algorithms: it
consumes the finished LearningPlan, authentic source MIDI notes, and the
canonical assessment clock. Missing, duplicated, out-of-range or retimed
source notes fail closed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from ..assessment_clock import expected_note_seconds
from ..learning import LearningPlan
from ..music import Piece


@dataclass(frozen=True)
class CodaStageEvidence:
    key: str
    hand: str
    level: str
    source_attacks: int
    written_attacks: int
    changed_attacks: int
    total_seconds: float
    stage_class: str


@dataclass(frozen=True)
class CodaAudit:
    source_title: str
    source_attacks: int
    stages: tuple[CodaStageEvidence, ...]
    categories: tuple[str, ...]
    all_source_attacks_in_final: bool

    def as_dict(self) -> dict:
        return {
            "source_title":self.source_title,
            "source_attacks":self.source_attacks,
            "stages":[s.__dict__ for s in self.stages],
            "categories":list(self.categories),
            "all_source_attacks_in_final":self.all_source_attacks_in_final,
            "note_level_meaning":"MIDI source ownership and playback clock, not original MusicXML parity",
        }


def audit_coda_midi(piece: Piece) -> CodaAudit:
    if piece.source_format!="midi":
        raise ValueError("Coda note audit requires original imported MIDI")
    plan=LearningPlan(piece,exercise_strategy="coda-midi")
    original={n.source_id:n for n in piece.notes}
    if not original or len(original)!=len(piece.notes):
        raise ValueError("Cannot audit duplicate or absent source MIDI IDs")
    results=[]
    category_counts=Counter()
    for ex in plan.exercises:
        for hand in plan.lesson_definition.stage_sequences:
            key,selected_hand=hand
            if key!=ex.key:
                continue
            stages=plan.lesson_definition.stage_sequences[hand]
            full=ex.phrase.notes if selected_hand=="both" else tuple(
                n for n in ex.phrase.notes if n.hand==selected_hand)
            expected={n.source_id for n in full}
            if not expected:
                raise ValueError("Generator created an empty playable hand")
            if set(n.source_id for n in stages[-1].variant.notes)!=expected:
                raise ValueError("Terminal score loses source MIDI notes")
            for stage in stages:
                notes=stage.variant.notes
                phrase=stage.variant.phrase
                if not notes:
                    raise ValueError("Empty generated Coda stage")
                if len({n.source_id for n in notes})!=len(notes):
                    raise ValueError("A source attack was repeated in an exercise")
                if not set(n.source_id for n in notes)<=expected:
                    raise ValueError("Coda stage invents or crosses source hand notes")
                if len(stage.variant.source_indices)!=len(notes):
                    raise ValueError("Stage source index cardinality differs")
                changed=0
                for index,n in zip(stage.variant.source_indices,notes):
                    if not 0<=index<len(ex.phrase.notes):
                        raise ValueError("Exercise index outside original score")
                    original_note=ex.phrase.notes[index]
                    if (n.source_id!=original_note.source_id or
                            (n.pitch,n.hand,n.track,n.channel)!=(
                                original_note.pitch,original_note.hand,
                                original_note.track,original_note.channel)):
                        raise ValueError("Incorrect source attack ownership or pitch")
                    if not (all(isfinite(x) for x in (n.start,n.end)) and
                            n.start>=phrase.start-1e-7 and
                            n.start<n.end<=phrase.end+1e-7):
                        raise ValueError("Retimed note exceeds score excerpt")
                    if abs(n.start-original_note.start)>1e-7 or abs(
                            n.end-original_note.end)>1e-7:
                        changed+=1
                if stage.transformed_rhythm and changed==0:
                    raise ValueError("A no-op stage claims transformed rhythm")
                if not stage.transformed_rhythm and changed:
                    raise ValueError("Retimed note is not marked transformed")
                tempo=stage.tempo_map(120)
                if tempo is not None:
                    if stage.transformed_rhythm:
                        raise ValueError("Unexpected tempo+timing combination")
                    if stage.tempo_policy is None:
                        raise ValueError("Tempo stage lacks its policy")
                    factor=stage.tempo_policy.factor
                    if factor not in (2,4) or abs(
                            tempo.bpm_at(0)-120/factor)>1e-7:
                        raise ValueError("Coda slowdown does not scale playback tempo")
                else:
                    from ..exercise_contracts import TempoMap, TempoSegment
                    tempo=TempoMap("audit-original",(
                        TempoSegment(0.0,phrase.end-phrase.start,120.0),))
                seconds=expected_note_seconds(phrase,tempo)
                for note in notes:
                    start,end,local_spb=seconds(note)
                    if not (-1e-7<=start<end<=tempo.duration_seconds+1e-7):
                        raise ValueError("Canonical MIDI grading clock disagrees")
                    if not isfinite(local_spb) or local_spb<=0:
                        raise ValueError("Invalid grading local beat")
                level=stage.variant.level
                category=("slowed" if level.startswith("coda-slowdown")
                          else "dotted" if level.startswith("coda-dotted")
                          else "chordified" if level.startswith("coda-chord")
                          else "voice" if level.startswith("coda-voice")
                          else "original")
                category_counts[category]+=1
                results.append(CodaStageEvidence(
                    ex.key,selected_hand,level,len(expected),len(notes),
                    changed,tempo.duration_seconds,category))
    terminal=plan.exercises[-1]
    final=plan.lesson_definition.stages(terminal,"both")[-1].variant
    full_ids=Counter(n.source_id for n in final.notes)
    complete=(full_ids==Counter(n.source_id for n in terminal.phrase.notes))
    if not complete:
        raise ValueError("Complete performance lost original MIDI notes")
    return CodaAudit(piece.title,len(piece.notes),tuple(results),
                     tuple(sorted(category_counts)),complete)
