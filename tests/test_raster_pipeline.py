"""Actual SVG to PNG rendering tests independent of Godot/Verovio binaries."""
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from piano_teacher.raster import rasterize_score
from piano_teacher.server import PracticeEngine

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
        rasterize_score(VEROVIO_GLYPH, width=9000)


def test_engine_caches_png_per_requested_resolution(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    class FakeScore:
        pages = (VEROVIO_GLYPH,)
    monkeypatch.setattr(engine, "engraving", lambda: FakeScore())
    calls = []
    def fake_raster(svg, *, width=2000):
        calls.append(width)
        return f"png-{width}".encode()
    monkeypatch.setattr("piano_teacher.server.rasterize_score", fake_raster)
    try:
        assert engine.engraved_png(width=4200) == b"png-4200"
        assert engine.engraved_png(width=4200) == b"png-4200"
        assert engine.engraved_png(width=3000) == b"png-3000"
        assert engine.engraved_png(width=4200) == b"png-4200"
        assert calls == [4200, 3000, 4200]
        assert len(engine._page_png) == 1
        with pytest.raises(ValueError, match="width"):
            engine.engraved_png(width=9000)
    finally:
        engine.db.close()


def test_engine_caches_png_and_validates_page(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)

    class FakeScore:
        pages = (VEROVIO_GLYPH,)

    calls = []
    monkeypatch.setattr(engine, "engraving", lambda: FakeScore())
    def fake_raster(svg):
        calls.append(svg)
        return b"png-data"
    monkeypatch.setattr("piano_teacher.server.rasterize_score", fake_raster)
    try:
        assert engine.engraved_png() == b"png-data"
        assert engine.engraved_png() == b"png-data"
        assert len(calls) == 1
        with pytest.raises(ValueError, match="Invalid score page"):
            engine.engraved_png(5)
    finally:
        engine.db.close()


def test_png_http_endpoint_and_svg_debug(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from piano_teacher.server import Handler
    engine = PracticeEngine(tmp_path, enable_midi=False)
    monkeypatch.setattr(engine, "engraved_png",
                        lambda page=0, *, width=1000: rasterize_score(VEROVIO_GLYPH, width=width)
                        if page == 0 else (_ for _ in ()).throw(ValueError("Invalid score page")))
    monkeypatch.setattr(engine, "engraved", lambda page=0: VEROVIO_GLYPH)
    class LocalHandler(Handler):
        pass
    LocalHandler.engine = engine
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/score.png?page=0", timeout=5) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read(8) == bytes.fromhex("89504e470d0a1a0a")
        with urlopen(base + "/score.png?page=0&width=2400", timeout=5) as response:
            sharp = Image.open(BytesIO(response.read()))
            assert sharp.size == (2400, 1440)
        with urlopen(base + "/score.svg?page=0", timeout=5) as response:
            assert response.headers["Content-Type"].startswith("image/svg+xml")
            assert b"<svg" in response.read()
        with pytest.raises(HTTPError) as err:
            urlopen(base + "/score.png?page=42", timeout=5)
        assert err.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        engine.db.close()


def test_godot_loads_png_with_same_notehead_coordinates():
    script = (Path(__file__).resolve().parents[1] / "godot/main.gd").read_text()
    assert '"/score.png?page=%d&width=%d"' in script
    assert "ScoreQuality.png_width(source_layout, score_frame.size.y)" in script
    assert "picture.load_png_from_buffer(body)" in script
    assert 'score_overlay.image_size = strip["size"]' in script
    # Long scores defer texture uploads but share the exact same engraving
    # geometry as short scores; the score view itself is only a sentinel.
    assert 'ScoreStrip.build(' in script
    assert 'source_layout, page_images, should_defer' in script
    assert 'score_view.texture = ImageTexture.create_from_image(ready_pixel)' in script
    # Both transparent and opaque margins are excluded; strip tiles preserve
    # the real geometry and avoid a single oversized GPU texture.
    assert "var opaque_bounds := _visible_engraving_bounds(picture)" in script
    assert "score_overlay.crop_origin = score_crop_origin" in script
    assert "score_overlay.active_page = current_page" in script
    overlay = (Path(__file__).resolve().parents[1] / "godot/score_overlay.gd").read_text()
    assert "func _sheet_xy(x: float, y: float)" in overlay
    assert "picture.load_svg_from_buffer" not in script


def test_practice_navigation_no_vertical_letter_wrapping():
    script = (Path(__file__).resolve().parents[1] / "godot/main.gd").read_text()
    # Flow navigation preserves full labels by wrapping actions to a new row.
    # The old fixed HBox became unreadable when buttons were squeezed.
    assert "practice_navigation = HFlowContainer.new()" in script
    assert "practice_navigation.add_theme_constant_override(\"v_separation\"" in script
    assert "practice_controls = controls" in script
    assert "controls := HFlowContainer.new()" in script
    assert "button.clip_text = false" in script
    assert "practice_header = HBoxContainer.new()" in script
    assert "tempo.custom_minimum_size = Vector2(190, 0)" in script
    assert "speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF" in script
    assert "hand_label.autowrap_mode = TextServer.AUTOWRAP_OFF" in script
    assert "progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF" in script
