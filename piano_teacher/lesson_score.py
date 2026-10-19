"""Compile exactly the active generated exercise events into MusicXML.

The same ExerciseVariant.phrase is used for grading, recovery and engraving.
No notes from the imported score can leak into a simplified lesson.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from collections import defaultdict
import hashlib
import math
from xml.etree import ElementTree as ET
from .music import Phrase, source_note_id
from .measure_grid import phrase_grid

DIVISIONS = 10080


@dataclass(frozen=True)
class LessonScore:
    musicxml: str
    phrase: Phrase
    note_bindings: dict = field(default_factory=dict)
    staff_clefs: dict = field(default_factory=dict)


def _ticks(beat: float) -> int:
    return round(beat * DIVISIONS)


def _signature(beats: float) -> tuple[int, int]:
    # Only a fallback when the source supplies no explicit meter context.
    fraction = Fraction(beats).limit_denominator(16)
    if abs(float(fraction) - beats) > .005:
        raise ValueError(f"Cannot express exercise bar duration: {beats}")
    if fraction.denominator == 1:
        return fraction.numerator, 4
    return fraction.numerator, 4 * fraction.denominator


def _pitch(parent: ET.Element, value: int, spelling=None) -> None:
    chromatic = ("C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B")
    alterations = (0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0)
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 127:
        raise ValueError(f"Invalid MIDI pitch {value}")
    p = ET.SubElement(parent, "pitch")
    index = value % 12
    step, alter, octave = spelling or (chromatic[index], alterations[index], value // 12 - 1)
    if (step not in 'CDEFGAB' or len(step) != 1 or not isinstance(alter, int)
            or not isinstance(octave, int)
            or (octave+1)*12+dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[step]+alter != value):
        raise ValueError(f"Pitch spelling {spelling} does not represent MIDI pitch {value}")
    ET.SubElement(p, "step").text = step
    if alter:
        ET.SubElement(p, "alter").text = str(alter)
    ET.SubElement(p, "octave").text = str(octave)


def _type(duration: int) -> tuple[str, bool] | None:
    # Spell ordinary durations. Compound values are split before emission.
    lengths = {4: "whole", 2: "half", 1: "quarter", .5: "eighth",
               .25: "16th", .125: "32nd", .0625: "64th"}
    for beats, label in lengths.items():
        if duration == round(beats * DIVISIONS):
            return label, False
        if duration == round(beats * DIVISIONS * 1.5):
            return label, True
    return None


def _duration_parts(duration: int) -> tuple[int, ...]:
    """Spell compounds without relying on Verovio to infer missing types."""
    if _tuplet_type(duration) is not None:
        return (duration,)
    ordinary = sorted({round(beats * DIVISIONS * dot)
                       for beats in (4, 2, 1, .5, .25, .125, .0625)
                       for dot in (1, 1.5)}, reverse=True)
    parts = []
    remaining = duration
    for length in ordinary:
        while remaining >= length:
            parts.append(length)
            remaining -= length
    if remaining:
        # An expressive MIDI duration between ordinary values is one event,
        # not a conventional note tied to a tiny residual. Those additional
        # noteheads impose collision spacing at almost identical clock times.
        # Keep its exact duration in one ratio; ordinary compounds still use
        # the conventional tied spelling above. Barline ties are independent.
        return (duration,)
    return tuple(parts)


def _tuplet_type(duration: int):
    for beats,label in ((4,'whole'),(2,'half'),(1,'quarter'),(.5,'eighth'),(.25,'16th'),(.125,'32nd'),(.0625,'64th')):
        for actual,normal in ((3,2),(5,4),(7,4),(9,8)):
            ticks = beats*DIVISIONS*normal/actual
            if abs(ticks-round(ticks)) < 1e-8 and duration == round(ticks):
                return label,actual,normal
    return None


def _append_note(measure: ET.Element, pitch: int | None, duration: int,
                 voice: int, *, chord=False, begin_tie=False, end_tie=False,
                 spelling=None, identifier: str | None = None) -> None:
    el = ET.SubElement(measure, "note")
    if identifier is not None:
        el.set('id', identifier)
    if chord:
        ET.SubElement(el, "chord")
    if pitch is None:
        ET.SubElement(el, "rest")
    else:
        _pitch(el, pitch, spelling)
    ET.SubElement(el, "duration").text = str(duration)
    ET.SubElement(el, "voice").text = str(voice)
    spelling = _type(duration)
    if spelling:
        ET.SubElement(el, "type").text = spelling[0]
        if spelling[1]:
            ET.SubElement(el, "dot")
    else:
        # MIDI onsets can lie between ordinary note values. MusicXML duration
        # alone is insufficient: Verovio derives its timemap from type and
        # time-modification. Preserve the integer duration with an exact ratio.
        tuplet = _tuplet_type(duration)
        if tuplet:
            label, actual, normal = tuplet
            ratio = Fraction(normal, actual)
        else:
            bases = ((4, "whole"), (2, "half"), (1, "quarter"),
                     (.5, "eighth"), (.25, "16th"), (.125, "32nd"), (.0625, "64th"))
            beats, label = min(bases, key=lambda value: abs(value[0] * DIVISIONS-duration))
            ratio = Fraction(duration, round(beats * DIVISIONS))
        ET.SubElement(el, "type").text = label
        modification = ET.SubElement(el, "time-modification")
        ET.SubElement(modification, "actual-notes").text = str(ratio.denominator)
        ET.SubElement(modification, "normal-notes").text = str(ratio.numerator)
    if pitch is not None and (begin_tie or end_tie):
        if begin_tie:
            ET.SubElement(el, "tie", type="stop")
        if end_tie:
            ET.SubElement(el, "tie", type="start")
    if (pitch is not None and (begin_tie or end_tie)) or not spelling:
        notations = ET.SubElement(el, "notations")
    if pitch is not None and (begin_tie or end_tie):
        if begin_tie:
            ET.SubElement(notations, "tied", type="stop")
        if end_tie:
            ET.SubElement(notations, "tied", type="start")
    if not spelling:
        # Verovio requires explicit tuplet notation as well as the ratio;
        # a time-modification by itself is ignored in its quarter-beat map.
        ET.SubElement(notations, "tuplet", type="start", number="1",
                      bracket="no", **{"show-number": "none"})
        ET.SubElement(notations, "tuplet", type="stop", number="1")


def _append_event(measure: ET.Element, tones: list, duration: int,
                  voice: int, *, begin_tie=False, end_tie=False, display_start=0,
                  bindings=None, counts=None) -> None:
    parts = _duration_parts(duration)
    position = display_start
    for index, length in enumerate(parts):
        # Emit every chord tone together in each tied segment. Splitting each
        # pitch independently would attach chord tags to the wrong time slot.
        for chord_index, tone in enumerate(tones):
            pitch = tone['pitch'] if tone is not None else None
            identifier = None
            if tone is not None:
                source = tone['source_id']
                segment = counts.get(source, 0)
                identifier = 'pt' + hashlib.sha256(source.encode()).hexdigest()[:32] + 's' + str(segment)
                if identifier in bindings:
                    raise ValueError('Duplicate emitted source-note identity')
                bindings[identifier] = {key: tone[key] for key in ('source_id','source_beat','pitch','hand')}
                bindings[identifier].update(is_attack=segment == 0, segment_index=segment,
                                             display_beat=position/DIVISIONS)
                counts[source] = segment+1
            _append_note(measure, pitch, length, voice, chord=chord_index > 0,
                         begin_tie=begin_tie or index > 0,
                         end_tie=end_tie or index < len(parts)-1,
                         spelling=tone.get('spelling') if tone else None, identifier=identifier)
        position += length


def _render_measure(measure: ET.Element, lanes: list[list[tuple]], length: int,
                    bar_start: int, bindings: dict, counts: dict) -> None:
    for lane_idx, events in enumerate(lanes or [[]]):
        if lane_idx:
            backup = ET.SubElement(measure, "backup")
            ET.SubElement(backup, "duration").text = str(length)
        position = 0
        for start, end, tones in events:
            if start >= bar_start+length or end <= bar_start:
                continue
            first, last = start < bar_start, end > bar_start+length
            start, end = max(start, bar_start)-bar_start, min(end, bar_start+length)-bar_start
            if start > position:
                _append_event(measure, [None], start-position, lane_idx+1)
            _append_event(measure, tones, end-start, lane_idx+1,
                          begin_tie=first, end_tie=last, display_start=bar_start+start,
                          bindings=bindings, counts=counts)
            position = end
        if position < length:
            _append_event(measure, [None], length-position, lane_idx+1)


def _key_alters(fifths: int) -> dict:
    result = defaultdict(int)
    for index in range(abs(fifths)):
        result[('FCGDAEB' if fifths > 0 else 'BEADGCF')[index % 7]] += 1 if fifths > 0 else -1
    return result


def _write_tuplet_groups(measure):
    """Give consecutive conventional tuplets one visible, honest group number."""
    voices = defaultdict(list)
    position = previous = 0
    for element in measure:
        duration = int(element.findtext('duration','0'))
        if element.tag == 'backup':
            position -= duration
        elif element.tag == 'note':
            chord = element.find('chord') is not None
            onset = previous if chord else position
            if not chord:
                previous = position; position += duration
            spec = _tuplet_type(duration) if element.find('time-modification') is not None else None
            if chord and spec:
                for notation in element.findall('./notations/tuplet'):
                    element.find('notations').remove(notation)
            if not chord:
                voices[element.findtext('voice')].append((element,onset,duration,spec))
    for events in voices.values():
        index = 0
        while index < len(events):
            _,_,_,spec = events[index]
            if spec is None:
                index += 1
                continue
            group = [events[index]]
            while (len(group) < spec[1] and index+len(group) < len(events)
                   and events[index+len(group)][3] == spec
                   and events[index+len(group)][1] == group[-1][1]+group[-1][2]):
                group.append(events[index+len(group)])
            if len(group) != spec[1]:
                # Expressive MIDI routinely uses isolated 5:4 and 7:4
                # durations (including rests) without a complete group.
                # The input MusicXML already contains an invisible local
                # start/stop pair to preserve Verovio's exact MIDI timemap.
                # Do not turn that singleton into a visible fake quintuplet
                # bracket/number. A visible n-tuplet requires n contiguous
                # notes/rests of the same ratio and notation value.
                index += len(group)
                continue
            for element,*_ in group:
                for notation in element.findall('./notations/tuplet'):
                    element.find('notations').remove(notation)
            for element,kind in ((group[0][0],'start'),(group[-1][0],'stop')):
                notations = element.find('notations')
                if notations is None:
                    notations = ET.SubElement(element,'notations')
                ET.SubElement(notations,'tuplet',type=kind,number='1',bracket='yes',**{'show-number':'actual'})
            index += len(group)


def _write_accidentals(measure: ET.Element, fifths: int = 0) -> None:
    """Spell visible alterations against source key context across all voices.

    MusicXML's pitch alter affects playback, but Verovio needs an accidental
    element to print its sharp or its later natural cancellation.
    """
    position = previous_onset = 0
    events = []
    for element in measure:
        duration = int(element.findtext("duration", "0"))
        if element.tag == "backup":
            position -= duration
        elif element.tag == "forward":
            position += duration
        elif element.tag == "note":
            onset = previous_onset if element.find("chord") is not None else position
            if element.find("pitch") is not None:
                events.append((onset, len(events), element))
            if element.find("chord") is None:
                previous_onset = position
                position += duration
    context = {}
    signature = _key_alters(fifths)
    for _, _, note in sorted(events):
        pitch = note.find("pitch")
        key = (pitch.findtext("step"), pitch.findtext("octave"))
        alteration = int(pitch.findtext("alter", "0"))
        # A continuation carries the visible pitch from its tied attack.
        # It does not establish a new accidental after a barline.
        if any(tie.get("type") == "stop" for tie in note.findall("tie")):
            continue
        if alteration != context.get(key, signature[key[0]]):
            accidental = ET.Element("accidental")
            accidental.text = {-2:'flat-flat',-1:'flat',0:'natural',1:'sharp',2:'double-sharp'}.get(alteration)
            if accidental.text is None:
                raise ValueError(f'Unsupported accidental alteration {alteration}')
            after = max((index for index, child in enumerate(note)
                         if child.tag in ("type", "dot")), default=len(note)-1)
            note.insert(after + 1, accidental)
        context[key] = alteration


def _readable_clef(notes, explicit, hand):
    pitches = [note.pitch for note in notes]
    def cost(sign, octave=0):
        low, high = (64,77) if sign == 'G' else (43,57)
        return sum(max(0, low-(pitch-12*octave), (pitch-12*octave)-high) for pitch in pitches)/max(1,len(pitches))
    best = min(('G','F'), key=lambda sign: (cost(sign), sign != ('G' if hand == 'right' else 'F')))
    if not pitches:
        best = 'G' if hand == 'right' else 'F'
    if explicit is not None:
        if explicit.sign not in ('G','F','C'):
            raise ValueError(f'Unsupported source clef {explicit.sign}')
        if explicit.sign in ('G','F') and explicit.line == (2 if explicit.sign == 'G' else 4):
            if explicit.octave_change not in (-1,0,1):
                raise ValueError('Unsupported clef octave change')
            if not pitches or cost(explicit.sign, explicit.octave_change) <= cost(best)+12:
                return {'sign':explicit.sign,'line':explicit.line,'octave_change':explicit.octave_change}
    return {'sign':best,'line':2 if best == 'G' else 4,'octave_change':0}


def infer_piece_clefs(notes) -> dict:
    """Choose stable piano clefs using the *whole piece*, not a lesson slice.

    Imported MIDI normally contains notes, not clefs. The left hand of Ala
    plays C4-G4 in the opening exercise but spends much of the piece below
    middle C; a per-phrase guess incorrectly switches it to treble. A single
    piece-wide choice keeps one predictable reading system throughout the
    practice route. Explicit source MusicXML clef changes still take priority.
    """
    return {
        hand: _readable_clef([n for n in notes if n.hand == hand], None, hand)
        for hand in ("right", "left")
    }


def _spelling(note, fifths):
    if note.spelling is not None:
        return note.spelling
    alters = _key_alters(fifths)
    for step, natural in dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11).items():
        if (natural+alters[step]) % 12 == note.pitch % 12:
            octave = (note.pitch-natural-alters[step])//12-1
            return step, alters[step], octave
    if fifths < 0:
        names = [('C',0),('D',-1),('D',0),('E',-1),('E',0),('F',0),('G',-1),('G',0),('A',-1),('A',0),('B',-1),('B',0)]
        step, alter = names[note.pitch % 12]
        return step, alter, note.pitch//12-1
    return None


def _phrase_lanes(phrase, hand, grid=()):
    groups = defaultdict(list)
    attacks = {}
    identities = set()
    for index, note in enumerate(phrase.notes):
        if note.hand != hand:
            continue
        source = source_note_id(note,index)
        if source in identities:
            raise ValueError('Duplicate required source-note identity')
        identities.add(source)
        if not all(math.isfinite(value) for value in (note.start,note.end)) or not phrase.start <= note.start < min(note.end,phrase.end):
            raise ValueError('Source note attack/duration is outside the active phrase')
        start, end = _ticks(note.start-phrase.start), _ticks(min(note.end,phrase.end)-phrase.start)
        if end <= start:
            raise ValueError('Source note duration cannot be represented at notation resolution')
        key = (note.track,note.voice,start)
        if key in attacks and abs(attacks[key]-(note.start-phrase.start)) > 1e-12:
            raise ValueError('Distinct source attacks collide at notation quantization resolution')
        attacks[key] = note.start-phrase.start
        groups[note.track,note.voice,start,end].append({'source_id':source,'source_beat':note.start-phrase.start,
                                                      'pitch':note.pitch,'hand':hand,'note':note})
    events = []
    for (track, voice, start, end), tones in groups.items():
        remaining = sorted(tones,key=lambda tone:(tone['pitch'],tone['source_id']))
        while remaining:
            layer, pitches = [], set()
            for tone in remaining:
                if tone['pitch'] not in pitches:
                    layer.append(tone); pitches.add(tone['pitch'])
            remaining = [tone for tone in remaining if tone not in layer]
            events.append((start,end,(track,voice),layer))
    events.sort(key=lambda event:(event[0],event[1],event[2],tuple(tone['source_id'] for tone in event[3])))
    lanes, endings, owners = [], [], []
    for start,end,owner,tones in events:
        lane = next((i for i,last in enumerate(endings) if last <= start and owners[i] == owner),None)
        if lane is None:
            lane = len(lanes); lanes.append([]); endings.append(0); owners.append(owner)
        lanes[lane].append((start,end,tones)); endings[lane] = end
    # Release quantization changes display duration only. Never extend a note
    # over the following source attack in its stable lane.
    for lane in lanes:
        for i,(start,end,tones) in enumerate(lane):
            rounded = round(end/(DIVISIONS//4))*(DIVISIONS//4)
            if _tuplet_type(end-start) is None and rounded > start and abs(rounded-end) <= _ticks(.12):
                end = min(rounded,_ticks(phrase.end-phrase.start),lane[i+1][0] if i+1 < len(lane) else _ticks(phrase.end-phrase.start))
            if i+1 < len(lane):
                following = lane[i+1][0]
                # Tiny key-release gaps in performance MIDI are articulation,
                # not useful additional rest instructions. Extend display only
                # to the next attack in this stable lane, within this measure.
                # Source notes, attack bindings and assessed releases stay exact.
                if (0 < following-end <= DIVISIONS/64
                        and not any(end <= _ticks(boundary) < following for boundary in grid)):
                    end = following
            lane[i] = (start,end,tones)
    return lanes


def build_lesson_score(phrase: Phrase, *, boundaries: tuple[float, ...] = (),
                       time_signatures: tuple[tuple[float, int, int], ...] = (),
                       key_signatures=(), clef_changes=(),
                       default_clefs: dict | None = None,
                       barlines: tuple = ()) -> LessonScore:
    """Create notation from the source measure grid, not averaged bars."""
    identities = [source_note_id(note,index) for index,note in enumerate(phrase.notes)]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate required source-note identity')
    grid = phrase_grid(phrase, boundaries)
    bars = len(grid) - 1
    changes = sorted(time_signatures)
    barline_at = {}
    for mark in barlines:
        key = (round(mark.beat, 8), mark.location)
        current = (mark.style, mark.repeat)
        if key in barline_at and barline_at[key] != current:
            raise ValueError("Conflicting source barline declarations")
        barline_at[key] = current

    def append_barline(measure, beat, location):
        style_and_repeat = barline_at.get((round(beat, 8), location))
        if style_and_repeat is None:
            return
        style, direction = style_and_repeat
        tag = ET.Element("barline", location=location)
        ET.SubElement(tag, "bar-style").text = style
        if direction:
            ET.SubElement(tag, "repeat", direction=direction)
        if location == "left":
            # MusicXML left barlines precede the note stream. Attributes
            # (meter/clef/key) stay at the beginning of the measure.
            index = next((i for i, node in enumerate(measure)
                          if node.tag not in {"attributes"}), len(measure))
            measure.insert(index, tag)
        else:
            measure.append(tag)

    def meter_at(beat: float, length: float) -> tuple[int, int]:
        active = [(n, d) for offset, n, d in changes if offset <= beat + 1e-7]
        return active[-1] if active else _signature(length)

    root = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = " "
    partlist = ET.SubElement(root, "part-list")
    # The two generated hand parts belong to one piano grand staff. Without
    # this group Verovio engraves separate barlines, leaving a gap between
    # the hands even though the opening system line connects them.
    piano_group = ET.SubElement(partlist, "part-group", type="start", number="1")
    ET.SubElement(piano_group, "group-symbol").text = "brace"
    ET.SubElement(piano_group, "group-barline").text = "yes"
    # The practice HUD already identifies the active hand. Verovio's
    # full-size Right/Left hand labels used to consume a large strip of score
    # space and make the clefs look like labels on a magnified PDF.
    for ident in ("RH", "LH"):
        scorepart = ET.SubElement(partlist, "score-part", id=ident)
        ET.SubElement(scorepart, "part-name").text = " "
        ET.SubElement(scorepart, "part-abbreviation").text = " "
    ET.SubElement(partlist, "part-group", type="stop", number="1")
    bindings, counts, staff_clefs = {}, {}, {}
    for hand, ident in (("right", "RH"), ("left", "LH")):
        part = ET.SubElement(root, "part", id=ident)
        last_meter = None
        last_key = last_clef = None
        lanes = _phrase_lanes(phrase, hand, grid)
        keys = sorted((key for key in key_signatures if key.hand in (hand,'both')),key=lambda item:item.beat)
        clefs = sorted((clef for clef in clef_changes if clef.hand in (hand,'both')),key=lambda item:item.beat)
        for lane in lanes:
            for _,_,tones in lane:
                for tone in tones:
                    attack_key = next((key for key in reversed(keys) if key.beat <= tone['note'].start+1e-7),None)
                    tone['spelling'] = _spelling(tone['note'],attack_key.fifths if attack_key else 0)
        for change in (*keys,*clefs):
            if phrase.start < change.beat < phrase.end and not any(abs(change.beat-phrase.start-beat)<1e-7 for beat in grid):
                raise ValueError('Mid-measure source key/clef changes are not supported in generated lessons')
        for b in range(bars):
            bar_start, bar_end = _ticks(grid[b]), _ticks(grid[b+1])
            if bar_end <= bar_start:
                raise ValueError("Source measure has no duration")
            beats, beat_type = meter_at(phrase.start + grid[b], grid[b+1] - grid[b])
            if beats <= 0 or beat_type <= 0:
                raise ValueError("Invalid imported time signature")
            measure = ET.SubElement(part, "measure", number=str(phrase.first_bar+b))
            if abs((beats * 4.0 / beat_type) - (grid[b+1] - grid[b])) > 1e-5:
                measure.set("implicit", "yes")
            source_beat = phrase.start+grid[b]
            active_key = next((key for key in reversed(keys) if key.beat <= source_beat+1e-7),None)
            active_clef = next((clef for clef in reversed(clefs) if clef.beat <= source_beat+1e-7),None)
            key_value = (active_key.fifths,active_key.mode) if active_key else None
            # A short practice phrase can sit in a different register from
            # the rest of the piano part. Reuse the piece-wide MIDI default
            # instead of jumping clefs between lessons. Source clefs override.
            if active_clef is None and default_clefs is not None and hand in default_clefs:
                chosen_clef = default_clefs[hand].copy()
            else:
                chosen_clef = _readable_clef(
                    [note for note in phrase.notes if note.hand == hand],
                    active_clef, hand)
            if b == 0:
                staff_clefs[hand] = chosen_clef
            if b == 0 or (beats, beat_type) != last_meter or key_value != last_key or chosen_clef != last_clef:
                attrs = ET.SubElement(measure, "attributes")
                if b == 0:
                    ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
                if active_key is not None and (b == 0 or key_value != last_key):
                    key = ET.SubElement(attrs,'key')
                    ET.SubElement(key,'fifths').text = str(active_key.fifths)
                    if active_key.mode:
                        ET.SubElement(key,'mode').text = active_key.mode
                if b == 0 or (beats,beat_type) != last_meter:
                    time = ET.SubElement(attrs, "time")
                    ET.SubElement(time, "beats").text = str(beats)
                    ET.SubElement(time, "beat-type").text = str(beat_type)
                if b == 0 or chosen_clef != last_clef:
                    clef = ET.SubElement(attrs, "clef")
                    ET.SubElement(clef, "sign").text = chosen_clef['sign']
                    ET.SubElement(clef, "line").text = str(chosen_clef['line'])
                    if chosen_clef['octave_change']:
                        ET.SubElement(clef,'clef-octave-change').text = str(chosen_clef['octave_change'])
            last_meter = (beats, beat_type)
            last_key, last_clef = key_value, chosen_clef
            append_barline(measure,source_beat,"left")
            _render_measure(measure,lanes,bar_end-bar_start,bar_start,bindings,counts)
            _write_accidentals(measure,active_key.fifths if active_key else 0)
            _write_tuplet_groups(measure)
            append_barline(measure,phrase.start+grid[b+1],"right")
    return LessonScore(ET.tostring(root, encoding="unicode"), phrase, bindings, staff_clefs)
