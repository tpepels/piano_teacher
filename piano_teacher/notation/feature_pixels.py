"""Bounded, source-directed note-feature evidence in retained native PNGs.

Expected facts come exclusively from the independent written-score reader.
Each call owns frame-local source grouping and cross-feature physical-ink
claims. Family measurements, structure and ledgers have independent owners;
this module retains the public proof entry points and report contracts.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image

from .adornment_pixels import (measure_flag, measure_flag_absence, measure_dot,
                               measure_chord_dots, measure_accidental)
from .feature_contract import (ACCIDENTALS, FLAG_COUNTS, STATUSES,
                               GLYPH_MINIMUM, FAMILY_MARGIN, feature_result)
from .feature_source import event_identity, read_feature_marks, required_accidentals
from .head_registration import (register_noteheads, source_chord_groups,
                                HEAD_MINIMUM, PITCH_TOLERANCE_STEPS)
from .ledger_pixels import verify_ledger_pixels
from .pixel_context import ledger_context_rows
from .pixel_ink import bright
from .pixel_proof import detect_staff_lines
from .proof import read_written_score
from .raster_matching import photographed_playhead_columns
from .reference_font import feature_glyphs
from .stem_pixels import measure_stem_ownership
from .structure_pixels import verify_structure_pixels

__all__ = ("verify_note_feature_pixels", "verify_structure_pixels", "verify_ledger_pixels")


def verify_note_feature_pixels(xml: str, folder: Path, *, hand='both', pitch_report: dict | None = None) -> dict:
    """Measure every required stem/flag/dot/accidental at written onsets.

    ``xml`` is original source XML, or the independent quantization candidate
    for MIDI. Frames are ``native-{beat:.5f}.png``. ``pitch_report`` is an
    advisory compatibility argument: current PNG registration is always
    repeated, so stale/forged evidence cannot authorize a feature. No detector
    threshold is configurable. Missing/ambiguous/unsupported requirements
    remain in the denominator. Quarter flag absence has its own bounded
    attachment measurement. Beam masks and other extra-ink checks remain
    outside this API's scope.
    """
    if hand not in ('both', 'left', 'right'):
        raise ValueError('Invalid hand mode')
    folder = Path(folder)
    written, marks, glyphs = read_written_score(xml), read_feature_marks(xml), feature_glyphs()
    accidentals = required_accidentals(written)
    by_clock = defaultdict(list)
    for note in written.symbols:
        if note['kind'] == 'note' and note['visible']:
            by_clock[round(float(note['beat']), 8)].append(note)
    measured = []
    for beat, notes in sorted(by_clock.items()):
        rows = {}
        for note in notes:
            if hand != 'both' and note['staff'] != hand:
                continue
            features = {}
            kind = note['note_type']
            if kind not in ('whole', 'breve', 'long', 'maxima'):
                features['stem'] = feature_result('unverified', 'Current-image stem evidence required')
            if kind in FLAG_COUNTS and not note['beams'] or kind not in ('whole', 'breve', 'long', 'maxima', 'half', 'quarter', *FLAG_COUNTS):
                features['flag'] = feature_result('unverified', 'Current-image flag evidence required')
            if kind == 'quarter':
                features['flag_absence'] = feature_result('unverified', 'Current-image quarter flag absence required')
            if note['dots']:
                features['dot'] = feature_result('unverified', 'Current-image augmentation-dot evidence required')
            if accidentals[note['source']['id']]:
                features['accidental'] = feature_result('unverified', 'Current-image accidental evidence required')
            row = dict(source_id=event_identity(note), measure=note['measure'], staff=note['staff'],
                       voice=note['voice'], beat=beat, spelling=note['spelling'], features=features)
            rows[note['source']['id']] = row
            measured.append(row)
        if not rows:
            continue
        filename = folder / f'native-{beat:.5f}.png'
        try:
            with Image.open(filename) as raw:
                image = raw.convert('RGB')
            staves, pixels = detect_staff_lines(image), bright(image)
        except (OSError, AssertionError, ValueError) as exc:
            for row in rows.values():
                for construct in row['features']:
                    row['features'][construct] = feature_result('unverified', f'Missing PNG or actual five-line staff evidence: {exc}', frame=filename.name)
            continue
        heads, errors = register_noteheads(pixels, staves, written, notes, glyphs,
                                  occlusion_columns=photographed_playhead_columns(image))
        groups = source_chord_groups(notes)
        owned_stems = measure_stem_ownership(pixels, groups, heads, marks)
        for group, stem in zip(groups, owned_stems):
            active = [n for n in group if n['source']['id'] in rows]
            if not active:
                continue
            if stem['status'] == 'verified':
                stem['evidence']['frame'] = filename.name
                stem['evidence']['physical_shaft_id'] = (
                    filename.name+':'+stem['evidence']['physical_shaft_id'])
            group_id = group[0]['source']['id']
            absence = None
            chord_dots=measure_chord_dots(pixels,glyphs,group,heads,staves[group[0]['staff']],written) if len(group)>1 else {
                n['source']['id']:measure_dot(pixels,glyphs,heads[n['source']['id']],n['dots'])
                for n in group if n['dots'] and n['source']['id'] in heads}
            if any(n['note_type'] == 'quarter' for n in active):
                absence = (measure_flag_absence(pixels, glyphs,
                    [heads.get(n['source']['id']) for n in group], stem,
                    {event_identity(n):chord_dots[n['source']['id']] for n in group if n['source']['id'] in chord_dots})
                    if all(n['note_type'] == 'quarter' for n in group) else
                    feature_result('ambiguous', 'Mixed written types need separate common-stem flag ownership'))
            for note in active:
                sid, kind = note['source']['id'], note['note_type']
                features = rows[sid]['features']
                head = heads.get(sid)
                if 'stem' in features:
                    features['stem'] = dict(stem)
                if 'flag_absence' in features:
                    features['flag_absence'] = dict(absence)
                if 'flag' in features:
                    if kind not in FLAG_COUNTS:
                        features['flag'] = feature_result('unsupported', 'No bounded external flag detector for this written type', note_type=kind)
                    elif stem['status'] != 'verified':
                        features['flag'] = feature_result(stem['status'], 'A flag requires its own independently attached stem endpoint')
                    elif len({n['note_type'] for n in group}) != 1:
                        features['flag'] = feature_result('ambiguous', 'Mixed written types cannot share an identified flag')
                    else:
                        features['flag'] = measure_flag(pixels, glyphs, head, stem, kind)
                        features['flag']['_group_id'] = group_id
                for construct in ('dot', 'accidental'):
                    if construct not in features:
                        continue
                    if head is None:
                        features[construct] = feature_result('unverified', errors.get(sid, 'Current-image head registration missing'))
                    elif construct == 'dot':
                        features[construct] = chord_dots[sid]
                    else:
                        required = accidentals[sid]
                        attrs = marks[sid]['accidental_attributes']
                        if required not in ACCIDENTALS or any(v == 'yes' for k, v in attrs.items() if k in ('parentheses', 'bracket')):
                            features[construct] = feature_result('unsupported', 'Accidental spelling/adornment needs an independent detector', expected=required)
                        else:
                            features[construct] = measure_accidental(pixels,glyphs,head,required,
                                [heads[n['source']['id']] for n in group if n['source']['id'] in heads],
                                ledger_context_rows(pixels,staves[note['staff']],written,group))
                # Mid-measure changes have no time-resolved clef/key API in
                # the existing pitch reader. Do not certify against a final
                # bar-level attribute when its onset order is ambiguous.
                changes = [m for structure in written.measures if structure['index'] == note['index']
                           and structure['source']['part_index'] == note['part_index']
                           for m in structure['metadata'] if m['kind'] in ('clef', 'key')
                           and float(m['onset']) > 0]
                if changes:
                    for construct in features:
                        features[construct] = feature_result('unsupported', 'Mid-measure clef/key changes require time-resolved registration')
        # Detached marks never reuse observed connected ink. Only a source
        # chord's explicitly common flag may share a contour.
        claims = [(name, result) for row in rows.values() for name, result in row['features'].items()
                  if result['status'] == 'verified' and '_support' in result]
        conflicted = set()
        for i, (name, result) in enumerate(claims):
            for j, (other_name, other) in enumerate(claims[:i]):
                common_flag = (name == other_name == 'flag' and
                               result.get('_group_id') == other.get('_group_id'))
                if not common_flag and result['_support'].intersection(other['_support']):
                    conflicted.update((i, j))
        for i in conflicted:
            claims[i][1].update(status='ambiguous', reason='Different source features cannot reuse the same observed ink')
        for row in rows.values():
            for result in row['features'].values():
                result.pop('_support', None)
                result.pop('_group_id', None)
    by_construct = {name: dict(expected=0, **dict.fromkeys(STATUSES, 0))
                    for name in ('stem', 'flag', 'dot', 'accidental', 'flag_absence')}
    for row in measured:
        for name, result in row['features'].items():
            by_construct[name]['expected'] += 1
            by_construct[name][result['status']] += 1
    coverage = {key: sum(c[key] for c in by_construct.values())
                for key in ('expected', *STATUSES)}
    complete = coverage['expected'] == coverage['verified']
    return dict(status='verified' if complete else 'incomplete', complete=complete,
                expected=coverage['expected'], verified=coverage['verified'], coverage=coverage,
                by_construct=by_construct, measured=measured,
                thresholds=dict(glyph_dice=GLYPH_MINIMUM, family_margin=FAMILY_MARGIN,
                                head_dice=HEAD_MINIMUM, pitch_staff_steps=PITCH_TOLERANCE_STEPS),
                pitch_report_rechecked=pitch_report is not None,
                scope='Required note features only, bound to current-image heads and original/candidate XML events',
                not_verified=['extra or unexpected symbols beyond the bounded quarter flag attachment',
                              'beams, ties, slurs, rests and key signatures',
                              'stem ownership where physical shafts or registered heads remain inseparable',
                              'global engraving correctness'])
