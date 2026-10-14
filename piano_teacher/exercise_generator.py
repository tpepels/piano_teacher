"""Generate progressively simplified, source-traceable MIDI exercises.

Only the generator is implemented here. The UI and grader must subsequently
consume the same variant before generated exercises are enabled for students.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from .music import Note, Phrase


@dataclass(frozen=True)
class ExerciseVariant:
    level: str
    phrase: Phrase
    source_indices: tuple[int, ...]

    @property
    def notes(self) -> tuple[Note, ...]:
        return self.phrase.notes


def generate_variants(phrase: Phrase, hand: str = "both") -> tuple[ExerciseVariant, ...]:
    """Skeleton -> chord outline -> original; omit musically redundant stages."""
    if hand not in ("right", "left", "both"):
        raise ValueError("Expected right, left, or both hands")
    indexed=[(i,n) for i,n in enumerate(phrase.notes) if hand=="both" or n.hand==hand]
    if not indexed:
        return ()
    indexed.sort(key=lambda pair:(pair[1].start,pair[1].hand,pair[1].pitch,pair[0]))
    beats=defaultdict(list)
    for i,n in indexed:
        beats[(n.hand,int(n.start-phrase.start+1e-7))].append((i,n))
    skeleton=[]
    for group in beats.values():
        chosen=min(group,key=lambda pair:(
            abs((pair[1].start-phrase.start)-round(pair[1].start-phrase.start)),
            -pair[1].pitch if pair[1].hand=="right" else pair[1].pitch,pair[0]))
        skeleton.append(chosen[0])
    chords=defaultdict(list)
    for i,n in indexed:
        chords[(n.hand,round(n.start,6))].append((i,n))
    outline=[]
    for group in chords.values():
        group.sort(key=lambda pair:(pair[1].pitch,pair[0]))
        outline.append(group[0][0])
        if len(group)>1:
            outline.append(group[-1][0])
    original=[i for i,_ in indexed]
    allowed=set(original)
    stages=[]
    previous=None
    for level,candidates in (("skeleton",skeleton),("outline",outline),("original",original)):
        indices=tuple(sorted(set(candidates)&allowed,key=lambda i:(phrase.notes[i].start,phrase.notes[i].pitch,i)))
        if not indices or indices==previous:
            continue
        variant_phrase=Phrase(phrase.number,phrase.first_bar,phrase.last_bar,phrase.start,phrase.end,
                              tuple(phrase.notes[i] for i in indices))
        stages.append(ExerciseVariant(level,variant_phrase,indices))
        previous=indices
    if len(stages)==1:
        return (ExerciseVariant("original",stages[0].phrase,stages[0].source_indices),)
    if stages[-1].level!="original":
        indices=tuple(sorted(original,key=lambda i:(phrase.notes[i].start,phrase.notes[i].pitch,i)))
        if stages[-1].source_indices==indices:
            stages[-1]=ExerciseVariant("original",stages[-1].phrase,indices)
        else:
            stages.append(ExerciseVariant("original",Phrase(
                phrase.number,phrase.first_bar,phrase.last_bar,phrase.start,phrase.end,
                tuple(phrase.notes[i] for i in indices)),indices))
    return tuple(stages)
