"""MIDI-native Fukuda (SMC 2015) score reduction.

Inputs are a scored MIDI Piece. There is deliberately NO audio decoding,
CQT, NMF or acoustic octave filtering: precise source MIDI pitches make
those layers inapplicable. Learner mistakes come from the shared
original-note assessment, not from a separate alignment here.

The three score rules follow Fukuda et al. §3.4: preserve outer chord
pitches, thin fast nonmelodic passages, and remove isolated return leaps
(or simplify adjacent groups for a one-way leap). Nontrivial stages always
return to the unchanged source score.
"""
from __future__ import annotations

from collections import defaultdict

from .exercise_generator import ExerciseVariant
from .music import Phrase
from .application.musical_scheduler import SCHEDULER


def _as_variant(source: ExerciseVariant, level: str,
                keep: set[int]) -> ExerciseVariant | None:
    if not keep or keep==set(source.source_indices):
        return None
    chosen=tuple((idx,n) for idx,n in zip(source.source_indices,source.notes)
                 if idx in keep)
    if not chosen or len(chosen)==len(source.notes):
        return None
    phrase=source.phrase
    return ExerciseVariant(level,Phrase(phrase.number,phrase.first_bar,
        phrase.last_bar,phrase.start,phrase.end,tuple(n for _,n in chosen)),
        tuple(i for i,_ in chosen))


def _protected(source: ExerciseVariant, weak: frozenset[str] | None) -> set[int]:
    return {i for i,n in zip(source.source_indices,source.notes)
            if weak is not None and n.source_id not in weak}


def rule_chord_outer(source: ExerciseVariant, *,
                     mistakes: frozenset[str] | None = None) -> ExerciseVariant | None:
    """Fukuda pattern 1: inner notes removed; keep lowest and highest."""
    keep=set(source.source_indices)
    groups=defaultdict(list)
    for idx,n in zip(source.source_indices,source.notes):
        groups[(n.hand,round(n.start,7))].append((n.pitch,idx,n))
    for chord in groups.values():
        if len(chord)<3:
            continue
        order=sorted(chord)
        if mistakes is not None and not any(n.source_id in mistakes
                                            for _,_,n in order):
            continue
        for _,idx,_ in order[1:-1]:
            keep.discard(idx)
    return _as_variant(source,"fukuda-midi-chord-outer",keep)


def rule_fast_thinning(source: ExerciseVariant, *,
                       bpm: float,threshold_seconds: float=.21,
                       mistakes: frozenset[str] | None = None) -> ExerciseVariant | None:
    """Fukuda pattern 2: thin rapid notes, but retain obvious upper melody.

    Preserve the first/last attack and alternating interior notes in a
    fast voice. A prominent upper melodic line is protected because the
    original paper reported that thinning melodies was unnatural.
    """
    if bpm<=0:
        raise ValueError("Invalid Fukuda tempo")
    keep=set(source.source_indices)
    by=defaultdict(list)
    for idx,n in zip(source.source_indices,source.notes):
        by[(n.hand,n.track,n.voice)].append((idx,n))
    for notes in by.values():
        notes.sort(key=lambda x:x[1].start)
        if len(notes)<4:
            continue
        for k in range(1,len(notes)-1):
            before=notes[k-1][1]; idx,n=notes[k];after=notes[k+1][1]
            # Never thin overlapping voices, chords or held melody pitches.
            if not (before.start<n.start<after.start and
                    before.end<=n.start+1e-7 and
                    n.end<=after.start+1e-7):
                continue
            if max(SCHEDULER.signed_beats_seconds(n.start-before.start,bpm),
                   SCHEDULER.signed_beats_seconds(after.start-n.start,bpm))>threshold_seconds:
                continue
            if mistakes is not None and n.source_id not in mistakes:
                continue
            # Only alternate positions; avoid successive removals.
            if k%2==1 and idx in keep and notes[k-1][0] in keep:
                # A local melodic peak must stay identifiable.
                if n.pitch>max(before.pitch,after.pitch):
                    continue
                keep.discard(idx)
    return _as_variant(source,"fukuda-midi-fast-thin",keep)


