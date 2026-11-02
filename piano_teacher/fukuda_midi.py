"""MIDI-native Fukuda (SMC 2015) score reduction and mistake detection.

Inputs are a scored MIDI Piece and performed MIDI note-on/off events.
There is deliberately NO audio decoding, CQT, NMF, microphone or acoustic
octave-error filter: precise source MIDI pitches make those layers both
inapplicable and potentially harmful. The score/performance alignment is
DTW on 12-dimensional MIDI chroma onset frames, with original beat-time
regularization and preserved source attack identities.

The three score rules follow Fukuda et al. §3.4: preserve outer chord
pitches, thin fast nonmelodic passages, and remove isolated return leaps
(or simplify adjacent groups for a one-way leap). Nontrivial stages always
return to the unchanged source score.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

from .exercise_generator import ExerciseVariant
from .music import Note, Phrase, Piece
from .practice import PlayedNote


@dataclass(frozen=True)
class AlignedOnset:
    score_beat: float
    performed_seconds: float
    score_pitches: tuple[int, ...]
    performed_pitches: tuple[int, ...]


@dataclass(frozen=True)
class MidiMismatch:
    source_id: str
    pitch: int
    onset_beat: float
    kind: str


@dataclass(frozen=True)
class MidiMistakeReport:
    alignment: tuple[AlignedOnset, ...]
    mismatches: tuple[MidiMismatch, ...]
    extra_pitches: tuple[tuple[float,int], ...]
    hand: str

    @property
    def problematic_source_ids(self) -> frozenset[str]:
        return frozenset(m.source_id for m in self.mismatches)


def _groups(notes: Sequence[Note], hand: str) -> tuple[tuple[float,tuple[int,...]],...]:
    by=defaultdict(list)
    for n in notes:
        if hand=="both" or n.hand==hand:
            by[round(n.start,7)].append(n.pitch)
    return tuple((t,tuple(sorted(values))) for t,values in sorted(by.items()))


def _played_groups(played: Sequence[PlayedNote], tolerance_s: float) -> tuple[tuple[float,tuple[int,...]],...]:
    if not all(isfinite(x.onset) and x.onset>=0 and
               (x.release is None or (isfinite(x.release) and x.release>=x.onset))
               and 0<=x.pitch<=127 for x in played):
        raise ValueError("Performed MIDI events contain invalid pitch or time")
    ordered=sorted(played,key=lambda x:(x.onset,x.pitch))
    if not ordered:
        return ()
    result=[]
    current=[]
    anchor=ordered[0].onset
    for n in ordered:
        if current and n.onset-anchor>tolerance_s:
            result.append((anchor,tuple(sorted(x.pitch for x in current))))
            current=[]
            anchor=n.onset
        current.append(n)
    if current:
        result.append((anchor,tuple(sorted(x.pitch for x in current))))
    return tuple(result)


def _chroma(pitches: tuple[int,...]) -> tuple[float,...]:
    out=[0.0]*12
    for pitch in pitches:
        out[pitch%12]+=1.0
    norm=sqrt(sum(v*v for v in out))
    return tuple(v/norm for v in out)


def align_midi_dtw(phrase: Phrase, played: Sequence[PlayedNote], *,
                   hand: str="both", bpm: float=90,
                   chord_window_seconds: float=.055,
                   maximum_onsets: int=1500) -> tuple[AlignedOnset,...]:
    """Monotone DTW chroma alignment; score and performance are real MIDI.

    A skipped score event or added played event can align to an adjacent
    frame. The optimal matched path is monotone, with a weak timing prior
    that prevents identical repeated chords from matching distant bars.
    """
    if bpm<=0 or not isfinite(bpm) or not 0<=chord_window_seconds<=.15:
        raise ValueError("Invalid alignment time configuration")
    score=_groups(phrase.notes,hand)
    perf=_played_groups(played,chord_window_seconds)
    if not score or not perf:
        return ()
    n,m=len(score),len(perf)
    if max(n,m)>maximum_onsets:
        raise ValueError("MIDI DTW exceeds bounded source event count")
    chroma_score=[_chroma(p) for _,p in score]
    chroma_perf=[_chroma(p) for _,p in perf]
    # Absolute movement is penalized but allowed; offsets are normalized
    # against each recording's actual first/last sounding time.
    min_score,max_score=score[0][0],score[-1][0]
    min_perf,max_perf=perf[0][0],perf[-1][0]
    s_span=max(max_score-min_score,1e-8)
    p_span=max(max_perf-min_perf,1e-8)
    inf=float("inf")
    costs=[[inf]*(m+1) for _ in range(n+1)]
    prev=[[None]*(m+1) for _ in range(n+1)]
    costs[0][0]=0.
    for i in range(1,n+1):
        for j in range(1,m+1):
            similarity=sum(a*b for a,b in zip(chroma_score[i-1],chroma_perf[j-1]))
            displacement=abs((score[i-1][0]-min_score)/s_span -
                             (perf[j-1][0]-min_perf)/p_span)
            cost=(1.0-similarity)+.15*displacement
            choices=((costs[i-1][j-1],0),(costs[i-1][j]+.30,1),
                     (costs[i][j-1]+.30,2))
            c,which=min(choices,key=lambda x:(x[0],x[1]))
            costs[i][j]=cost+c
            prev[i][j]=which
    i,j=n,m
    pairs=[]
    while i>0 and j>0:
        direction=prev[i][j]
        if direction==0:
            pairs.append((i-1,j-1));i-=1;j-=1
        elif direction==1:
            i-=1
        else:
            j-=1
    pairs.reverse()
    return tuple(AlignedOnset(score[i][0],perf[j][0],
                               score[i][1],perf[j][1]) for i,j in pairs)


def detect_midi_mistakes(phrase: Phrase, played: Sequence[PlayedNote], *,
                         hand: str="both", bpm: float=90,
                         onset_tolerance_s: float=.14) -> MidiMistakeReport:
    """Detect missed, wrong and extra MIDI events after alignment.

    Do NOT ignore octave errors: the paper's acoustic-NMF octave errors
    are transcription artifacts, whereas a MIDI pitch is authoritative.
    """
    aligned=align_midi_dtw(phrase,played,hand=hand,bpm=bpm)
    notes=tuple(n for n in phrase.notes if hand=="both" or n.hand==hand)
    unused=set(range(len(played)))
    pairs=[]
    # DTW anchors align even an expressive performance with tempo drift.
    for n in notes:
        anchor=min(aligned,key=lambda p:abs(p.score_beat-n.start),
                   default=None)
        target=((n.start-phrase.start)*60/bpm if anchor is None
                else anchor.performed_seconds+
                    (n.start-anchor.score_beat)*60/bpm)
        for j in unused:
            p=played[j]
            if p.pitch==n.pitch:
                pairs.append((abs(p.onset-target),n.source_id,j,n,target))
    taken_ids=set()
    matches={}
    for distance,sid,j,n,target in sorted(pairs,key=lambda x:x[0]):
        # Broad note-matching limit permits DTW-expressive timing while
        # preventing an unrelated same-pitch note several measures away.
        if distance>max(.4,1.25*60/bpm):
            continue
        if sid not in taken_ids and j in unused:
            matches[sid]=(j,target)
            taken_ids.add(sid);unused.remove(j)
    errors=[]
    for n in notes:
        if n.source_id not in matches:
            # Recognize a wrong pitch at this aligned score event.
            anchor=min(aligned,key=lambda p:abs(p.score_beat-n.start),
                       default=None)
            target=anchor.performed_seconds if anchor is not None else (
                n.start-phrase.start)*60/bpm
            candidates=[j for j in unused
                        if abs(played[j].onset-target)<=onset_tolerance_s]
            if candidates:
                unused.remove(min(candidates,key=lambda j:abs(
                    played[j].onset-target)))
                errors.append(MidiMismatch(n.source_id,n.pitch,n.start,"wrong"))
            else:
                errors.append(MidiMismatch(n.source_id,n.pitch,n.start,"missed"))
        else:
            j,target=matches[n.source_id]
            if abs(played[j].onset-target)>onset_tolerance_s:
                errors.append(MidiMismatch(n.source_id,n.pitch,n.start,"timing"))
    return MidiMistakeReport(aligned,tuple(errors),
        tuple((played[j].onset,played[j].pitch) for j in sorted(unused)),hand)


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
            if max((n.start-before.start)*60/bpm,
                   (after.start-n.start)*60/bpm)>threshold_seconds:
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
