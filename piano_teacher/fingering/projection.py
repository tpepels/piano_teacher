"""Project original source assignments without consulting any provider."""
from __future__ import annotations
from .types import FingeringPlan
from .placement import source_placements


def authored_projection_sources(plan: FingeringPlan | None) -> frozenset[str]:
    """Authored numbers whose ink is now owned by the projected native plan."""
    return frozenset(sid for sid,a in plan.assignments.items()
                     if a.finger is not None and a.authored_text) if plan else frozenset()


def project_model(model: dict, plan: FingeringPlan | None, *, source_musicxml: str = '') -> dict:
    if plan is None:
        return model
    placements = source_placements(source_musicxml)
    events = []
    for event in model.get('notation_events', ()):
        event = dict(event)
        event.pop('fingering', None)
        a = plan.assignments.get(event.get('source_id'))
        if a and event.get('is_attack') and a.finger is not None:
            event['fingering'] = {'source_id': a.source_id, 'finger': a.finger,
                                  'hand': a.hand, 'origin': a.origin}
            if a.source_id in placements:
                event['fingering']['placement'] = placements[a.source_id]
        events.append(event)
    return {**model, 'notation_events': events, 'fingering': plan.summary()}
