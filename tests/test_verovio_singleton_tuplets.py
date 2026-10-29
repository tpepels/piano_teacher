"""Singleton tuplet fragments preserve the real source artwork and anchor."""
import base64
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from PIL import Image
import pytest

from piano_teacher.notation.assets.tuplets import (
    classes, extract_tuplets, semantic_tuplets, source_ids, tuplet_fragments,
)
from piano_teacher.preprocessing_cache import PreprocessingCache


def singleton(event_id="solo", *, kind="note", chord=False):
    event = dict(kind=kind, staff="right", voice="1", measure=1,
                 beat=0., id=event_id, chord=False, tuplet_marks=[
                     dict(type="start", number="1", bracket="yes", show_number="both"),
                     dict(type="stop", number="1", bracket="yes", show_number="both")])
    events = [event]
    if chord:
        events.append(dict(event, id="upper", chord=True, tuplet_marks=[]))
    return dict(notation_events=events)


def source_svg(*, kind="note", chord=False, bracket=True, hidden=False):
    import verovio
    from piano_teacher.score import _create_verovio_toolkit

    pitched = "<rest/>" if kind == "rest" else "<pitch><step>C</step><octave>5</octave></pitch>"
    marks = (f'<notations><tuplet type="start" number="1" bracket="{"yes" if bracket else "no"}" '
             f'show-number="{"none" if hidden else "both"}"/>'
             '<tuplet type="stop" number="1"/></notations>')
    timing = ('<duration>19</duration><voice>1</voice><type>quarter</type>'
              '<time-modification><actual-notes>20</actual-notes>'
              '<normal-notes>19</normal-notes></time-modification>')
    notes = f'<note id="solo">{pitched}{timing}{marks}</note>'
    if chord:
        notes += ('<note id="upper"><chord/><pitch><step>E</step><octave>5</octave></pitch>'
                  + timing + '</note>')
    xml = ('<score-partwise version="4.0"><part-list><score-part id="RH">'
           '<part-name>Right</part-name></score-part></part-list><part id="RH">'
           '<measure number="1" implicit="yes"><attributes><divisions>20</divisions>'
           '<time><beats>4</beats><beat-type>4</beat-type></time>'
           '<clef><sign>G</sign><line>2</line></clef></attributes>' + notes + '</measure></part></score-partwise>')
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions(dict(inputFrom="xml", scale=48, pageWidth=900, pageHeight=650,
                                   svgViewBox=True, svgBoundingBoxes=True, svgContentBoundingBoxes=True))
    assert toolkit.loadData(xml)
    return toolkit.renderToSVG(1)


@pytest.mark.parametrize("kind", ["note", "rest"])
def test_one_explicit_start_stop_event_remains_a_required_semantic_group(kind):
    assert semantic_tuplets(singleton(kind=kind)) == {("solo",): {"staff": "right"}}


@pytest.mark.parametrize("kind,chord,bracket", [
    ("note", False, True), ("note", False, False),
    ("note", True, True), ("rest", False, True),
])
def test_actual_verovio_singleton_number_and_bracket_are_retained(kind, chord, bracket):
    svg = source_svg(kind=kind, chord=chord, bracket=bracket)
    # Confirm the independent source really has ink; container count alone
    # cannot authorize inventing a tuplet numeral.
    root = ET.fromstring(svg)
    groups = [n for n in root.iter() if classes(n) == {"tuplet"}]
    assert len(groups) == 1
    assert any("tupletNum" in classes(n) for n in groups[0].iter())
    assert source_ids(groups[0]) == (("solo", "upper") if chord else ("solo",))
    result = extract_tuplets([svg], singleton(kind=kind, chord=chord))
    assert set(result) == {"solo"}
    fragment = result["solo"]
    assert fragment["source"] == "verovio-engraved-tuplet"
    assert fragment["note_ids"] == ["solo"]
    assert fragment["span"] > 0
    assert bool(fragment["bracket"]) == bracket
    artwork = [fragment["number"], *([fragment["bracket"]] if bracket else [])]
    assert fragment["span"] == max(part["bounds"][2] for part in artwork)
    for part in artwork:
        with Image.open(BytesIO(base64.b64decode(part["png_base64"]))) as image:
            assert image.getchannel("A").getbbox() is not None
        assert part["units_per_space"] == 250
        assert part["bounds"][2] > 0 and part["bounds"][3] > 0


