"""Original Coda explicit-excerpt and category schema (not a curriculum)."""
from piano_teacher.research.coda_author_catalog import (
    AUTHOR_REVISION, AUTHOR_CATEGORIES, AUTHOR_DOTTED_PATTERNS,
    AUTHOR_SLOWDOWN_FACTORS, catalog_requests, score_excerpt_categories,
)
from piano_teacher.research.coda_auto_chord_levels import original_chord_levels


def test_exact_pinned_source_categories_and_parameters():
    assert AUTHOR_REVISION=="a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"
    assert score_excerpt_categories()==(
        "Score Level","Part Level","Voice Level: Original",
        "Voice Level: Dotted","Voice Level: Chordified",
        "Voice Level: Slowed Down")
    assert AUTHOR_DOTTED_PATTERNS==((1.5,0.5),(0.5,1.5))
    assert AUTHOR_SLOWDOWN_FACTORS==(2,4)
    requests=catalog_requests(4,4,4)
    assert [r.category for r in requests].count("Voice Level: Original")==1
    assert [r.parameter for r in requests if r.category=="Voice Level: Dotted"]==[
        (1.5,0.5),(0.5,1.5)]
    assert [r.parameter for r in requests if r.category=="Voice Level: Chordified"]==list(
        original_chord_levels(4,4,4))
    assert [r.parameter for r in requests if r.category=="Voice Level: Slowed Down"]==[2,4]


def test_author_invalid_zero_width_not_silently_normalized():
    requests=catalog_requests(1,3,4)
    assert any(r.category=="Voice Level: Chordified" and r.parameter==0
               for r in requests)


def test_every_voice_request_is_source_catalog_category_not_lesson_order():
    req=catalog_requests(8,3,8)
    assert req
    assert all(r.category in AUTHOR_CATEGORIES for r in req)
    assert len(req)==1+2+len(original_chord_levels(8,3,8))+2
    assert len({(r.category,r.variant) for r in req})==len(req)
