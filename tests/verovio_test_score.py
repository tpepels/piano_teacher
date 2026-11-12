"""Test models engraved through a real Verovio page.

Chord templates exist only for chords of an engraved score: their stem and
head arrangement are read from Verovio's own pages. Tests build their
chords here instead of handing the atlas a bare model.

- ``verovio_pages(xml)``: Verovio's pages for a test's own MusicXML, whose
  note ids are the test model's event ids.
- ``prepare_musicxml(xml, folder)``: the whole score through the import and
  preparation path of a user's file (import_piece -> ScoreArtifacts).

Not a test module.
"""
from __future__ import annotations

from pathlib import Path


def verovio_pages(xml: str) -> list[str]:
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit

    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48, "pageWidth": 900,
                               "pageHeight": 650, "svgViewBox": True,
                               "svgBoundingBoxes": True, "svgContentBoundingBoxes": True})
    assert toolkit.loadData(xml), "Verovio refused the test score"
    return [toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)]


def prepare_musicxml(xml: str, folder: Path) -> dict:
    """layout, model and pages of the whole score as one exercise."""
    from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.music import Phrase
    from piano_teacher.preprocessing_cache import PreprocessingCache

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "score.musicxml"
    path.write_text(xml)
    piece, _ = import_piece(path)
    bounds = piece.bar_boundaries
    phrase = Phrase(1, 1, len(bounds) - 1, bounds[0], bounds[-1], piece.notes)
    artifacts = ScoreArtifacts(PreprocessingCache(folder / "cache"))
    selected = ScoreSelection(piece, phrase, "both", "test", 1, path.name)
    return {"layout": artifacts.geometry(selected),
            "model": artifacts.semantic_score(selected),
            "pages": list(artifacts.engraving(selected).pages),
            "notation_xml": artifacts.notation_musicxml(selected),
            "cache": artifacts.preprocessing}


def score_xml(right: list[str], left: list[str] | None = None, *,
              divisions: int = 4, fifths: int = 0) -> str:
    """Two-staff piano MusicXML from per-measure note XML (whole rests fill
    an absent left hand)."""
    left = left or ['<note><rest/><duration>%d</duration><voice>1</voice>'
                    '<type>whole</type></note>' % (4 * divisions)] * len(right)

    def part(ident, measures, clef):
        body = []
        for number, content in enumerate(measures, 1):
            head = (f"<attributes><divisions>{divisions}</divisions><key><fifths>{fifths}"
                    "</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>"
                    f"<clef><sign>{clef[0]}</sign><line>{clef[1]}</line></clef></attributes>"
                    if number == 1 else "")
            body.append(f'<measure number="{number}">{head}{content}</measure>')
        return f'<part id="{ident}">{"".join(body)}</part>'

    return ('<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0">'
            '<part-list><score-part id="RH"><part-name>Right Hand</part-name></score-part>'
            '<score-part id="LH"><part-name>Left Hand</part-name></score-part></part-list>'
            + part("RH", right, ("G", 2)) + part("LH", left, ("F", 4)) + "</score-partwise>")


def chord_xml(names: str, kind: str = "quarter", duration: int = 4,
              stem: str | None = None, beams: tuple[str, ...] = ()) -> str:
    """One chord of a measure, from names like "C4 E4 G#4"."""
    letters = []
    for index, name in enumerate(names.split()):
        step, rest = name[0], name[1:]
        alter = rest.count("#") - rest.count("b")
        octave = int(rest.strip("#b"))
        letters.append(
            "<note>" + ("<chord/>" if index else "") + f"<pitch><step>{step}</step>"
            + (f"<alter>{alter}</alter>" if alter else "") + f"<octave>{octave}</octave></pitch>"
            f"<duration>{duration}</duration><voice>1</voice><type>{kind}</type>"
            + (f"<accidental>{'sharp' if alter > 0 else 'flat'}</accidental>" if alter else "")
            + (f"<stem>{stem}</stem>" if stem else "")
            + ("".join(f'<beam number="1">{b}</beam>' for b in beams) if not index else "")
            + "</note>")
    return "".join(letters)


def rest_xml(duration: int, kind: str, dots: int = 0) -> str:
    return (f"<note><rest/><duration>{duration}</duration><voice>1</voice>"
            f"<type>{kind}</type>" + "<dot/>" * dots + "</note>")


def chords_by_names(model: dict) -> dict[tuple, dict]:
    """(measure, names bottom to top) -> leader event, for every chord."""
    from piano_teacher.notation.assets.chords import chord_lanes, head_order

    def name(e):
        s = e["spelling"]
        return f"{s['step']}{'#' * max(0, s.get('alter') or 0)}{'b' * max(0, -(s.get('alter') or 0))}{s['octave']}"

    return {(leader["measure"], " ".join(name(n) for n in head_order(notes))): leader
            for leader, notes, _ in chord_lanes(model)}
