"""Source-traceable exercises following the original Coda backend's categories.

This is an independent research adapter, not a copy of the author's code.
Reference: Tang (2025), §2.3, pp.11–16; annieetang/coda_backend
music/exercise.py at a4eb85dfc2bd418818ca9ff775c0a11ccccb3530.

The author's backend uses equal-duration runs, per-voice matrices and
factors 2/4 for written slowdown. Known unguarded bugs (out-of-bounds
subgroups, nested pitch list, silent rounding) are deliberately not
reproduced. Unsupported inputs fail closed and the differences are
documented; this is reference-guided, not blanket parity.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from ..exercise_contracts import OriginalTiming, TimingPlan
from ..exercise_generator import ExerciseVariant
from ..music import Phrase
from ..notation.rhythm_safety import (
    rhythm_protected_source_ids, slur_endpoint_source_ids, beamed_source_ids,
)
from .coda_matrix import MatrixScore, MatrixVoice
from .coda_reference_matrix import CodaVoiceMatrix, score_voice_matrices


@dataclass(frozen=True)
class CodaLevelSelection:
    level: str
    variant: ExerciseVariant
    hand: str
    voice: str | None


@dataclass(frozen=True)
class CodaReferenceResult:
    family: str
    timing: TimingPlan
    changed_sources: tuple[str,...]
    groups: tuple[tuple[str,...],...]


def original_coda_levels(variant: ExerciseVariant, *,
                         boundaries: tuple[float,...],
                         source_musicxml: str = "") -> tuple[CodaLevelSelection,...]:
    """Actual Coda Score → Part → Voice isolation, NOT measure splitting."""
    matrix=MatrixScore.from_phrase(
        variant.phrase,boundaries=boundaries,source_musicxml=source_musicxml)
    result=[CodaLevelSelection("score",variant,"both",None)]
    for part in matrix.parts:
        ids=tuple(index for voice in part.voices
                  for attack in voice.attacks for index in attack.source_indices)
        if not ids:
            continue
        indices=tuple(i for i in range(len(variant.notes)) if i in set(ids))
        subset=_select(variant,indices,f"coda-part-{part.hand}")
        result.append(CodaLevelSelection("part",subset,part.hand,None))
        for voice in part.voices:
            source_indices={i for attack in voice.attacks for i in attack.source_indices}
            indices=tuple(i for i in range(len(variant.notes)) if i in source_indices)
            result.append(CodaLevelSelection(
                "voice",_select(variant,indices,"coda-voice-"+voice.name),
                part.hand,voice.name))
    return tuple(result)


def _select(original:ExerciseVariant,indices:tuple[int,...],name:str)->ExerciseVariant:
    p=original.phrase
    phrase=Phrase(p.number,p.first_bar,p.last_bar,p.start,p.end,
                  tuple(p.notes[i] for i in indices))
    return ExerciseVariant(name,phrase,tuple(original.source_indices[i] for i in indices))


@dataclass(frozen=True)
class CodaReferenceSlowdown:
    """Original Coda duration-and-notation scaling (not a TempoMap ramp)."""
    factor: int

    def transform(self, variant: ExerciseVariant) -> CodaReferenceResult:
        if self.factor not in (2,4):
            raise ValueError("Original Coda backend generates slowdown factors 2 and 4")
        original=OriginalTiming().transform(variant)
        events=tuple(replace(e,
            exercise_start=e.exercise_start*self.factor,
            exercise_end=e.exercise_end*self.factor)
            for e in original.events)
        plan=TimingPlan(
            "coda-reference-slowdown-x"+str(self.factor),
            variant,events,original.duration_beats*self.factor)
        return CodaReferenceResult(
            "tempo-shaping",plan,tuple(n.source_id for n in variant.notes),())


def _protected(score:MatrixScore)->frozenset[str]:
    protected=score.connector_protected_source_ids() | score.context_protected_source_ids()
    if score.original_musicxml:
        protected |= (rhythm_protected_source_ids(score.original_musicxml)
                      | slur_endpoint_source_ids(score.original_musicxml)
                      | beamed_source_ids(score.original_musicxml))
        # In this deliberately strict research adapter, do not retime
        # notated articulations/ornaments/time-modification without an
        # annotation-to-transformed-time projection.
        from xml.etree import ElementTree as ET
        for item in score.notation_elements:
            if item.kind!="note":
                continue
            node=ET.fromstring(item.xml)
            if node.find("{*}notations") is not None or node.find(
                    "{*}time-modification") is not None:
                protected |= {item.source_id}
    return frozenset(protected)


def _source(score:MatrixScore, variant:ExerciseVariant, quantization:int):
    matrices=score_voice_matrices(score,quantization=quantization)
    paired=[]
    for part in score.parts:
        for voice in part.voices:
            matrix=next(m for m in matrices
                        if m.voice==voice.name and m.hand==part.hand)
            paired.append((voice,matrix))
    return paired


def _mutable_events(variant:ExerciseVariant):
    original=OriginalTiming().transform(variant)
    return list(original.events),original.duration_beats


def _safe_group(score:MatrixScore, voice:MatrixVoice,
                members:tuple[tuple[int,...],...],
                protected:frozenset[str],
                start:float,end:float)->bool:
    indices=tuple(i for attack in voice.attacks
                  for i in attack.source_indices
                  if start-1e-7 <= score.phrase.notes[i].start < end-1e-7)
    if not indices or any(score.phrase.notes[i].source_id in protected
                          for i in indices):
        return False
    if any(rest.onset < end-1e-7 and rest.end > start+1e-7
           for rest in voice.written_rests):
        return False
    bar=next((j for j,(a,b) in enumerate(zip(score.boundaries,score.boundaries[1:]))
              if a-1e-7 <= start < b-1e-7),None)
    return (bar is not None and
            end <= score.boundaries[bar+1]+1e-7 and
            all(score.phrase.notes[i].start>=start-1e-7 and
                score.phrase.notes[i].end<=end+1e-7 for i in indices))


@dataclass(frozen=True)
class CodaReferenceDotted:
    """Alternating 3:1 and 1:3 source equal-duration runs."""
    long_first: bool

    @property
    def pattern(self)->tuple[float,float]:
        return (1.5,.5) if self.long_first else (.5,1.5)

    def transform(self,variant:ExerciseVariant,*,boundaries:tuple[float,...],
                  quantization:int,source_musicxml:str="")->CodaReferenceResult:
        score=MatrixScore.from_phrase(
            variant.phrase,boundaries=boundaries,source_musicxml=source_musicxml)
        guarded=_protected(score)
        events,duration=_mutable_events(variant)
        decisions=[]
        for voice,matrix in _source(score,variant,quantization):
            flat,pitches=matrix.flatten()
            for start,finish,_ in matrix.equal_duration_ranges():
                attacks=[tick for tick in range(start,finish) if flat[tick]>0]
                # Incomplete odd-length alternating runs retain the final
                # original attack instead of overstepping the source bar.
                for a,b in zip(attacks[::2],attacks[1::2]):
                    n=flat[a]
                    if b-a!=n or flat[b]!=n:
                        continue
                    parts=[n*self.pattern[0],n*self.pattern[1]]
                    if any(abs(round(v)-v)>1e-8 or v<=0 for v in parts):
                        continue
                    first_start=score.phrase.start+a/quantization
                    end=score.phrase.start+(b+n)/quantization
                    if not _safe_group(score,voice,(),guarded,first_start,end):
                        continue
                    ids1=tuple((p,a) for p in pitches[a])
                    ids2=tuple((p,b) for p in pitches[b])
                    sources=tuple(
                        source for pitch,tick,index,source in matrix.owners
                        if (pitch,tick) in ids1+ids2)
                    if len(sources)!=len(ids1)+len(ids2):
                        raise ValueError("Coda source matrix lost ownership")
                    for pitch,tick,index,source in matrix.owners:
                        if (pitch,tick) in ids1:
                            events[index]=replace(events[index],
                                exercise_end=(a+parts[0])/quantization)
                        elif (pitch,tick) in ids2:
                            events[index]=replace(events[index],
                                exercise_start=(a+parts[0])/quantization,
                                exercise_end=(a+2*n)/quantization)
                    decisions.append(sources)
                # The pinned backend applies the next multiplier to the
                # final event of an odd-length run (not merely to pairs).
                # That may extend a note past a score boundary or through
                # a new attack; retain reference behavior ONLY when that
                # complete transformed duration remains representable.
                if len(attacks)%2:
                    a=attacks[-1]
                    n=flat[a]
                    length=n*self.pattern[0]
                    if length>0 and abs(round(length)-length)<=1e-8:
                        onset=score.phrase.start+a/quantization
                        old_end=score.phrase.start+(a+n)/quantization
                        new_end=score.phrase.start+(a+length)/quantization
                        next_ticks=[tick for tick in range(a+1,matrix.steps)
                                    if flat[tick]>0]
                        next_onset=(score.phrase.start+next_ticks[0]/quantization
                                    if next_ticks else float("inf"))
                        containing_bar=next((right for left,right in
                            zip(score.boundaries,score.boundaries[1:])
                            if left-1e-7<=onset<right-1e-7),None)
                        rest_conflict=any(
                            rest.onset < new_end-1e-7 and
                            rest.end > old_end+1e-7
                            for rest in voice.written_rests)
                        if (containing_bar is not None and
                                new_end<=containing_bar+1e-7 and
                                new_end<=next_onset+1e-7 and
                                not rest_conflict and
                                _safe_group(score,voice,(),guarded,onset,old_end)):
                            owners=tuple((pitch,index,source)
                                         for pitch,tick,index,source in matrix.owners
                                         if tick==a)
                            if owners:
                                for pitch,index,source in owners:
                                    events[index]=replace(
                                        events[index],
                                        exercise_end=(a+length)/quantization)
                                decisions.append(tuple(source for _,_,source in owners))
        plan=TimingPlan(
            "coda-reference-dotted-"+("long-short" if self.long_first else "short-long"),
            variant,tuple(events),duration)
        return CodaReferenceResult(
            "dotted-rhythms",plan,tuple(s for group in decisions for s in group),
            tuple(decisions))


@dataclass(frozen=True)
class CodaReferenceChordification:
    """Group equal-duration runs into blocked chords of chosen grid width."""
    chord_level: int

    def transform(self,variant:ExerciseVariant,*,boundaries:tuple[float,...],
                  quantization:int,source_musicxml:str="")->CodaReferenceResult:
        if self.chord_level<=0:
            raise ValueError("Chord grouping width must be positive")
        score=MatrixScore.from_phrase(
            variant.phrase,boundaries=boundaries,source_musicxml=source_musicxml)
        guarded=_protected(score)
        events,duration=_mutable_events(variant)
        groups=[]
        for voice,matrix in _source(score,variant,quantization):
            flat,pitches=matrix.flatten()
            for start,finish,_ in matrix.equal_duration_ranges():
                for group_start in range(start,finish,self.chord_level):
                    end=min(group_start+self.chord_level,finish)
                    attacks=[t for t in range(group_start,end) if flat[t]>0]
                    if len(attacks)<2:
                        continue
                    source_durations={flat[t] for t in attacks}
                    if len(source_durations)!=1:
                        continue
                    n=next(iter(source_durations))
                    # The author's equal-length range ends at the NEXT
                    # different duration, which may be separated by silence.
                    # A grouping is valid if its source notes are contiguous;
                    # padding after the last attack remains a real rest.
                    if attacks[0]!=group_start:
                        continue
                    if any(b-a !=n for a,b in zip(attacks,attacks[1:])):
                        continue
                    actual_end=attacks[-1]+n
                    if actual_end>end or sum(flat[t] for t in attacks)!=actual_end-group_start:
                        continue
                    group_entries=[(pitch,t,index,source)
                                   for pitch,t,index,source in matrix.owners
                                   if t in attacks]
                    distinct={pitch for pitch,_,_,_ in group_entries}
                    # Tang's §2.5 validation: no more than five
                    # chord tones, and pitch span at most one octave.
                    if len(distinct)!=len(group_entries) or len(distinct)>5 or (
                            max(distinct)-min(distinct)>12):
                        continue
                    origin=score.phrase.start+group_start/quantization
                    target_end=score.phrase.start+actual_end/quantization
                    if not _safe_group(score,voice,(),guarded,origin,target_end):
                        continue
                    for pitch,t,index,source in group_entries:
                        events[index]=replace(events[index],
                            exercise_start=group_start/quantization,
                            exercise_end=actual_end/quantization)
                    groups.append(tuple(e[3] for e in group_entries))
        plan=TimingPlan(
            "coda-reference-chordified-"+str(self.chord_level),
            variant,tuple(events),duration)
        return CodaReferenceResult(
            "chordification",plan,tuple(s for group in groups for s in group),
            tuple(groups))
