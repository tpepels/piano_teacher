"""Local vector recovery keeps useful detail within raster allocation limits."""
import base64
from io import BytesIO
import math

from PIL import Image
import pytest

from piano_teacher.notation.assets import tuplets


def _svg(width=10, height=10, page_height=1000):
    # Ten SVG units are one staff space; the page raster has only 1.6 px/space.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10000 {page_height}">'
            f'<rect x="100" y="100" width="{width}" height="{height}"/></svg>')


def _image(art):
    assert art is not None
    with Image.open(BytesIO(base64.b64decode(art['png_base64']))) as raw:
        return raw.convert('RGBA')


@pytest.fixture
def allocations(monkeypatch):
    from cairosvg.surface import cairo
    original = cairo.ImageSurface
    sizes = []

    def bounded_surface(fmt, width, height):
        assert 0 < width <= 1500
        assert 0 < height <= 850
        assert width*height <= tuplets.MAX_RASTER_PIXELS
        sizes.append((width, height))
        return original(fmt, width, height)

    monkeypatch.setattr(cairo, 'ImageSurface', bounded_surface)
    return sizes


@pytest.mark.parametrize('width,height,bounds', [
    (600, 20, [0, 0, 15000, 500]),
    (20, 400, [0, 0, 500, 10000]),
])
def test_large_ink_reduces_density_without_losing_physical_bounds(
        allocations, width, height, bounds):
    art = tuplets.crop_art(_svg(width, height), .01, (.01, .1), 'bracket')
    image = _image(art)
    assert len(allocations) == 1
    assert image.getchannel('A').getextrema()[1] == 255
    assert art['bounds'] == pytest.approx(bounds, abs=32)
    density = image.width*250/art['bounds'][2]
    assert 8 <= density < 32


def test_pixel_budget_also_reduces_density_before_allocating(monkeypatch, allocations):
    monkeypatch.setattr(tuplets, 'MAX_RASTER_PIXELS', 50_000)
    art = tuplets.crop_art(_svg(200, 200), .01, (.01, .1), 'bracket')
    image = _image(art)
    assert len(allocations) == 1
    assert image.width*image.height <= 50_000
    assert art['bounds'] == pytest.approx([0, 0, 5000, 5000], abs=32)
    assert 8 <= image.width*250/art['bounds'][2] < 32


def test_small_numeral_keeps_32_pixels_per_space(allocations):
    art = tuplets.crop_art(_svg(), .01, (.01, .1), 'number')
    image = _image(art)
    assert len(allocations) == 1
    assert 32 <= image.width <= 34
    assert 32 <= image.height <= 34
    assert image.width*250/art['bounds'][2] == pytest.approx(32)
    assert art['bounds'] == pytest.approx([0, 0, 250, 250], abs=16)


@pytest.mark.parametrize('width,height,budget', [
    (2000, 10, 8_000_000),
    (10, 1200, 8_000_000),
    (200, 200, 1000),
])
def test_ink_that_cannot_fit_at_useful_density_is_rejected_before_allocation(
        monkeypatch, allocations, width, height, budget):
    monkeypatch.setattr(tuplets, 'MAX_RASTER_PIXELS', budget)
    page_height = max(1000, height+200)
    assert tuplets.crop_art(_svg(width, height, page_height),
                            10/page_height, (0, 0), 'bracket') is None
    assert allocations == []


@pytest.mark.parametrize('staff_space', [0, -1, math.nan, math.inf, 1e-320])
def test_invalid_local_staff_scale_does_not_allocate(allocations, staff_space):
    assert tuplets._local_vector_art(_svg(), staff_space, (0, 0), 'number') is None
    assert allocations == []


@pytest.mark.parametrize('origin', [(math.nan, 0), (0, math.inf)])
def test_nonfinite_origin_does_not_allocate(allocations, origin):
    assert tuplets._local_vector_art(_svg(), .01, origin, 'number') is None
    assert allocations == []


@pytest.mark.parametrize('extent', [
    (0, 0, 0, 1), (0, 0, 1, 0), (math.nan, 0, 1, 1),
    (0, 0, math.inf, 1), (1e308, 0, 1e308, 1),
])
def test_invalid_recorded_extent_does_not_allocate(monkeypatch, allocations, extent):
    from cairosvg.surface import cairo
    monkeypatch.setattr(cairo.RecordingSurface, 'ink_extents', lambda _: extent)
    assert tuplets._local_vector_art(_svg(), .01, (0, 0), 'number') is None
    assert allocations == []


def test_empty_art_does_not_allocate(allocations):
    assert tuplets._local_vector_art(_svg(0, 0), .01, (0, 0), 'number') is None
    assert allocations == []


def test_normal_page_still_uses_existing_raster_path(monkeypatch):
    def unexpected_local(*args):
        pytest.fail('Normal page entered local vector recovery')

    monkeypatch.setattr(tuplets, '_local_vector_art', unexpected_local)
    svg = _svg().replace('10000 1000', '1000 1000')
    art = tuplets.crop_art(svg, .01, (.1, .1), 'number')
    assert _image(art).size == (16, 16)
    assert art['bounds'] == pytest.approx([0, 0, 250, 250])