def test_singleton_fragment_retains_its_actual_offset_instead_of_recentering():
    import piano_teacher.source_svg as geometry
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">
    <g class="tuplet"><g class="tupletNum"><rect x="130" y="100" width="40" height="20"/></g>
    <g class="tupletBracket"><path d="M90 150L90 140L180 140L180 150" fill="none" stroke="black" stroke-width="2"/></g>
    <g class="note" id="solo"><use href="#head" x="100" y="200"/></g></g>
    <defs><circle id="head" r="5"/></defs></svg>'''
    original = geometry.parse_svg_geometry
    # This fixture has no printed staff. Supply only the externally measured
    # staff lattice; actual crop geometry and anchor coordinates remain real.
    def measured(page):
        found = original(page)
        return SimpleNamespace(elements=found.elements,
            staff_systems={"system-0": {"staff_lines": [.55, .575, .6, .625, .65]}})
    from unittest.mock import patch
    with patch.object(geometry, "parse_svg_geometry", measured):
        item = extract_tuplets([svg], singleton())["solo"]
    # Numeral left edge is 30px right of the sole source anchor, not centred
    # on it. One staff space is 10px, or 250 normalized units.
    assert item["number"]["bounds"][0] == pytest.approx(750)
    assert item["number"]["bounds"][2] == pytest.approx(1000)


def test_hidden_singleton_does_not_acquire_invented_artwork():
    svg = source_svg(bracket=False, hidden=True)
    assert semantic_tuplets(singleton())
    assert extract_tuplets([svg], singleton()) == {}


def test_unpaired_ratio_does_not_invent_a_semantic_singleton():
    model = singleton()
    model["notation_events"][0]["tuplet_marks"].pop()
    assert semantic_tuplets(model) == {}


def test_idless_graphic_cannot_choose_between_coincident_singletons(monkeypatch):
    import piano_teacher.source_svg as geometry
    svg = source_svg(bracket=False)
    root = ET.fromstring(svg)
    for node in root.iter():
        for child in list(node):
            if "note" in classes(child):
                node.remove(child)
    model = singleton()
    other = deepcopy(model["notation_events"][0])
    other.update(id="other", voice="2")
    model["notation_events"].append(other)
    monkeypatch.setattr(geometry, "parse_svg_geometry", lambda _: SimpleNamespace(
        elements={"solo": (.2, .5, "s"), "other": (.2, .5, "s")},
        staff_systems={"s": {"staff_lines": [.55, .575, .6, .625, .65]}}))
    assert semantic_tuplets(model) == {("solo",): {"staff": "right"}, ("other",): {"staff": "right"}}
    assert extract_tuplets([ET.tostring(root, encoding="unicode")], model) == {}


def test_singleton_artwork_roundtrips_through_cache(tmp_path, monkeypatch):
    svg = source_svg()
    expected = extract_tuplets([svg], singleton())
    assert expected
    cache = PreprocessingCache(tmp_path)
    assert tuplet_fragments([svg], singleton(), cache, "single-visible") == expected
    monkeypatch.setattr("piano_teacher.notation.assets.tuplets.extract_tuplets",
                        lambda *_: pytest.fail("Valid cached singleton was discarded"))
    assert tuplet_fragments([svg], singleton(), PreprocessingCache(tmp_path), "single-visible") == expected


@pytest.fixture
def generated_rest_source(tmp_path):
    """The real lesson builder removes XML rest IDs; the model assigns its own."""
    from dataclasses import replace
    from piano_teacher.server import PracticeEngine
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model
    from piano_teacher.score import render_layout

    path = tmp_path/"rest.musicxml"
    path.write_text('''<score-partwise version="4.0"><part-list><score-part id="RH">
    <part-name>Right Hand</part-name></score-part></part-list><part id="RH">
    <measure number="1" implicit="yes"><attributes><divisions>20</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="source-rest"><rest/><duration>19</duration><voice>1</voice><type>quarter</type>
    <time-modification><actual-notes>20</actual-notes><normal-notes>19</normal-notes></time-modification>
    <notations><tuplet type="start" number="1" bracket="yes" show-number="both"/>
    <tuplet type="stop" number="1"/></notations></note>
    <note id="after"><pitch><step>E</step><octave>5</octave></pitch><duration>20</duration>
    <voice>1</voice><type>quarter</type></note></measure></part></score-partwise>''')
    engine = PracticeEngine(tmp_path/"cache", enable_midi=False)
    try:
        engine.load(str(path))
        engine.plan.restore_location(kind="learn", first_bar=1, last_bar=1, hand="right", level="original")
        piece = engine.plan.piece
        score = build_lesson_score(engine.display_phrase(), boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, source_musicxml=piece.source_musicxml)
        xml = ET.fromstring(score.musicxml)
        target = next(n for n in xml.find("part").findall("measure/note")
                      if n.find("time-modification") is not None)
        assert target.get("id") is None
        start = target.find("notations/tuplet[@type='start']")
        start.set("show-number", "both")
        start.set("bracket", "yes")
        score = replace(score, musicxml=ET.tostring(xml, encoding="unicode"))
        model = build_score_model(score, boundaries=piece.bar_boundaries, hand="right")
        engraving = render_layout(score, 1, 1, "right", total_beats=score.phrase.end,
                                  bpm=120, continuous=True)
        return list(engraving.pages), model
    finally:
        engine.db.close()


def test_generated_model_rest_id_binds_to_the_real_anonymous_svg_rest(generated_rest_source):
    pages, model = generated_rest_source
    assert model["notation_events"][0]["id"] == "rest:right:1:0"
    result = extract_tuplets(pages, model)
    assert set(result) == {"rest:right:1:0"}
    item = result["rest:right:1:0"]
    assert item["note_ids"] == ["rest:right:1:0"]
    assert item["number"] and item["bracket"]
    assert item["span"] > 0


@pytest.mark.parametrize("damage", ["note-id", "missing-rest", "extra-rest", "staff-order", "model-rest-id"])
def test_anonymous_rest_binding_fails_closed_on_inventory_damage(generated_rest_source, damage):
    pages, original = generated_rest_source
    model = deepcopy(original)
    root = ET.fromstring(pages[0])
    if damage == "note-id":
        next(n for n in root.iter() if classes(n) == {"note"}).set("id", "wrong-source-note")
    elif damage in {"missing-rest", "extra-rest"}:
        for parent in root.iter():
            rest = next((n for n in parent if classes(n) & {"rest", "mRest"}), None)
            if rest is not None:
                if damage == "missing-rest":
                    parent.remove(rest)
                else:
                    copied = deepcopy(rest)
                    copied.set("id", "extra-source-rest")
                    parent.append(copied)
                break
    elif damage == "staff-order":
        model["staff_order"].reverse()
    else:
        model["notation_events"][0]["id"] = "rest:right:1:999"
    result = extract_tuplets([ET.tostring(root, encoding="unicode")], model)
    assert "rest:right:1:0" not in result
    assert "rest:right:1:999" not in result
