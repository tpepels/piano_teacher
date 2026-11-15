"""The physical shaft oracle uses independently engraved source beams.

No Godot bitmap, native asset atlas, or engine-provided stem direction can
replace an independently rendered stem path. Compact SVG and full diagnostic
SVG must measure the same authored score geometry.
"""
from pathlib import Path
import pytest
from piano_teacher.notation.stem_pixels import source_verovio_stem_extensions


RAILS = "".join(
    '<path d="M0 %d L2000 %d" stroke-width="13"/>' % (v,v)
    for v in (180,360,540,720,900)
)


def _svg(note: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg"><g class="staff">'
            + RAILS + note + '</g></svg>')


def test_original_beam_end_path_uses_written_tip_not_standalone_stem(tmp_path: Path):
    # Authored source end is 567 SVG units from a registered notehead.
    # With a 180-unit staff space its 3.15-space beam stem is entirely
    # legitimate even though a standalone note would require 3.5 spaces.
    note = ('<g class="note" id="source-beam-end">'
            '<g class="notehead"><use transform="translate(400,540) scale(.72,.72)"/></g>'
            '<g class="stem"><path d="M409 568 L409 1107"/></g></g>')
    (tmp_path/'verovio-0.svg').write_text(_svg(note))
    result = source_verovio_stem_extensions(tmp_path)
    assert result["source-beam-end"]["down"] == pytest.approx(567/180)
    assert "up" not in result["source-beam-end"]


def test_diagnostic_source_svg_content_bounds_are_equally_authoritative(tmp_path: Path):
    note = ('<g class="note" id="source-up">'
            '<g class="notehead"><use transform="translate(400,540) scale(.72,.72)"/></g>'
            '<g class="stem"><g class="content-bounding-box">'
            '<rect x="400" y="-45" height="566" width="18"/></g></g></g>')
    (tmp_path/'verovio-0.svg').write_text(_svg(note))
    result = source_verovio_stem_extensions(tmp_path)
    assert result["source-up"]["up"] == pytest.approx(585/180)
    assert "down" not in result["source-up"]


def test_source_reference_is_exact_id_bound_and_absent_without_independent_svg(tmp_path: Path):
    assert source_verovio_stem_extensions(tmp_path) == {}
    (tmp_path/'verovio-0.svg').write_text(_svg(
        '<g class="note" id="different"><g class="notehead">'
        '<use transform="translate(400,540) scale(.72,.72)"/></g>'
        '<g class="stem"><path d="M409 568 L409 1107"/></g></g>'))
    result = source_verovio_stem_extensions(tmp_path)
    assert "expected-id" not in result
    assert "different" in result
