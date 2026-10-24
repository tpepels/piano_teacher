"""Native signature positions must follow actual Verovio staff-relative ink."""
import json
from pathlib import Path
import re
import shutil
import subprocess
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_key_positions_match_verovio_for_every_supported_clef_line(tmp_path):
    import verovio
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot is required")
    toolkit = verovio.toolkit()
    toolkit.setOptions({"breaks": "none", "header": "none", "footer": "none"})
    cases = []
    ns = "{http://www.w3.org/2000/svg}"
    for sign in ("G", "F", "C"):
        for line in range(1, 6):
            for fifths in (-7, 7):
                xml = f'''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>{fifths}</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>{sign}</sign><line>{line}</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>'''
                assert toolkit.loadData(xml)
                svg = ET.fromstring(toolkit.renderToSVG(1))
                staff = next(n for n in svg.iter() if n.get("class") == "staff")
                rails = [float(re.findall(r"-?[0-9.]+", n.get("d"))[1])
                         for n in list(staff) if n.tag == ns+"path"][:5]
                gap = (max(rails)-min(rails))/4
                key = next(n for n in staff.iter() if n.get("class") == "keySig")
                ys = [float(re.search(r"translate\([^,]+,\s*([-0-9.]+)", n.get("transform")).group(1))
                      for n in key.iter() if n.tag == ns+"use"]
                steps = [round((max(rails)-y)/gap*2) for y in ys]
                assert len(steps) == 7
                cases.append({"clef": {"sign": sign, "line": line, "octave_change": 0},
                              "fifths": fifths, "steps": steps})
                if line == {"G": 2, "F": 4, "C": 3}[sign]:
                    cases.append({"clef": {"sign": sign}, "fifths": fifths, "steps": steps})
    path = tmp_path/"reference.json"
    path.write_text(json.dumps(cases))
    result = subprocess.run([godot, "--headless", "--path", str(ROOT/"godot"),
        "--script", str(ROOT/"tests/godot/native_key_signatures.gd"), "--", str(path)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    assert "NATIVE_KEY_FAILURES:0" in result.stdout
