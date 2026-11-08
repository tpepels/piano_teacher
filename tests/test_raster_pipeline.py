"""Actual SVG to PNG rendering tests independent of Godot/Verovio binaries."""
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from piano_teacher.engraving.raster import rasterize_score
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from test_phase1_camera import native_camera_run

VEROVIO_GLYPH = """<svg xmlns="http://www.w3.org/2000/svg"
 xmlns:xlink="http://www.w3.org/1999/xlink" width="1000" height="600"
 viewBox="0 0 1000 600">
 <defs><symbol id="glyph"><path d="M0 0H200V45H0Z" fill="#111111"/></symbol></defs>
 <g class="system"><g class="note" id="n1"><g class="notehead">
   <use xlink:href="#glyph" x="100" y="150"/>
 </g></g></g>
 <path d="M100 160 H920 M100 180 H920 M100 200 H920" stroke="black"/>
 </svg>"""


def test_verovio_style_symbol_use_has_visible_pixels():
    data = rasterize_score(VEROVIO_GLYPH, width=1000)
    assert data.startswith(b"\\x89PNG\\r\\n\\x1a\\n".decode("unicode_escape").encode("latin1"))
    image = Image.open(BytesIO(data))
    assert image.size == (1000, 600)
    assert all(channel < 60 for channel in image.getpixel((110, 160))[:3])


def test_higher_resolution_engraving_preserves_vector_sharpness():
    standard = Image.open(BytesIO(rasterize_score(VEROVIO_GLYPH, width=1000)))
    detailed = Image.open(BytesIO(rasterize_score(VEROVIO_GLYPH, width=3600)))
    assert detailed.size == (3600, 2160)
    # The same SVG path is rerasterized by Cairo at the new resolution;
    # it is NOT a blurred resize of the original PNG.
    # Cairo independently antialiases the same vector at each resolution;
    # sampled edge pixels need not have identical gray values.
    original = standard.getpixel((110, 160))[:3]
    rerendered = detailed.getpixel((396, 576))[:3]
    assert max(abs(a-b) for a,b in zip(original, rerendered)) <= 24
    assert detailed.getpixel((400, 720))[0] < 90


def test_rasterizer_rejects_blank_page():
    blank = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'
    with pytest.raises(RuntimeError, match="blank page"):
        rasterize_score(blank)


def test_rasterizer_rejects_corrupted_svg_and_excessive_output():
    with pytest.raises(RuntimeError, match="Cannot rasterize"):
        rasterize_score("<svg broken>")
    with pytest.raises(ValueError, match="width"):
        rasterize_score(VEROVIO_GLYPH, width=13000)


def test_production_native_view_uses_source_note_identities(native_camera_run):
    # Raster utilities above serve offline verification only. Production
    # coordinates now come from the real native CanvasItem and source model.
    report, _ = native_camera_run
    # READY holds its take offscreen; source identities show once it plays.
    ready = next(s for s in report["samples"] if s["label"] == "ready")
    assert not ready["heads"] and ready["visible_count"] == 0
    playing = next(s for s in report["samples"] if s["label"] == "playing")
    assert playing["heads"] and playing["visible_count"] > 0
    assert len({h["id"] for h in playing["heads"]}) == len(playing["heads"])
    assert report["same_atlas"] and report["same_index"]


def test_practice_navigation_no_vertical_letter_wrapping():
    # The Practice header and transport moved to practice_screen.gd. Labels
    # stay on one line (title and progress never wrap), the tempo control is a
    # fixed-width button, and the transport row is a flow container that
    # wraps whole buttons instead of squeezing them.
    script = (Path(__file__).resolve().parents[1] / "godot/practice_screen.gd").read_text()
    assert "practice_controls = controls" in script
    assert "controls := HFlowContainer.new()" in script
    assert "button.clip_text = false" in script
    assert "practice_header = HBoxContainer.new()" in script
    assert "title_label.autowrap_mode = TextServer.AUTOWRAP_OFF" in script
    assert "progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF" in script
    assert "speed_label.custom_minimum_size = Vector2(182,40)" in script
