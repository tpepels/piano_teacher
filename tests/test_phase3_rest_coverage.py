"""Rectangular rest identification needs measured staff-relative edges."""
from copy import deepcopy

import pytest

from test_phase3_visual_coverage import score, bar, rest, rest_row, ledger, rows


def oriented_rest(kind):
    whole=kind=='whole'
    return dict(rest_row(kind=kind), shape_match=.9, next_family_score=.4,
                observed_rest=kind, type_ambiguity=False,
                visible_original_ink_removed=40,
                orientation_evidence=dict(observed_rest=kind, staff_lines=[100.,120.,140.,160.,180.],
                    staff_gap=20., height_spaces=.5,
                    hanging_edge_error_spaces=.02 if whole else .48,
                    sitting_edge_error_spaces=.48 if whole else .02))


@pytest.mark.parametrize('kind',['half','whole'])
def test_valid_independent_staff_edge_evidence_can_identify_rectangular_rest(kind):
    result=ledger(score(bar(rest(kind=kind))),rests=[oriented_rest(kind)])
    assert rows(result,'rest')[0]['status']=='verified'
    for construct in ('rest_rhythm','rest_placement'):
        assert rows(result,construct)[0]['status']=='unsupported'


@pytest.mark.parametrize('kind',['half','whole'])
def test_old_contour_evidence_preserves_half_whole_ambiguity(kind):
    result=ledger(score(bar(rest(kind=kind))),rests=[rest_row(kind=kind)])
    assert rows(result,'rest')[0]['status']=='ambiguous'


@pytest.mark.parametrize('mutate',[
    lambda r:r.pop('orientation_evidence'),
    lambda r:r.update(type_ambiguity=True),
    lambda r:r.update(observed_rest='whole'),
    lambda r:r['orientation_evidence'].update(observed_rest='whole'),
    lambda r:r['orientation_evidence'].update(staff_lines=[100.,100.,140.,160.,180.]),
    lambda r:r['orientation_evidence'].update(staff_gap=float('nan')),
    lambda r:r['orientation_evidence'].update(height_spaces=.15),
    lambda r:r['orientation_evidence'].update(sitting_edge_error_spaces=.4),
    lambda r:r['orientation_evidence'].update(hanging_edge_error_spaces=.02),
    lambda r:r.update(visible_original_ink_removed=0),
    lambda r:r.update(shape_match=.4),
    lambda r:r.update(next_family_score=.89),
])
def test_missing_or_corrupt_orientation_evidence_cannot_lift_ambiguity(mutate):
    measurement=oriented_rest('half')
    mutate(measurement)
    result=ledger(score(bar(rest(kind='half'))),rests=[measurement])
    assert rows(result,'rest')[0]['status']=='ambiguous'


def test_event_identity_still_required_despite_valid_rest_orientation():
    measurement=oriented_rest('half')
    measurement['source_id']='different'
    result=ledger(score(bar(rest(kind='half'))),rests=[measurement])
    assert rows(result,'rest')[0]['status']=='unverified'


def rhythmic_rest(kind='whole', dots=0):
    from fractions import Fraction
    measurement=oriented_rest(kind)
    measurement['dot_evidence']=dict(status='verified',expected_count=dots,observed_count=dots,
        dots=[dict(box=[10+i*10,20,14+i*10,24],shape_match=.95) for i in range(dots)])
    duration={'whole':4,'half':2,'quarter':1}[kind]*(2-Fraction(1,2**dots))
    xml=score(bar(rest(kind=kind,extra='<dot/>'*dots).replace('<duration>1</duration>',f'<duration>{int(duration*4)}</duration>'))
              .replace('<divisions>1</divisions>','<divisions>4</divisions>'))
    return xml,measurement


@pytest.mark.parametrize('kind,dots',[('whole',0),('half',1),('quarter',2)])
def test_rest_rhythm_requires_independent_type_dots_and_exact_duration(kind,dots):
    xml,measurement=rhythmic_rest(kind,dots)
    result=ledger(xml,rests=[measurement])
    assert rows(result,'rest_rhythm')[0]['status']=='verified'
    assert all(r['status']=='verified' for r in rows(result,'dot'))
    assert rows(result,'rest_placement')[0]['status']=='unsupported'


