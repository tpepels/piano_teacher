"""Original MusicXML remains available after note import and source caching.

It is deliberately NOT evidence that every expression is already displayed
by the native compositor. That requires a separate identity-safe mapping.
"""
from hashlib import sha256
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.preprocessing_cache import PreprocessingCache


def _decorated_source(tmp_path):
    phrase = Phrase(1, 1, 1, 0.0, 4.0, (
        Note(0.0, 1.0, 72, 0, 0, "right", "right-0"),
        Note(2.0, 3.0, 76, 0, 0, "right", "right-2"),
        Note(0.0, 4.0, 48, 1, 0, "left", "left-0"),
    ))
    root = ET.fromstring(build_lesson_score(phrase).musicxml)
    rh = root.find("./part[@id='RH']/measure")
    assert rh is not None
    directions = ET.Element("direction")
    kind = ET.SubElement(directions, "direction-type")
    dynamics = ET.SubElement(kind, "dynamics")
    ET.SubElement(dynamics, "p")
    rh.insert(1, directions)
    pedal = ET.Element("direction")
    pedal_kind = ET.SubElement(pedal, "direction-type")
    ET.SubElement(pedal_kind, "pedal", type="start")
    rh.insert(2, pedal)
    first = next(tag for tag in rh.findall("note") if tag.find("pitch") is not None)
    notations = ET.SubElement(first, "notations")
    articulations = ET.SubElement(notations, "articulations")
    ET.SubElement(articulations, "staccato")
    ornaments = ET.SubElement(notations, "ornaments")
    ET.SubElement(ornaments, "turn")
    ET.SubElement(notations, "slur", type="start", number="1")
    last = [tag for tag in rh.findall("note") if tag.find("pitch") is not None][-1]
    ET.SubElement(ET.SubElement(last, "notations"), "slur",
                  type="stop", number="1")
    xml = ET.tostring(root, encoding="unicode")
    target = tmp_path / "expressive.musicxml"
    target.write_text(xml, encoding="utf-8")
    return target


def _assert_expression_preserved(piece):
    root = ET.fromstring(piece.source_musicxml)
    assert root.find("./part[@id='RH']/measure/direction/direction-type/dynamics/p") is not None
    assert root.find(".//direction-type/pedal[@type='start']") is not None
    assert root.find(".//note/notations/articulations/staccato") is not None
    assert root.find(".//note/notations/ornaments/turn") is not None
    assert root.find(".//note/notations/slur[@type='start']") is not None
    assert root.find(".//note/notations/slur[@type='stop']") is not None


def test_original_expressions_survive_musicxml_import_and_cache(tmp_path):
    path = _decorated_source(tmp_path)
    fingerprint = sha256(path.read_bytes()).hexdigest()
    cache = PreprocessingCache(tmp_path / "cache")
    piece, _ = cache.load_import(path, fingerprint,
        importer=lambda p: (load_musicxml(p, bpm=80), None))
    _assert_expression_preserved(piece)
    reopened, _ = cache.load_import(path, fingerprint,
        importer=lambda _: (_ for _ in ()).throw(
            AssertionError("Unexpected re-import of cached MusicXML")))
    _assert_expression_preserved(reopened)
    assert reopened.source_musicxml == piece.source_musicxml
    assert [n.source_id for n in reopened.notes] == [
        n.source_id for n in piece.notes]
