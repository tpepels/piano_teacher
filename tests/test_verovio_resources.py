"""Verify Verovio 5.x Python API and font resource initialization."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from piano_teacher.score import (_create_verovio_toolkit, _pitches_from_verovio,
                                 _verovio_object, render_layout)


def fake_install(tmp_path):
    package = tmp_path / "site-packages" / "verovio"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    data = package / "data"
    data.mkdir()
    for filename in ("Bravura.xml", "Leipzig.xml"):
        (data / filename).write_text("<font/>")
    return package / "__init__.py", data


def test_toolkit_uses_bundled_fonts(tmp_path):
    module_file, resources = fake_install(tmp_path)
    calls = []

    class Toolkit:
        def setResourcePath(self, path):
            calls.append(("resources", path))
            return True

    def constructor(init):
        calls.append(("constructor", init))
        return Toolkit()

    _create_verovio_toolkit(SimpleNamespace(__file__=str(module_file), toolkit=constructor))
    assert calls == [("constructor", False), ("resources", str(resources))]


def test_missing_and_unloadable_fonts_fail_clearly(tmp_path):
    module_file, resources = fake_install(tmp_path)
    (resources / "Leipzig.xml").unlink()
    module = SimpleNamespace(__file__=str(module_file), toolkit=lambda _: None)
    with pytest.raises(RuntimeError, match=r"Leipzig.xml.*force-reinstall"):
        _create_verovio_toolkit(module)
    (resources / "Leipzig.xml").write_text("<font/>")
    module.toolkit = lambda _: SimpleNamespace(setResourcePath=lambda path: False)
    with pytest.raises(RuntimeError, match="could not load its Bravura/Leipzig fonts"):
        _create_verovio_toolkit(module)


def test_native_and_json_data_both_supported():
    assert _verovio_object([{"on": ["n"]}], "timemap") == [{"on": ["n"]}]
    assert _verovio_object('[{"on":["n"]}]', "timemap") == [{"on": ["n"]}]
    assert _verovio_object({"pitch": 60}, "pitch") == {"pitch": 60}
    with pytest.raises(ValueError, match="unexpected"):
        _verovio_object(None, "timemap")


def test_pitch_lookup_accepts_python_dicts():
    class Toolkit:
        def renderToMIDI(self):
            return "base64"
        def getMIDIValuesForElement(self, identifier):
            return {"pitch": 66}
    assert _pitches_from_verovio(Toolkit(), [{"on": ["n1"]}]) == {"n1": 66}


def test_render_pipeline_passes_dicts_and_has_note_geometry(tmp_path, monkeypatch):
    module_file, resources = fake_install(tmp_path)

    class Measure:
        def __init__(self, n):
            self.number = n
        def getElementsByClass(self, kind):
            return []
        def getContextByClass(self, kind):
            return None

    class Part:
        def __init__(self):
            self.id = "P1"
            self.measures = [Measure(1)]
        def getElementsByClass(self, kind):
            return self.measures if kind is Measure else []
        def append(self, measure):
            self.measures.append(measure)

    class Score:
        def __init__(self):
            self.parts = []
        def recurse(self):
            return self
        def getElementsByClass(self, kind):
            return [m for p in self.parts for m in p.measures] if kind is Measure else []
        def append(self, part):
            self.parts.append(part)

    class Exporter:
        def __init__(self, score):
            assert score.parts
        def parse(self):
            return b'<score-partwise version="4.0"/>'

    music21 = ModuleType("music21")
    music21.stream = SimpleNamespace(Measure=Measure, Part=Part, Score=Score)
    music21.clef = SimpleNamespace(Clef=type("Clef", (), {}))
    music21.key = SimpleNamespace(KeySignature=type("KeySignature", (), {}))
    xml_module = ModuleType("music21.musicxml")
    exporter_module = ModuleType("music21.musicxml.m21ToXml")
    exporter_module.GeneralObjectExporter = Exporter

    class Toolkit:
        def __init__(self, init_fonts):
            assert init_fonts is False
        def setResourcePath(self, path):
            assert Path(path) == resources
            return True
        def setOptions(self, options):
            assert isinstance(options, dict)
            assert options["smuflTextFont"] == "embedded"
            assert "svgFontType" not in options
            return True
        def loadData(self, value):
            assert value.startswith("<score-partwise")
            return True
        def getPageCount(self):
            return 1
        def renderToSVG(self, page):
            return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                    '<g class="system"><g class="note" id="n1">'
                    '<g class="notehead"><use x="20" y="30" href="#glyph"/>'
                    '</g></g></g></svg>')
        def renderToTimemap(self, options):
            assert isinstance(options, dict)
            assert options["includeRests"] is True
            return [{"qstamp": 0, "on": ["n1"]}]
        def renderToMIDI(self):
            return "base64-data"
        def getMIDIValuesForElement(self, key):
            return {"pitch": 60}

    verovio = ModuleType("verovio")
    verovio.__file__ = str(module_file)
    verovio.toolkit = Toolkit
    for name, module in (("music21", music21), ("music21.musicxml", xml_module),
                         ("music21.musicxml.m21ToXml", exporter_module), ("verovio", verovio)):
        monkeypatch.setitem(sys.modules, name, module)
    notation = Score()
    notation.parts = [Part()]
    result = render_layout(notation, 1, 1, "both", total_beats=4)
    assert len(result.pages) == 1
    assert result.layout["anchors"][0]["x"] == pytest.approx(.2)
    assert result.layout["notes"][0]["pitch"] == 60