@pytest.mark.parametrize('mutate',[
    lambda r:r['dot_evidence'].update(status='unverified'),
    lambda r:r['dot_evidence'].update(expected_count=1),
    lambda r:r['dot_evidence'].update(observed_count=True),
    lambda r:r['dot_evidence'].update(observed_count=1),
    lambda r:r['dot_evidence'].update(dots=[dict(box=[10,20,14,24],shape_match=.95)]),
    lambda r:r.update(observed_rest='half'),
    lambda r:r.update(source_id='forged'),
])
def test_rest_rhythm_never_uses_status_alone_or_wrong_event_fields(mutate):
    xml,measurement=rhythmic_rest()
    mutate(measurement)
    assert rows(ledger(xml,rests=[measurement]),'rest_rhythm')[0]['status']!='verified'


def test_rest_duration_arithmetic_and_generated_dot_changes_stay_blocking():
    xml,measurement=rhythmic_rest('half',1)
    bad=xml.replace('<duration>12</duration>','<duration>10</duration>')
    assert rows(ledger(bad,rests=[measurement]),'rest_rhythm')[0]['status']!='verified'
    generated=xml.replace('<dot/>','')
    assert rows(ledger(xml,generated,rests=[measurement]),'rest_rhythm')[0]['status']!='verified'


def test_same_dot_contour_cannot_verify_two_source_rest_dots():
    xml,measurement=rhythmic_rest('quarter',2)
    measurement['dot_evidence']['dots'][1]=measurement['dot_evidence']['dots'][0]
    result=ledger(xml,rests=[measurement])
    assert rows(result,'rest_rhythm')[0]['status']!='verified'
    assert all(r['status']!='verified' for r in rows(result,'dot'))


@pytest.fixture(scope='module')
def actual_placement_report():
    from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels
    from test_phase3_rest_orientation import REAL
    xml=(REAL/'score.musicxml').read_text()
    return xml,verify_all_rest_pixels(xml,REAL)


def test_actual_placement_payload_maps_to_bound_rest_obligation(actual_placement_report):
    xml,report=actual_placement_report
    result=ledger(None,xml,rests=report['measured'])
    assert rows(result,'rest_placement')[0]['status']=='verified'
    assert rows(result,'rest_rhythm')[0]['status']=='verified'


@pytest.mark.parametrize('mutate',[
    lambda p:p.clear(),
    lambda p:p.update(status='verified',min_clearance_spaces=0),
    lambda p:p.update(min_clearance_pixels=0),
    lambda p:p.update(registration_match=.2),
    lambda p:p.update(grid_phase_error_spaces=.5),
    lambda p:p.update(grid_phase_tolerance_spaces=1),
    lambda p:p.update(required_clearance_spaces=0),
    lambda p:p.update(baseline_y=p['baseline_y']+10),
    lambda p:p.update(staff_lines=[0,0,0,0,0]),
    lambda p:p.update(corridor_y=[0,10]),
    lambda p:p.update(baseline_range_y=[0,10000]),
    lambda p:p.update(silhouette_bbox=[0,0,1,1]),
    lambda p:p.update(bbox=[p["bbox"][0]+1,*p["bbox"][1:]]),
])
def test_forged_status_cannot_replace_placement_geometry(actual_placement_report,mutate):
    xml,original=actual_placement_report
    report=deepcopy(original)
    placement=report['measured'][0]['placement_evidence']
    mutate(placement)
    placement['status']='verified'
    result=ledger(None,xml,rests=report['measured'])
    assert rows(result,'rest_placement')[0]['status']!='verified'


def test_placement_requires_same_source_event_and_preserves_detector_failure(actual_placement_report):
    xml,original=actual_placement_report
    report=deepcopy(original)
    report['measured'][0]['source_id']='forged'
    assert rows(ledger(None,xml,rests=report['measured']),'rest_placement')[0]['status']!='verified'
    report=deepcopy(original)
    report['measured'][0]['placement_evidence'].update(status='mismatch',reason='Measured overlap')
    assert rows(ledger(None,xml,rests=report['measured']),'rest_placement')[0]['status']=='mismatch'


def test_nonrectangular_rest_rhythm_needs_an_independent_family_margin():
    xml,measurement=rhythmic_rest('quarter')
    measurement['next_family_score']=.89
    assert rows(ledger(xml,rests=[measurement]),'rest_rhythm')[0]['status']!='verified'
