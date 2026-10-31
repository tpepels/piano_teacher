"""Two-clock contract for a source written tie and its single sounding attack.

An imported MusicXML tied chain is one graded/MIDI note but can occupy
multiple written noteheads. The immutable source segments have their own
IDs and onset/release, while their sounding owner is the first segment's
source ID. The projected segments must match the renderer's physical
MusicXML noteheads exactly; a tie stop never becomes another attack.

Currently restricted to two source segments separated by one original
internal barline, retaining the onset and the first segment. The final
continuation may shorten without crossing an authored rest.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ..exercise_contracts import TimingPlan
from ..music import Piece
from ..notation.lesson import DIVISIONS, LessonScore
from .coda_source_metadata import source_elements


@dataclass(frozen=True)
class WrittenTieSegment:
    written_id: str
    onset: float
    end: float
    start_tie: bool
    stop_tie: bool


@dataclass(frozen=True)
class WrittenTieChain:
    sounding_id: str
    voice: str
    pitch: int
    source_segments: tuple[WrittenTieSegment, ...]
    projected_segments: tuple[WrittenTieSegment, ...]

    @property
    def sounding_ends(self) -> tuple[float, float]:
        return self.source_segments[-1].end, self.projected_segments[-1].end


def _pitch(note: ET.Element) -> int:
    pitch=note.find("{*}pitch")
    if pitch is None:
        raise ValueError("Written tie cannot point to a rest")
    return (12*(int(pitch.findtext("{*}octave"))+1)
            + {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}[
                pitch.findtext("{*}step")]
            + int(pitch.findtext("{*}alter","0")))


def _roles(note: ET.Element) -> frozenset[str]:
    played={tag.get("type") for tag in note.findall("{*}tie")}
    engraved={tag.get("type") for tag in
              note.findall("{*}notations/{*}tied")}
    if played and engraved and played != engraved:
        raise ValueError("Written tie performance and notation roles differ")
    roles=played or engraved
    if not roles <= {"start","stop"}:
        raise ValueError("Unsupported written tie declaration")
    return frozenset(roles)


def tie_segment_chains(piece: Piece, timing: TimingPlan) -> tuple[WrittenTieChain, ...]:
    """Read original XML segments and link them to exact imported attacks."""
    parts=source_elements(
        piece.source_musicxml,first_bar=1,
        last_bar=len(piece.bar_boundaries)-1,boundaries=piece.bar_boundaries)
    original={n.source_id:n for n in timing.original.notes}
    exercise={n.source_id:n for n in timing.exercise_phrase.notes}
    running={}
    completed=[]
    for item in parts:
        if item.kind!="note" or item.end is None or item.is_rest:
            continue
        xml=ET.fromstring(item.xml)
        roles=_roles(xml)
        if not roles:
            continue
        pitch=_pitch(xml)
        key=(item.voice_id,pitch)
        segment=WrittenTieSegment(
            item.source_id,item.onset,item.end,
            "start" in roles,"stop" in roles)
        if "stop" in roles:
            active=running.get(key)
            if active is None:
                raise ValueError("Written tie has no exact source voice/pitch start")
            owner,segments=active
            if abs(segments[-1].end-segment.onset)>1e-7:
                raise ValueError("Written tie has a sounding gap")
            segments.append(segment)
            if "start" not in roles:
                completed.append((owner,item.voice_id,pitch,tuple(segments)))
                del running[key]
        else:
            if key in running:
                raise ValueError("Written tie starts twice in one voice/pitch")
            running[key]=(item.source_id,[segment])
    if running:
        raise ValueError("Written tie has an unclosed source continuation")
    chains=[]
    for owner,voice,pitch,segments in completed:
        note=original.get(owner)
        transformed=exercise.get(owner)
        if (note is None or transformed is None
                or note.voice!=voice or note.pitch!=pitch
                or abs(note.start-segments[0].onset)>1e-7
                or abs(note.end-segments[-1].end)>1e-7
                or abs(transformed.start-note.start)>1e-7):
            raise ValueError("Written tie and sounding source attack do not agree")
        if len(segments)!=2 or not (
                segments[0].start_tie and not segments[0].stop_tie and
                segments[1].stop_tie and not segments[1].start_tie):
            raise ValueError("Only two-segment written source ties are verified")
        boundary=segments[0].end
        if (abs(segments[1].onset-boundary)>1e-7
                or not any(abs(b-boundary)<1e-7
                           for b in piece.bar_boundaries[1:-1])
                or not boundary+1e-7<transformed.end<=note.end+1e-7):
            raise ValueError("Retimed written tie must retain its source barline")
        projected=(segments[0],WrittenTieSegment(
            segments[1].written_id,boundary,transformed.end,False,True))
        chains.append(WrittenTieChain(
            owner,voice,pitch,segments,projected))
    return tuple(chains)


def verify_written_tie_projection(
    chains: tuple[WrittenTieChain, ...], lesson: LessonScore
) -> None:
    """Check each generated glyph against a written segment, no reattacks."""
    if not chains:
        return
    root=ET.fromstring(lesson.musicxml)
    by_owner={}
    for note in root.findall(".//{*}note[@id]"):
        binding=lesson.note_bindings.get(note.get("id"))
        if binding is None:
            continue
        by_owner.setdefault(binding["source_id"],[]).append((binding,note))
    for chain in chains:
        glyphs=sorted(by_owner.get(chain.sounding_id,()),
                      key=lambda pair:pair[0]["display_beat"])
        if len(glyphs)!=len(chain.projected_segments):
            raise ValueError("Written tie lost or duplicated a projected notehead")
        for i,((binding,note),segment) in enumerate(
                zip(glyphs,chain.projected_segments)):
            onset=float(binding["display_beat"])
            end=onset+int(note.findtext("{*}duration","0"))/DIVISIONS
            played={mark.get("type") for mark in note.findall("{*}tie")}
            drawn={mark.get("type") for mark in
                   note.findall("{*}notations/{*}tied")}
            expected=({"start"} if i==0 else {"stop"})
            if (abs(onset-segment.onset)>1e-7 or
                    abs(end-segment.end)>1e-7 or
                    _pitch(note)!=chain.pitch or
                    played!=expected or drawn!=expected or
                    bool(binding["is_attack"])!=(i==0)):
                raise ValueError("Written tie glyph, sounding owner or boundary disagrees")
