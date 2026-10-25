"""Source-authored engraving hints; independent of inference and storage."""
from fractions import Fraction
from math import isfinite
from xml.etree import ElementTree as ET


def source_placements(xml: str) -> dict[str, dict]:
    if not xml:
        return {}
    root=ET.fromstring(xml)
    for element in root.iter():
        element.tag=element.tag.rsplit('}',1)[-1]
    result={}
    for pi,part in enumerate(root.findall('part')):
        ties={}
        for mi,measure in enumerate(part.findall('measure')):
            for ordinal,note in enumerate(measure):
                if note.tag!='note' or note.find('pitch') is None or note.find('grace') is not None:
                    continue
                pitch=note.find('pitch')
                midi=(int(Fraction(pitch.findtext('octave')))+1)*12+{
                    'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[pitch.findtext('step')]+int(Fraction(pitch.findtext('alter','0')))
                key=note.findtext('staff','1'),note.findtext('voice','1'),midi
                sid=f'xml-p{pi}-m{mi}-e{ordinal}'
                roles={mark.get('type') for mark in (note.findall('tie') or note.findall('./notations/tied'))}
                attack=ties.get(key,sid) if 'stop' in roles else sid
                if 'start' in roles:
                    ties[key]=attack
                elif 'stop' in roles:
                    ties.pop(key,None)
                for mark in note.findall('./notations/technical/fingering'):
                    if mark.get('alternate')=='yes' or mark.get('substitution')=='yes':
                        continue
                    hint={}
                    if mark.get('placement') in ('above','below'):
                        hint['placement']=mark.get('placement')
                    for attribute in ('default-x','default-y','relative-x','relative-y'):
                        try:
                            value=float(mark.attrib[attribute])
                        except (KeyError,ValueError):
                            continue
                        if isfinite(value):
                            hint[attribute.replace('-','_')]=value
                    if hint and attack not in result:
                        result[attack]=hint
    return result
