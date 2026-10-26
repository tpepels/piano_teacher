"""Readable MIDI piano registers, independent of the performing hand.

MIDI assigns tracks/channels, not engraved staves. A remote register in a
simultaneous source chord can use the other existing piano staff as its own
notation voice. This module changes no Note, source ID, onset or release.
Authored MusicXML never passes through this inference.
"""
from collections import defaultdict

_STEPS={'C':0,'D':1,'E':2,'F':3,'G':4,'A':5,'B':6}
_CHROMATIC=(0,0,1,1,2,3,3,4,4,5,5,6)


def _diatonic(tone):
    note=tone['note']
    if note.spelling is not None:
        step,_,octave=note.spelling
        return octave*7+_STEPS[step]
    return (note.pitch//12-1)*7+_CHROMATIC[note.pitch%12]


def _ledgers(position,clef):
    sign=clef.get('sign','G')
    line=int(clef.get('line',2 if sign=='G' else 4))
    bottom={'G':32,'F':24,'C':28}[sign]-(line-1)*2+int(clef.get('octave_change',0))*7
    step=position-bottom
    return max(0,(-step)//2,(step-8)//2)


def _partition(tones,staff,clefs):
    ordered=sorted(tones,key=lambda tone:(_diatonic(tone),tone['source_id']))
    if len(ordered)<2 or _diatonic(ordered[-1])-_diatonic(ordered[0])<12:
        return [],tones
    other='left' if staff=='right' else 'right'
    candidates=[]
    for split in range(1,len(ordered)):
        if _diatonic(ordered[split])-_diatonic(ordered[split-1])<7:
            continue
        for remote,remaining in ((ordered[:split],ordered[split:]),
                                 (ordered[split:],ordered[:split])):
            own=[_ledgers(_diatonic(t),clefs[staff]) for t in remote]
            destination=[_ledgers(_diatonic(t),clefs[other]) for t in remote]
            # An octave by itself is no reason to rewrite a chord. Require
            # extreme ledger reach, a clearly better destination and a compact
            # remaining group in the original staff's readable register.
            if (max(own)<=4 or max(destination)>2
                    or max(_ledgers(_diatonic(t),clefs[staff]) for t in remaining)>4):
                continue
            saving=sum(own)-sum(destination)
            if saving>=3*len(remote):
                candidates.append((saving,remote,remaining))
    if not candidates:
        return [],tones
    _,remote,remaining=max(candidates,key=lambda item:item[0])
    return remote,remaining


def distribute_piano_registers(lanes_by_hand,clefs):
    """Keep resident voices first; add independently timed remote voices.

    Input lanes have already resolved exact source grouping and display release
    quantization. Each split therefore retains those exact intervals and gives
    all tied segments the same destination. Resident left/right notes never
    merge with a transferred voice, including physically coincident unisons.
    """
    result={'right':[],'left':[]}
    transferred=defaultdict(list)
    for staff in ('right','left'):
        for lane_index,lane in enumerate(lanes_by_hand[staff]):
            resident=[]
            for start,end,tones in lane:
                remote,remaining=_partition(tones,staff,clefs)
                if remaining:
                    resident.append((start,end,remaining))
                if remote:
                    other='left' if staff=='right' else 'right'
                    for tone in remote:
                        tone['notation_staff']=other
                    transferred[other,staff,lane_index].append((start,end,remote))
            if resident:
                result[staff].append(resident)
    for (destination,_,_),lane in transferred.items():
        result[destination].append(lane)
    return result
