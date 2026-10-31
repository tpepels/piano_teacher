"""Audited subset of source expressive marks in Coda rhythm projections.

The production lesson compiler already knows how to attach author slurs,
articulations and beams. This guard only permits them for source attacks
whose clock is unchanged and checks every required mark in generated XML.
No copied author mark is silently treated as successfully retained.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ..exercise_contracts import TimingPlan
from ..music import Piece
from .coda_matrix import MatrixScore


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class SourceNoteMarks:
    source_id: str
    slurs: tuple[tuple[tuple[str, str], ...], ...]
    articulations: tuple[str, ...]
    beams: tuple[tuple[str, str], ...]
    stem: str | None


@dataclass(frozen=True)
class SourceBarTie:
    source_id: str
    boundary: float
    sounding_end: float


@dataclass(frozen=True)
class AnnotationObligations:
    notes: tuple[SourceNoteMarks, ...]
    dynamics: tuple[str, ...]
    ties: tuple[SourceBarTie, ...]


def source_annotation_obligations(piece: Piece, timing: TimingPlan, *,
                                  factor: int) -> AnnotationObligations:
    source = ET.fromstring(piece.source_musicxml)
    index = {n.source_id: (n.start, n.end) for n in timing.original.notes}
    exercises = {n.source_id: (n.start, n.end)
                 for n in timing.exercise_phrase.notes}
    if len(index) != len(timing.original.notes) or set(index) != set(exercises):
        raise ValueError("Coda annotations require unique, unchanged source ownership")

    def unchanged(sid: str) -> bool:
        return (sid in index and sid in exercises
                and all(abs(a-b) < 1e-7
                        for a,b in zip(index[sid],exercises[sid])))

    marks = []
    dynamics = []
    has_source_ties = False
    for pi, part in enumerate(source.findall("{*}part")):
        for mi, measure in enumerate(part.findall("{*}measure")):
            saw_note = False
            for ordinal, child in enumerate(measure):
                tag = _tag(child)
                if tag == "direction":
                    if factor != 1 or saw_note:
                        raise ValueError("Coda cannot safely retime source directions")
                    types = child.findall("{*}direction-type")
                    if len(types) != 1 or len(types[0]) != 1 or (
                            _tag(types[0][0]) != "dynamics"):
                        raise ValueError("Unsupported Coda source direction")
                    names = list(types[0][0])
                    if len(names) != 1 or _tag(names[0]) not in {
                            "p","pp","ppp","mp","mf","f","ff","fff"}:
                        raise ValueError("Unsupported Coda source dynamics")
                    if child.find("{*}offset") is not None:
                        raise ValueError("Coda cannot move an offset source direction")
                    dynamics.append(_tag(names[0]))
                if tag != "note":
                    continue
                saw_note = True
                source_id=f"xml-p{pi}-m{mi}-e{ordinal}"
                declared=child.findall("{*}tie")
                declared+=child.findall("{*}notations/{*}tied")
                if declared:
                    has_source_ties=True
                    if factor!=1 or any(
                            set(m.attrib)!={"type"} or m.get("type") not in
                            ("start","stop") or len(m) for m in declared):
                        raise ValueError("Coda only supports plain, unretimed source-bar ties")
                slurs=[]
                articulations=[]
                for group in child.findall("{*}notations"):
                    for mark in group:
                        if _tag(mark)=="slur":
                            if (mark.get("type") not in ("start","stop")
                                    or set(mark.attrib)-{"number","type","placement"}):
                                raise ValueError("Unsupported source slur markup")
                            slurs.append(tuple(sorted(mark.attrib.items())))
                        elif _tag(mark)=="tied":
                            # Sounding tie chains are verified as one
                            # original source attack below, not as separate
                            # re-attack source-note identities.
                            continue
                        elif _tag(mark)=="articulations":
                            if not len(mark) or any(
                                    _tag(m) not in ("staccato","tenuto","accent")
                                    or m.attrib or len(m) for m in mark):
                                raise ValueError("Unsupported Coda articulation")
                            articulations.extend(_tag(m) for m in mark)
                        else:
                            raise ValueError("Coda cannot yet transform authored tie/tuplet/ornament markup")
                beams=tuple((mark.get("number","1"),(mark.text or "").strip())
                            for mark in child.findall("{*}beam"))
                if any(level!="1" or kind not in ("begin","continue","end")
                       for level,kind in beams):
                    raise ValueError("Unsupported source beam shape")
                stem=child.findtext("{*}stem")
                if not (slurs or articulations or beams or stem):
                    continue
                if factor != 1 or not unchanged(source_id):
                    raise ValueError("Coda annotations cannot follow a retimed source attack")
                marks.append(SourceNoteMarks(source_id,tuple(slurs),
                            tuple(articulations),beams,stem))
    ties=[]
    if has_source_ties or any(mark.slurs for mark in marks):
        matrix = MatrixScore.from_phrase(
            timing.original.phrase,boundaries=piece.bar_boundaries,
            source_musicxml=piece.source_musicxml)
        links = matrix.source_connectors()
        slurs = [link for link in links if link.kind=="slur"]
        if any(mark.slurs for mark in marks):
            if not slurs or any(link.issue is not None or
                                link.start_source_id not in index or
                                link.stop_source_id not in index for link in slurs):
                raise ValueError("Unpaired or unsupported source slur cannot be preserved")
            if any(not unchanged(sid)
                   for sid in matrix.connector_protected_source_ids()
                   if sid in index):
                raise ValueError("Coda cannot retime a note inside an authored slur")
        if has_source_ties:
            arcs=[link for link in links if link.kind=="tie"]
            source_by_id={item.source_id:item for item in matrix.notation_elements}
            if not arcs or any(link.issue is not None for link in arcs):
                raise ValueError("Coda cannot preserve incomplete source ties")
            seen=set()
            for arc in arcs:
                start=source_by_id.get(arc.start_source_id)
                stop=source_by_id.get(arc.stop_source_id)
                expected=index.get(arc.start_source_id)
                boundary=arc.stop_beat
                if (start is None or stop is None or expected is None
                        or stop.end is None or boundary is None
                        or arc.start_source_id in seen
                        or arc.stop_source_id in index
                        or not any(abs(boundary-b)<1e-7
                                   for b in piece.bar_boundaries[1:-1])
                        or abs(start.onset-expected[0])>1e-7
                        or abs(stop.end-expected[1])>1e-7
                        or not unchanged(arc.start_source_id)):
                    raise ValueError("Coda only supports complete unchanged ties at source barlines")
                seen.add(arc.start_source_id)
                ties.append(SourceBarTie(arc.start_source_id,boundary,stop.end))
    return AnnotationObligations(tuple(marks),tuple(dynamics),tuple(ties))


def verify_annotation_projection(obligations: AnnotationObligations,
                                 musicxml: str, bindings: dict) -> None:
    """Compare the *actual* compiler output with every source annotation."""
    if not obligations.notes and not obligations.dynamics and not obligations.ties:
        return
    generated=ET.fromstring(musicxml)
    targets={}
    for note in generated.findall(".//note[@id]"):
        info=bindings.get(note.get("id"))
        if info and info["is_attack"]:
            source_id=info["source_id"]
            if source_id in targets:
                raise ValueError("Ambiguous generated annotation attack")
            targets[source_id]=note
    for required in obligations.notes:
        dest=targets.get(required.source_id)
        if dest is None:
            raise ValueError("Coda annotation lost its original notehead")
        actual_slurs=tuple(tuple(sorted(m.attrib.items()))
            for m in dest.findall("{*}notations/{*}slur"))
        actual_articulations=tuple(_tag(m)
            for m in dest.findall("{*}notations/{*}articulations/*"))
        actual_beams=tuple((m.get("number","1"),(m.text or "").strip())
            for m in dest.findall("{*}beam"))
        if (Counter(actual_slurs)!=Counter(required.slurs)
                or Counter(actual_articulations)!=Counter(required.articulations)
                or Counter(actual_beams)!=Counter(required.beams)
                or dest.findtext("{*}stem")!=required.stem):
            raise ValueError(f"Coda changed authored annotation at {required.source_id}")
    for tie in obligations.ties:
        starts=[]
        stops=[]
        for note in generated.findall(".//note[@id]"):
            info=bindings.get(note.get("id"))
            if not info or info["source_id"]!=tie.source_id:
                continue
            at=float(info["display_beat"])
            length=int(note.findtext("{*}duration","0"))/10080
            if abs(at+length-tie.boundary)<1e-7:
                if (note.find("{*}tie[@type='start']") is not None and
                        note.find("{*}notations/{*}tied[@type='start']") is not None):
                    starts.append(note)
            if abs(at-tie.boundary)<1e-7:
                if (note.find("{*}tie[@type='stop']") is not None and
                        note.find("{*}notations/{*}tied[@type='stop']") is not None):
                    stops.append(note)
        if len(starts)!=1 or len(stops)!=1:
            raise ValueError("Coda lost the original sounding tie at its barline")
    # Replacing a complete source beam group must never leave a dangling
    # auto-generated begin/end on an adjacent changed or omitted note.
    # Every rendered voice's primary beam sequence must be internally
    # balanced within the original measure.
    for part in generated.findall("{*}part"):
        for measure in part.findall("{*}measure"):
            by_voice = {}
            for note in measure.findall("{*}note"):
                if note.find("{*}rest") is not None or (
                        note.find("{*}chord") is not None):
                    continue
                voice=note.findtext("{*}voice","1")
                by_voice.setdefault(voice,[]).append(note)
            for notes in by_voice.values():
                opened=False
                for note in notes:
                    beams=[mark for mark in note.findall("{*}beam")
                           if mark.get("number","1")=="1"]
                    if len(beams)>1:
                        raise ValueError("Coda output duplicates primary beams")
                    kind=(beams[0].text or "").strip() if beams else None
                    if kind=="begin":
                        if opened:
                            raise ValueError("Coda beam group was split without an end")
                        opened=True
                    elif kind=="continue":
                        if not opened:
                            raise ValueError("Coda beam group lost its beginning")
                    elif kind=="end":
                        if not opened:
                            raise ValueError("Coda beam group lost its beginning")
                        opened=False
                    elif kind is not None:
                        raise ValueError("Unsupported Coda output beam mark")
                    elif opened:
                        raise ValueError("Coda beam group has an unmarked middle")
                if opened:
                    raise ValueError("Coda beam group has no ending")
    actual_dynamics=tuple(_tag(m) for m in
        generated.findall(".//direction/direction-type/dynamics/*"))
    if Counter(actual_dynamics)!=Counter(obligations.dynamics):
        raise ValueError("Coda projected source dynamics inconsistently")
