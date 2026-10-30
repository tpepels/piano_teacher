"""Source-authored notation hierarchy for experimental Coda MMR.

Preserves original MusicXML part/measure/voice ownership, context inherited
from preceding measures, and every direct measure element. This model does
not infer a piano hand for rest-only or unvoiced notation, and cannot yet
claim fidelity to Coda's unpublished detailed MMR transformations.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .coda_source_metadata import MatrixSourceElement

# Only attributes whose value continues into later MusicXML measures.
# Unknown attributes remain in the lossless original subtree inventory.
PERSISTENT_ATTRIBUTES = frozenset({
    "divisions", "key", "time", "staves", "clef", "transpose",
    "staff-details", "measure-style", "part-symbol",
})


@dataclass(frozen=True)
class MatrixContextValue:
    kind: str
    number: str
    xml: str
    source_id: str
    source_measure: int


@dataclass(frozen=True)
class MatrixContextChange:
    value: MatrixContextValue
    onset: float


@dataclass(frozen=True)
class MatrixMeasureContext:
    part_index: int
    measure: int
    inherited: tuple[MatrixContextValue, ...]
    changes: tuple[MatrixContextChange, ...]
    resulting: tuple[MatrixContextValue, ...]

    def at_entry(self, kind: str, number: str = "1") -> MatrixContextValue | None:
        return next((v for v in self.inherited
                     if (v.kind, v.number) == (kind, number)), None)


@dataclass(frozen=True)
class MatrixNotationVoice:
    name: str
    elements: tuple[MatrixSourceElement, ...]


@dataclass(frozen=True)
class MatrixNotationMeasure:
    number: int
    elements: tuple[MatrixSourceElement, ...]
    context: MatrixMeasureContext


@dataclass(frozen=True)
class MatrixNotationPart:
    index: int
    measures: tuple[MatrixNotationMeasure, ...]
    voices: tuple[MatrixNotationVoice, ...]
    unvoiced: tuple[MatrixSourceElement, ...]

    def __post_init__(self):
        ids = [e.source_id for v in self.voices for e in v.elements]
        ids.extend(e.source_id for e in self.unvoiced)
        expected = [e.source_id for m in self.measures for e in m.elements]
        if sorted(ids) != sorted(expected) or len(set(ids)) != len(ids):
            raise ValueError("Notation part did not retain every source XML child exactly once")


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _snapshot(state: dict[tuple[str, str], MatrixContextValue]
              ) -> tuple[MatrixContextValue, ...]:
    return tuple(state[key] for key in sorted(state))


def measure_contexts(source_musicxml: str, *,
                     first_bar: int, last_bar: int,
                     notation_elements: tuple[MatrixSourceElement, ...]
                     ) -> tuple[MatrixMeasureContext, ...]:
    """Replay actual previous source attributes; never invent entry clefs.

    An initial excerpt may have no <attributes> element even though it
    inherits an earlier key/meter/clef. Source and measure ordinals remain
    immutable; no synthetic XML is inserted in the original score.
    """
    if not source_musicxml:
        if notation_elements:
            raise ValueError("Source elements require original MusicXML")
        return ()
    if first_bar < 1 or last_bar < first_bar:
        raise ValueError("Invalid original source measure range")
    root = ET.fromstring(source_musicxml)
    if _tag(root) != "score-partwise":
        raise ValueError("Expected score-partwise source MusicXML")
    selected_by_id = {e.source_id: e for e in notation_elements}
    if len(selected_by_id) != len(notation_elements):
        raise ValueError("Duplicate source notation identity")
    results: list[MatrixMeasureContext] = []
    for pi, part in enumerate(root.findall("{*}part")):
        measures = part.findall("{*}measure")
        if len(measures) < last_bar:
            raise ValueError("Missing selected MusicXML source measure")
        state: dict[tuple[str, str], MatrixContextValue] = {}
        for mi, measure in enumerate(measures[:last_bar]):
            selected = first_bar-1 <= mi < last_bar
            before = _snapshot(state)
            changes: list[MatrixContextChange] = []
            for ordinal, element in enumerate(measure):
                if _tag(element) != "attributes":
                    continue
                source_id = f"xml-p{pi}-m{mi}-e{ordinal}"
                corresponding = selected_by_id.get(source_id)
                if selected and (
                    corresponding is None or corresponding.kind != "attributes"
                    or corresponding.part_index != pi
                    or corresponding.measure != mi+1):
                    raise ValueError("Selected attribute missing from source inventory")
                for child in element:
                    kind = _tag(child)
                    if kind not in PERSISTENT_ATTRIBUTES:
                        continue
                    # MusicXML numbered clefs, keys and times must remain
                    # independent; "1" is the implicit default staff.
                    number = child.get("number", "1")
                    value = MatrixContextValue(
                        kind, number, ET.tostring(child, encoding="unicode"),
                        source_id, mi+1)
                    state[kind, number] = value
                    if selected:
                        changes.append(MatrixContextChange(
                            value, corresponding.onset))
            if selected:
                results.append(MatrixMeasureContext(
                    pi, mi+1, before, tuple(changes), _snapshot(state)))
    return tuple(results)


def notation_parts(elements: tuple[MatrixSourceElement, ...],
                   contexts: tuple[MatrixMeasureContext, ...]
                   ) -> tuple[MatrixNotationPart, ...]:
    """Partition the complete original notation inventory without duplication."""
    by_part = sorted({c.part_index for c in contexts})
    if elements and not contexts:
        raise ValueError("Source notation lacks measure contexts")
    result = []
    for pi in by_part:
        part_elements = tuple(e for e in elements if e.part_index == pi)
        part_contexts = tuple(c for c in contexts if c.part_index == pi)
        measures = tuple(MatrixNotationMeasure(
            c.measure, tuple(e for e in part_elements if e.measure == c.measure), c)
            for c in part_contexts)
        names = sorted({e.voice_id for e in part_elements if e.voice_id is not None})
        voices = tuple(MatrixNotationVoice(
            name, tuple(e for e in part_elements if e.voice_id == name))
            for name in names)
        unvoiced = tuple(e for e in part_elements if e.voice_id is None)
        result.append(MatrixNotationPart(pi, measures, voices, unvoiced))
    return tuple(result)
