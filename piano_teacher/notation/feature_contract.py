"""Existing note-feature evidence vocabulary and fixed measurement thresholds.

No recognition, source geometry or mutable verification session lives here.
"""
GLYPH_MINIMUM = .72
FAMILY_MARGIN = .05
STATUSES = ('verified', 'unverified', 'ambiguous', 'unsupported', 'mismatch')
FLAG_COUNTS = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4, '128th': 5}
ACCIDENTALS = {'flat': 'acc_flat', 'natural': 'acc_natural', 'sharp': 'acc_sharp',
               'double-flat': 'acc_double_flat', 'flat-flat': 'acc_double_flat',
               'double-sharp': 'acc_double_sharp'}
ALTERATIONS = {-2: 'double-flat', -1: 'flat', 0: 'natural', 1: 'sharp', 2: 'double-sharp'}


def feature_result(status, reason, **evidence):
    return dict(status=status, reason=reason, evidence=evidence)
