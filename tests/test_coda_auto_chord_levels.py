"""The exact source algorithm's width set, including invalid zero."""
import pytest
from piano_teacher.research.coda_auto_chord_levels import original_chord_levels


@pytest.mark.parametrize(("q","n","d","expected"),[
    (4, 4, 4, (2,4,8,16)),
    (8, 4, 4, (2,4,8,16,32)),
    (3, 3, 4, (1,2,3,4,6,8,12)),
    (12, 4, 4, (2,4,6,8,12,16,24)),
    (1, 3, 4, (0,1,2,4,8,12)),
])
def test_exact_author_chord_level_set(q,n,d,expected):
    assert original_chord_levels(q,n,d)==expected


def test_invalid_arguments_fail_closed():
    for args in ((0,4,4),(4,0,4),(4,4,0),(-1,4,4),(4,4,2.0)):
        with pytest.raises(ValueError):
            original_chord_levels(*args)
