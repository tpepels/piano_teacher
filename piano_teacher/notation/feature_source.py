"""Independent written identities and accidental obligations for note features."""
from xml.etree import ElementTree as ET

from .feature_contract import ALTERATIONS


def event_identity(note):
    return note.get('id') or note['source']['id']


def read_feature_marks(xml):
    """Supplement the oracle with explicit stem/adornment declarations only."""
    root = ET.fromstring(xml)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    result = {}
    for p, part in enumerate(root.findall('part')):
        for m, measure in enumerate(part.findall('measure')):
            for ordinal, element in enumerate(measure):
                if element.tag == 'note':
                    accidental = element.find('accidental')
                    result[f'xml-p{p}-m{m}-e{ordinal}'] = dict(
                        stem=element.findtext('stem'),
                        accidental_attributes={} if accidental is None else accidental.attrib)
    return result


def required_accidentals(written):
    """Written accidental state, per measure/part/staff/pitch octave.

    Explicit cautionary naturals are requirements too. Implicit accidentals
    follow key and prior written spelling, across voices; tied continuations
    need no repeated accidental. Mid-measure changes are blocked by caller.
    """
    states = {}
    result = {}
    for note in written.symbols:
        if note['kind'] != 'note':
            continue
        staff, bar = note['staff'], note['index']
        keys = [(at, fifths) for at, hand, fifths in written.keys if hand == staff and at <= bar]
        fifths = max(keys, key=lambda pair: pair[0])[1] if keys else 0
        key_alters = {step: (1 if fifths > 0 else -1)
                      for step in ('FCGDAEB' if fifths > 0 else 'BEADGCF')[:abs(fifths)]}
        step, alter, octave = note['spelling']
        state = states.setdefault((note['part_index'], bar, staff), {})
        previous = state.get((step, octave), key_alters.get(step, 0))
        required = note['accidental']
        if required is None and not note['tie_stop'] and alter != previous:
            required = ALTERATIONS.get(alter, f'alteration-{alter}')
        result[note['source']['id']] = required
        state[step, octave] = alter
    return result
