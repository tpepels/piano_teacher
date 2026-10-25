"""The explicit annotation boundary shared by canonical audit producers.

Only authored technical/fingering elements are removed. Musical numbers,
other technical marks, source IDs and even the original XML serialization
remain intact. Native annotation paint is disabled separately at capture.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from xml.parsers import expat

from piano_teacher.music import Piece

CANONICAL_CAPTURE_CONFIG = {
    "version": 1,
    "score_ink": "canonical",
    "fingering_annotations": False,
    "transport_overlay": True,
}

_MUSICXML_NAMESPACES = {"", "http://www.musicxml.org/ns/musicxml"}


@dataclass
class _Element:
    name: str
    start: int
    opening_end: int
    empty: bool
    attributes: dict
    children: int = 0
    content: bool = False
    removals: list[tuple[int, int]] = field(default_factory=list)


def canonical_musicxml(xml: str) -> str:
    """Remove authored fingering without rewriting any remaining XML bytes.

    Empty technical/notations containers are removed only when this operation
    emptied them. Identified/attributed containers and comments are retained.
    Invalid XML or entity-generated markup fails rather than silently yielding
    a different reference. Imported piece XML has already expanded entities.
    """
    if not xml:
        return xml
    raw = xml.encode("utf-8")
    parser = expat.ParserCreate(encoding="utf-8", namespace_separator="}")
    stack: list[_Element] = []
    removals: list[tuple[int, int]] = []

    def tag_end(start: int) -> int:
        quote = 0
        for index in range(start, len(raw)):
            byte = raw[index]
            if quote:
                if byte == quote:
                    quote = 0
            elif byte in (34, 39):
                quote = byte
            elif byte == 62:
                return index + 1
        raise ValueError("Unterminated MusicXML tag")

    def start(name: str, attributes: dict) -> None:
        begin = parser.CurrentByteIndex
        if raw[begin:begin + 1] != b"<":
            # Expat points at &entity; for every expanded child. Such offsets
            # cannot identify just one child without consuming neighboring ink.
            raise ValueError("Cannot isolate fingering inside entity-generated markup")
        end = tag_end(begin)
        stack.append(_Element(name, begin, end,
                              raw[begin:end].rstrip().endswith(b"/>"), attributes))

    def content(value: str, *unused) -> None:
        if stack and value.strip():
            stack[-1].content = True

    def comment(*unused) -> None:
        if stack:
            stack[-1].content = True

    def end(name: str) -> None:
        node = stack.pop()
        finish = node.opening_end if node.empty else tag_end(parser.CurrentByteIndex)
        namespace, _, local = name.rpartition("}")
        parent = stack[-1] if stack else None
        fingering = (namespace in _MUSICXML_NAMESPACES and local == "fingering"
                     and parent is not None
                     and parent.name == (namespace + "}" if namespace else "") + "technical")
        emptied = (namespace in _MUSICXML_NAMESPACES and local in {"technical", "notations"}
                   and node.removals and not node.children and not node.content
                   and not node.attributes)
        removed = fingering or bool(emptied)
        spans = [(node.start, finish)] if removed else node.removals
        if parent is not None:
            parent.removals.extend(spans)
            if not removed:
                parent.children += 1
        else:
            removals.extend(spans)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = content
    parser.CommentHandler = comment
    parser.ProcessingInstructionHandler = comment
    parser.Parse(raw, True)
    if not removals:
        return xml
    pieces = []
    previous = 0
    for begin, finish in removals:
        pieces.append(raw[previous:begin])
        previous = finish
    pieces.append(raw[previous:])
    return b"".join(pieces).decode("utf-8")


def canonical_piece(piece: Piece) -> Piece:
    """Copy the XML reference only; keep original Note and phrase identities."""
    return replace(piece, source_musicxml=canonical_musicxml(piece.source_musicxml))
