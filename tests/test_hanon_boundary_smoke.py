"""Single-frame Hanon terminal flag/barline clearance in fast CI.

The separate full regression tests three viewport widths, multiple source
boundaries and repeated-score preparations. Keep only one independently
photographed failing case in short CI.
"""
import json

from PIL import Image

import test_native_boundary_clearance as boundary


def test_real_hanon_terminal_boundary_has_no_flag_contact(tmp_path, monkeypatch):
    script = boundary.HARNESS.replace(
        "for width in [1024,1536,1920]:",
        "for width in [1216]:")
    assert script != boundary.HARNESS
    monkeypatch.setattr(boundary, "HARNESS", script)
    source = json.loads((boundary.FIXTURE / "fixture.json").read_text())
    source["boundary_samples"] = [{"beat":8.0}]
    input_file = tmp_path / "hanon.json"
    input_file.write_text(json.dumps(source))
    folder, frames = boundary._capture(input_file, tmp_path)
    assert len(frames) == 1
    frame = frames[0]
    assert frame["beat"] == 8.0 and frame["width"] == 1216
    assert frame["model"] == source["model"]
    result = boundary._assert_flag_clearance(
        Image.open(folder / frame["file"]).convert("RGB"))
    assert result["contact"] == 0
