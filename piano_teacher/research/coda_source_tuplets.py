"""Strict source-owned tuplets for the Coda experimental notation projection.

Complete source-owned 3:2, 5:4 or 7:4 eighth-note groups in one
source measure/voice are supported when their timing remains unchanged. The exact original attack,
duration, source XML markers and generated group must all agree. Complex,
nested, rest-bearing or time-shifted groups deliberately fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ..exercise_contracts import TimingPlan
from ..music import Piece
from .coda_source_metadata import source_elements


def _name(element: ET.Element) -> str:
    return element.tag.rsplit("}",1)[-1]


@dataclass(frozen=True)
class CodaTupletRest:
    source_id: str
    onset: float
    end: float
    measure: int


@dataclass(frozen=True)
class CodaTupletGroup:
    source_ids: tuple[str, ...]
    actual: int
    normal: int
    number: str
    start_attrs: tuple[tuple[str, str], ...]
    stop_attrs: tuple[tuple[str, str], ...]
    rests: tuple[CodaTupletRest, ...] = ()


def source_tuplet_groups(piece: Piece, timing: TimingPlan, *,
                         factor: int) -> tuple[CodaTupletGroup, ...]:
    """Validate every authored ratio and bracket before exposing a score."""
    if not piece.source_musicxml:
        return ()
    original = timing.original.phrase
    xml = source_elements(piece.source_musicxml,first_bar=original.first_bar,
                          last_bar=original.last_bar,boundaries=piece.bar_boundaries)
    source = {note.source_id:note for note in timing.original.notes}
    exercise = {note.source_id:note for note in timing.exercise_phrase.notes}
    if len(source)!=len(timing.original.notes) or set(source)!=set(exercise):
        raise ValueError("Coda tuplets require complete source note identity")
    groups = []
    opened = {}
    involved = set()
    ratio_notes = set()
    ratios = {}
    for item in xml:
        if item.kind!="note":
            continue
        note=ET.fromstring(item.xml)
        marks=note.findall("{*}notations/{*}tuplet")
        ratio=note.find("{*}time-modification")
        if ratio is not None or marks:
            if (factor!=1 or (not item.is_rest and (
                    item.source_id not in source or
                    any(abs(a-b)>1e-7 for a,b in (
                        (source[item.source_id].start,exercise[item.source_id].start),
                        (source[item.source_id].end,exercise[item.source_id].end))))):
                raise ValueError("Coda cannot remap a source tuplet's timed event")
            actual=int(ratio.findtext("{*}actual-notes","0")) if ratio is not None else 0
            normal=int(ratio.findtext("{*}normal-notes","0")) if ratio is not None else 0
            if ((actual,normal) not in ((3,2),(5,4),(7,4))
                    or note.findtext("{*}type")!="eighth"
                    or item.end is None
                    or abs(item.end-item.onset-(normal/(2*actual)))>1e-7):
                raise ValueError("Coda currently requires unmodified 3:2, 5:4 or 7:4 eighth tuplets")
            ratio_notes.add(item.source_id)
            ratios[item.source_id]=(actual,normal)
        for mark in marks:
            attrs=mark.attrib
            kind=attrs.get("type")
            number=attrs.get("number","1")
            if (kind not in ("start","stop") or number!="1"
                    or set(attrs)-{"type","number","bracket","show-number"}
                    or attrs.get("bracket","yes") not in ("yes","no")
                    or attrs.get("show-number","actual") not in ("actual","none")):
                raise ValueError("Coda source tuplet mark is unsupported")
            key=(item.part_index,item.measure,item.voice_id,number)
            if kind=="start":
                if key in opened:
                    raise ValueError("Coda source tuplets cannot overlap or nest")
                opened[key]=(item,tuple(sorted(attrs.items())))
            else:
                first=opened.pop(key,None)
                if first is None:
                    raise ValueError("Coda source tuplet has an unmatched stop")
                start,start_attrs=first
                members=[candidate for candidate in xml
                    if candidate.kind=="note" and
                    candidate.part_index==item.part_index and
                    candidate.measure==item.measure and
                    candidate.voice_id==item.voice_id and
                    start.onset-1e-7<=candidate.onset<=item.onset+1e-7]
                start_ratio=ratios.get(start.source_id)
                if (start_ratio is None
                        or len(members)!=start_ratio[0]
                        or members[0].source_id!=start.source_id
                        or members[-1].source_id!=item.source_id):
                    raise ValueError("Coda source tuplet has an incomplete numbered group")
                if (any(member.source_id not in ratio_notes
                        or ratios.get(member.source_id)!=start_ratio
                        for member in members) or
                        any(abs(left.end-right.onset)>1e-7
                        for left,right in zip(members,members[1:]))):
                    raise ValueError("Coda source tuplet must be a complete contiguous ratio group")
                rest_members=[(i,m) for i,m in enumerate(members) if m.is_rest]
                if len(rest_members)>1 or any(
                        i in (0,len(members)-1) for i,_ in rest_members):
                    raise ValueError("Coda only supports one interior tuplet rest")
                ids=tuple(member.source_id for member in members)
                if involved.intersection(ids):
                    raise ValueError("Coda source tuplets share ambiguous notes")
                involved.update(ids)
                groups.append(CodaTupletGroup(
                    ids,start_ratio[0],start_ratio[1],
                    number,start_attrs,tuple(sorted(attrs.items())),
                    tuple(CodaTupletRest(
                        item.source_id,item.onset,item.end,item.measure)
                        for _,item in rest_members)))
    if opened or ratio_notes != involved:
        raise ValueError("Coda source tuplet is incomplete or has unowned ratio notes")
    return tuple(groups)


def verify_projected_tuplets(groups: tuple[CodaTupletGroup, ...],
                             xml: str, bindings: dict) -> None:
    """Check generated ratio, eighth glyph type and authored bracket endpoints."""
    if not groups:
        return
    generated=ET.fromstring(xml)
    by_source={}
    for element in generated.findall(".//{*}note[@id]"):
        info=bindings.get(element.get("id"))
        if info and info.get("is_attack"):
            if info["source_id"] in by_source:
                raise ValueError("Coda tuplet has duplicated attack glyph ownership")
            by_source[info["source_id"]]=element
    for group in groups:
        for index,source_id in enumerate(group.source_ids):
            note=by_source.get(source_id)
            if note is None:
                raise ValueError("Coda tuplet lost a source notehead")
            ratio=note.find("{*}time-modification")
            if (ratio is None or
                    ratio.findtext("{*}actual-notes")!=str(group.actual) or
                    ratio.findtext("{*}normal-notes")!=str(group.normal) or
                    note.findtext("{*}type")!="eighth"):
                raise ValueError("Coda changed an authored tuplet ratio")
            marks=note.findall("{*}notations/{*}tuplet")
            expected = (group.start_attrs if index==0
                        else group.stop_attrs if index==len(group.source_ids)-1 else None)
            if expected is None:
                if marks:
                    raise ValueError("Coda added an unowned middle tuplet mark")
                continue
            candidates=[m for m in marks
                        if m.get("type")==dict(expected).get("type")
                        and m.get("number","1")==group.number]
            if len(candidates)!=1 or len(marks)!=1 or any(
                    candidates[0].get(key)!=value for key,value in expected):
                raise ValueError("Coda changed source tuplet group styling")