def rule_octave_leaps(source: ExerciseVariant, *,
                      bpm: float, mistakes: frozenset[str] | None = None
                      ) -> ExerciseVariant | None:
    """Fukuda pattern 3-A removes the returning distant note.

    For 3-B (no returning leap), remove a suitable inner chord note or
    a rapid neighboring nonmelodic note, as in §3.4.3 of the paper.
    """
    keep=set(source.source_indices)
    by=defaultdict(list)
    for idx,n in zip(source.source_indices,source.notes):
        by[(n.hand,n.track,n.voice)].append((idx,n))
    for group in by.values():
        group.sort(key=lambda x:x[1].start)
        for k in range(1,len(group)-1):
            a=group[k-1][1];idx,b=group[k];c=group[k+1][1]
            if mistakes is not None and b.source_id not in mistakes:
                continue
            if (a.start<b.start<c.start and abs(b.pitch-a.pitch)>12
                    and abs(c.pitch-b.pitch)>12 and abs(c.pitch-a.pitch)<=12):
                keep.discard(idx)
    stage=_as_variant(source,"fukuda-midi-return-leap",keep)
    if stage is not None:
        return stage
    # Pattern 3-B only triggers near a large one-way leap; use one of
    # the paper's neighboring chord/fast rules, not arbitrary pitch shifts.
    leaps=tuple((a[1],b[1]) for g in by.values()
                for a,b in zip(g,g[1:])
                if abs(a[1].pitch-b[1].pitch)>12)
    if mistakes is not None:
        leaps=tuple((a,b) for a,b in leaps
                    if a.source_id in mistakes or b.source_id in mistakes)
    if not leaps:
        return None
    # 3-B affects ONLY material adjacent to the detected leap. A remote
    # chord elsewhere in a hundred-bar piece must never be removed merely
    # because another passage contains a large melodic interval.
    neighborhood=frozenset(n.source_id for n in source.notes
        if any(abs(n.start-b.start)<=2.0 or abs(n.start-a.start)<=2.0
               for a,b in leaps))
    inner=rule_chord_outer(source,mistakes=neighborhood)
    if inner is not None:
        return _as_variant(source,"fukuda-midi-leap-neighbor",set(inner.source_indices))
    fast=rule_fast_thinning(source,bpm=bpm,mistakes=neighborhood)
    if fast is not None:
        return _as_variant(source,"fukuda-midi-leap-neighbor",set(fast.source_indices))
    return None


def fukuda_midi_variants(original: ExerciseVariant, *, bpm: float,
                         mistakes: frozenset[str] | None = None
                         ) -> tuple[ExerciseVariant,...]:
    """All three original-rule families, ordered easiest to source."""
    proposals=(rule_chord_outer(original,mistakes=mistakes),
               rule_fast_thinning(original,bpm=bpm,mistakes=mistakes),
               rule_octave_leaps(original,bpm=bpm,mistakes=mistakes))
    seen=set()
    stages=[]
    for variant in proposals:
        if variant is None:
            continue
        signature=tuple(variant.source_indices)
        if signature in seen:
            continue
        seen.add(signature)
        stages.append(variant)
    return (*stages,original)


def as_fukuda_stage(variant: ExerciseVariant):
    """Attach author-owned provenance to a MIDI reduction.

    Stage naming is an internal generator concern. Teaching/UI code consumes
    the metadata and never needs to know Fukuda level-string conventions.
    """
    from .exercise_pipeline import ExerciseStage
    labels = {
        "fukuda-midi-chord-outer": ("chord-reduction", "Outer chord notes"),
        "fukuda-midi-fast-thin": ("fast-reduction", "Fewer fast notes"),
        "fukuda-midi-return-leap": ("return-leap", "Simplified wide leaps"),
        "fukuda-midi-leap-neighbor": ("leap-neighbor", "Neighboring leap practice"),
    }
    if variant.level == "original":
        return ExerciseStage(variant, origin="original", technique="original",
                             display_name="Original notes and rhythm")
    if variant.level not in labels:
        raise ValueError(f"Unknown Fukuda source-reduction stage: {variant.level}")
    technique, label = labels[variant.level]
    return ExerciseStage(variant, origin="fukuda-midi",
                         technique=technique, display_name=label)
