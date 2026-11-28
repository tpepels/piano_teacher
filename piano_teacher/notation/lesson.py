"""Compile exactly the active generated exercise events into MusicXML.

The same ExerciseVariant.phrase is used for grading, recovery and engraving.
No notes from the imported score can leak into a simplified lesson.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from collections import defaultdict
from bisect import bisect_left
import hashlib
import math
from xml.etree import ElementTree as ET
from ..music import Phrase, source_note_id
from ..measure_grid import phrase_grid
from ..source_timing import source_meter
from .midi_beaming import beam_midi_measure
from .piano_registers import distribute_piano_registers
from .written_marks import project_written_marks

DIVISIONS = 10080


@dataclass(frozen=True)
class LessonScore:
    musicxml: str
    phrase: Phrase
    note_bindings: dict = field(default_factory=dict)
    staff_clefs: dict = field(default_factory=dict)
    unrendered_expressions: tuple[str, ...] = ()


def _ticks(beat: float) -> int:
    return round(beat * DIVISIONS)


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


_NOTE_VALUES = ((Fraction(4), "whole"), (Fraction(2), "half"),
                (Fraction(1), "quarter"), (Fraction(1, 2), "eighth"),
                (Fraction(1, 4), "16th"), (Fraction(1, 8), "32nd"),
                (Fraction(1, 16), "64th"), (Fraction(1, 32), "128th"))


def _dotted_ticks(beats: Fraction, dots: int) -> int | None:
    # 10080 divisions cannot express every small multiply-dotted value.
    # Generate only mathematically exact ticks; never round an onset.
    duration = beats * DIVISIONS * sum(
        (Fraction(1, 2 ** position) for position in range(dots + 1)),
        Fraction(0))
    return int(duration) if duration.denominator == 1 else None


def _type(duration: int) -> tuple[str, int] | None:
    # One to four dots are supported when the source rhythm is exactly
    # expressible on our fixed tick grid; otherwise preserve its duration
    # using the existing precise time-modification path.
    for beats, label in _NOTE_VALUES:
        for dots in range(5):
            if _dotted_ticks(beats, dots) == duration:
                return label, dots
    return None


def _duration_parts(duration: int) -> tuple[int, ...]:
    """Spell compounds without relying on Verovio to infer missing types."""
    if _tuplet_type(duration) is not None:
        return (duration,)
    ordinary = sorted({
        length for beats, _ in _NOTE_VALUES for dots in range(5)
        if (length := _dotted_ticks(beats, dots)) is not None
    }, reverse=True)
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
    for beats,label in ((4,'whole'),(2,'half'),(1,'quarter'),(.5,'eighth'),(.25,'16th'),(.125,'32nd'),(.0625,'64th'),(.03125,'128th')):
        for actual,normal in ((3,2),(5,4),(7,4),(9,8)):
            ticks = beats*DIVISIONS*normal/actual
            if abs(ticks-round(ticks)) < 1e-8 and duration == round(ticks):
                return label,actual,normal
    return None


def _append_note(measure: ET.Element, pitch: int | None, duration: int,
                 voice: int, *, chord=False, begin_tie=False, end_tie=False,
                 spelling=None, identifier: str | None = None,
                 hidden_rest: bool = False, stem: str | None = None) -> None:
    el = ET.SubElement(measure, "note")
    if pitch is None and hidden_rest:
        # Keep each synthetic voice's exact duration/cursor but omit its
        # superfluous silence glyph. Otherwise independently reconstructed
        # pseudo-voices draw 32nd/64th rests above and below unrelated notes.
        el.set("print-object", "no")
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
        for _ in range(spelling[1]):
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
                     (.5, "eighth"), (.25, "16th"), (.125, "32nd"), (.0625, "64th"), (.03125, "128th"))
            beats, label = min(bases, key=lambda value: abs(value[0] * DIVISIONS-duration))
            ratio = Fraction(duration, round(beats * DIVISIONS))
        ET.SubElement(el, "type").text = label
        modification = ET.SubElement(el, "time-modification")
        ET.SubElement(modification, "actual-notes").text = str(ratio.denominator)
        ET.SubElement(modification, "normal-notes").text = str(ratio.numerator)
    if pitch is not None and stem in ('up', 'down'):
        ET.SubElement(el, 'stem').text = stem
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
                  bindings=None, counts=None, hidden_rest=False,
                  stem: str | None = None) -> None:
    parts = _duration_parts(duration)
    position = display_start
    for index, length in enumerate(parts):
        # Emit every chord tone together in each tied segment. Splitting each
        # pitch independently would attach chord tags to the wrong time slot.
        for chord_index, tone in enumerate(tones):
            pitch = tone['pitch'] if tone is not None else None
            identifier = None
            if pitch is not None:
                source = tone['source_id']
                segment = counts.get(source, 0)
                identifier = 'pt' + hashlib.sha256(source.encode()).hexdigest()[:32] + 's' + str(segment)
                if identifier in bindings:
                    raise ValueError('Duplicate emitted source-note identity')
                bindings[identifier] = {key: tone[key] for key in ('source_id','source_beat','pitch','hand','notation_timing')}
                if 'notation_staff' in tone:
                    bindings[identifier]['notation_staff'] = tone['notation_staff']
                bindings[identifier].update(is_attack=segment == 0, segment_index=segment,
                                             display_beat=position/DIVISIONS)
                counts[source] = segment+1
            _append_note(measure, pitch, length, voice, chord=chord_index > 0,
                         begin_tie=begin_tie or index > 0,
                         end_tie=end_tie or index < len(parts)-1,
                         spelling=tone.get('spelling') if tone else None,
                         identifier=identifier,
                         hidden_rest=hidden_rest or bool(tone and tone.get('hidden_rest')),
                         stem=stem)
        position += length


def _midi_voice_stems(lanes: list[list[tuple]]) -> dict[int, str]:
    """Explicit opposite stems for independently held MIDI voices.

    Standard polyphonic engraving places upper voices up and lower voices
    down. MIDI may encode a sustained lower note and rapid upper notes
    on the *same* track/voice; they still need independent shafts/flags.
    The incoming note durations are never changed.
    """
    events = [(start, end, index, tone['pitch'])
              for index, lane in enumerate(lanes)
              for start, end, tones in lane
              for tone in tones if tone is not None and tone.get('pitch') is not None]
    if len(events) < 2:
        return {}
    events.sort()
    active: list[tuple[int, int]] = []
    overlapping = set()
    for start, end, lane, _ in events:
        active = [(until, owner) for until, owner in active if until > start]
        for until, owner in active:
            if owner != lane:
                overlapping.update((owner, lane))
        active.append((end, lane))
    if len(overlapping) < 2:
        return {}
    pitches = {
        lane: sorted(tone['pitch'] for _, _, tones in lanes[lane]
                     for tone in tones if tone is not None and tone.get('pitch') is not None)
        for lane in overlapping
    }
    # Use each lane's middle register (not accidental first-event order).
    # An upper short-note beam should stay up; a sustained low note down.
    upper_first = sorted(overlapping,
                         key=lambda i: (-pitches[i][len(pitches[i])//2], i))
    split = (len(upper_first)+1)//2
    return {lane: 'up' if rank < split else 'down'
            for rank, lane in enumerate(upper_first)}


def _render_measure(measure: ET.Element, lanes: list[list[tuple]], length: int,
                    bar_start: int, bindings: dict, counts: dict,
                    hide_performance_micro_rests: bool = False,
                    midi_stems: dict[int, str] | None = None) -> None:
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
                # Tiny key-release gaps from live MIDI are not intentional
                # written rests. Preserve the exact MusicXML voice cursor
                # without printing a distracting 32nd/64th rest. Explicit
                # MusicXML and opening silence stay fully visible.
                micro_gap = (hide_performance_micro_rests and position > 0
                             and start-position <= DIVISIONS//8)
                _append_event(measure, [None], start-position, lane_idx+1,
                              hidden_rest=lane_idx > 0 or micro_gap)
            _append_event(measure, tones, end-start, lane_idx+1,
                          begin_tie=first, end_tie=last, display_start=bar_start+start,
                          bindings=bindings, counts=counts,
                          stem=(midi_stems or {}).get(lane_idx))
            position = end
        if position < length:
            _append_event(measure, [None], length-position, lane_idx+1,
                          hidden_rest=lane_idx > 0)


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
        alteration = int(Fraction(pitch.findtext("alter", "0")))
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
        # Notation-authored clefs are authoritative even when the sounding
        # register is unusual. Never silently replace an explicit F/G/C
        # with a MIDI heuristic: it shifts every engraved note vertically.
        if explicit.sign not in ('G','F','C'):
            raise ValueError(f'Unsupported source clef {explicit.sign}')
        if not 1 <= explicit.line <= 5:
            raise ValueError(f'Unsupported source clef line {explicit.line}')
        if explicit.octave_change not in (-1,0,1):
            raise ValueError('Unsupported clef octave change')
        return {'sign':explicit.sign,'line':explicit.line,
                'octave_change':explicit.octave_change}
    return {'sign':best,'line':2 if best == 'G' else 4,'octave_change':0}


def infer_piece_clefs(notes) -> dict:
    """Choose whole-piece register defaults, before per-measure MIDI planning.

    The left hand of Ala starts higher than its overall register; its stable
    whole-piece bass default must not jump between lesson slices. For a right
    hand spanning low and high registers, infer_midi_clef_plan supplies
    conservative per-measure changes. Authored MusicXML clefs take priority.
    """
    # MIDI stores sounding pitches, not printed clefs. Choose each hand's
    # clef from its complete register, then reuse it for every lesson slice.
    # Forcing right-hand G causes bass-register passages to acquire multiple
    # ledger lines below the staff, even when F is the readable choice.
    # Actual MusicXML clef changes still override these inferred defaults.
    return {
        hand: _readable_clef(
            [note for note in notes if note.hand == hand], None, hand)
        for hand in ("right", "left")
    }


def infer_midi_clef_plan(notes, boundaries) -> dict[int, dict[str, dict]]:
    """Choose RH clefs per measure from a stable two-bar MIDI register window.

    MIDI has no authored clef changes. A whole-piece average can incorrectly
    print treble over an opening bass-register passage; short exercise notes
    alone can fluctuate in the opposite direction. Look ahead two source
    measures and require a substantial ledger-line benefit, with hysteresis
    for subsequent switches. LH retains the tested whole-piece default.
    Returned keys are original 1-based bar numbers, independent of lessons.
    """
    if len(boundaries) < 2:
        return {}
    right = sorted(
        (note for note in notes if note.hand == "right"),
        key=lambda note: note.start)
    starts = [note.start for note in right]
    fallback = infer_piece_clefs(notes)["right"]
    current = fallback.copy()
    pending = ""
    pending_count = 0
    result: dict[int, dict[str, dict]] = {}
    for index in range(len(boundaries) - 1):
        start = boundaries[index]
        horizon = boundaries[min(index + 2, len(boundaries) - 1)]
        # Binary bounds keep long piano scores O(N log N + B log N)
        # rather than rescanning every MIDI note for every bar.
        lo = bisect_left(starts, start)
        hi = bisect_left(starts, horizon)
        pitches = [note.pitch for note in right[lo:hi]]
        candidate = ""
        if len(pitches) >= 2:
            # Positive advantage favours bass, negative favours treble.
            g_cost = sum(max(0, 64 - p, p - 77) for p in pitches) / len(pitches)
            f_cost = sum(max(0, 43 - p, p - 57) for p in pitches) / len(pitches)
            advantage = g_cost - f_cost
            if advantage >= 3.0:
                candidate = "F"
            elif advantage <= -3.0:
                candidate = "G"
        if index == 0 and candidate:
            current = {"sign":candidate,"line":4 if candidate == "F" else 2,
                       "octave_change":0}
        elif candidate and candidate != current["sign"]:
            pending_count = pending_count + 1 if pending == candidate else 1
            pending = candidate
            if pending_count >= 2:
                current = {"sign":candidate,
                           "line":4 if candidate == "F" else 2,
                           "octave_change":0}
                pending = ""
                pending_count = 0
        else:
            pending = ""
            pending_count = 0
        result[index + 1] = {"right":current.copy()}
    return result


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


def _midi_ornament_onsets(phrase, hand):
    """Recognize nearly exact 32nd-triplet runs in performed MIDI.

    Imported performances can land one original MIDI tick before a regular
    triplet grid. Printing those as isolated 64th/6:5 tuplets makes a genuine
    Chopin turn illegible and also forces excessive note/accidental spacing.
    Only correct the *display* onsets of a complete four-attack pattern; the
    untouched source beats in note bindings remain authoritative for grading.
    Unchanged source beat assignments and key-release measurements remain authoritative.
    """
    by_lane = defaultdict(set)
    for note in phrase.notes:
        if note.hand == hand:
            by_lane[(note.track, note.voice)].add(
                round(note.start-phrase.start, 9))
    result = {}
    unit = Fraction(1, 12)
    tolerance = .004
    for owner, attacks in by_lane.items():
        times = sorted(attacks)
        for i in range(len(times)-3):
            origin = round(times[i]*4)/4
            # Require the complete ornament to begin/end on the quarter
            # subdivisions; don't invent triplets from random expressive
            # rubato or arbitrary isolated note pairs.
            if abs(times[i]-origin) > tolerance:
                continue
            if any(abs(times[i+j]-(origin+float(unit)*j)) > tolerance
                   for j in range(4)):
                continue
            for j in range(4):
                result[(*owner,times[i+j])] = _ticks(
                    origin+float(unit)*j)
    return result


_RELEASE_GRID = DIVISIONS // 4


def _release_tolerance(rounded: int, end: int) -> float:
    """Beats a performed release may move to its 16th-grid value: shortening
    by at most .08 beat, lengthening by at most .15 beat."""
    return .08 if rounded < end else .15


# A performed chord's keys release a few ticks apart. Two raw releases are
# one written release when display quantization could move them to one value
# (at most .08 shorter plus .15 longer) and they differ by at most half the
# shorter note, so a 16th and a 32nd stay separate values.
_CHORD_RELEASE_SPREAD = .08 + .15


def _release_clusters(tones: list[dict], start: int) -> list[list[dict]]:
    """Tones of one attack grouped by raw release proximity, shortest first."""
    clusters: list[list[dict]] = []
    for tone in sorted(tones, key=lambda t: (t['end'], t['source_id'])):
        if clusters:
            first = clusters[-1][0]
            limit = min(_ticks(_CHORD_RELEASE_SPREAD), (first['end']-start)/2)
            if tone['end']-first['end'] <= limit:
                clusters[-1].append(tone)
                continue
        clusters.append([tone])
    return clusters


def _phrase_lanes(phrase, hand, grid=()):
    groups = defaultdict(list)
    attacks = {}
    identities = set()
    # A swung offbeat at MIDI beat .6 must reach the playhead at .6, not
    # .5: at the 40 BPM practice tempo that shift is 150 ms, larger than
    # the grader's onset tolerance. Only MIDI-tick-sized ornament noise may
    # move the displayed onset; rest clutter is handled independently.
    triplet_onsets = _midi_ornament_onsets(phrase, hand)
    ornament_onsets = triplet_onsets
    for index, note in enumerate(phrase.notes):
        if note.hand != hand:
            continue
        source = source_note_id(note,index)
        if source in identities:
            raise ValueError('Duplicate required source-note identity')
        identities.add(source)
        if not all(math.isfinite(value) for value in (note.start,note.end)) or not phrase.start <= note.start < min(note.end,phrase.end):
            raise ValueError('Source note attack/duration is outside the active phrase')
        original_start = _ticks(note.start-phrase.start)
        start = ornament_onsets.get(
            (note.track,note.voice,round(note.start-phrase.start,9)),
            original_start)
        end = _ticks(min(note.end,phrase.end)-phrase.start)
        if end <= start:
            raise ValueError('Source note duration cannot be represented at notation resolution')
        key = (note.track,note.voice,original_start)
        if key in attacks and abs(attacks[key]-(note.start-phrase.start)) > 1e-12:
            raise ValueError('Distinct source attacks collide at notation quantization resolution')
        attacks[key] = note.start-phrase.start
        display_key = (
            note.track,note.voice,round(note.start-phrase.start,9))
        timing = "triplet" if display_key in triplet_onsets else "exact"
        groups[note.track,note.voice,start].append({
            'source_id':source,'source_beat':note.start-phrase.start,
            'pitch':note.pitch,'hand':hand,'note':note,
            'notation_timing':timing,'end':end})
    events = []
    for (track, voice, start), attack in groups.items():
        # A performed MIDI chord keeps measured release offsets; cluster
        # adjacent releases before choosing notation timing for each group.
        clusters = _release_clusters(attack, start)
        for tones in clusters:
            end = sorted(t['end'] for t in tones)[(len(tones)-1)//2]
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
            # MIDI note-off is commonly just before a notated triplet's
            # next onset. Moonlight Sonata I has eighth-triplet attacks at
            # 0, 1/3, 2/3 beat but physical releases 0.01875 beat early.
            # Complete source-backed triplet runs must display the full
            # written 3:2 eighth duration: otherwise Verovio engraves
            # isolated irregular-ratio flags instead of a triple beam group.
            # Only display length changes; source-note timing and grading do
            # not. The onset grid, following source onset (or a completed
            # triplet beat), and tiny release gap must all independently fit.
            third = DIVISIONS // 3
            target = start + third
            next_start = lane[i+1][0] if i+1 < len(lane) else None
            beat_start = start // DIVISIONS * DIVISIONS
            in_triplet = ((start-beat_start) in (0, third, 2*third)
                          and end < target
                          and 0 < target-end <= _ticks(.025)
                          and target <= _ticks(phrase.end-phrase.start)
                          and (next_start is None or next_start >= target)
                          and not any(end <= _ticks(boundary) < target
                                      for boundary in grid))
            preceding_pair = (
                (start-beat_start) == 2*third
                and i >= 2
                and lane[i-2][0] == beat_start
                and lane[i-1][0] == beat_start+third)
            if in_triplet and (next_start == target or preceding_pair):
                end = target
            rounded = round(end/_RELEASE_GRID)*_RELEASE_GRID
            # Performance MIDI stores physical key release, not the intended
            # written duration. At Autumn Leaves measure 8, for example,
            # a 3.798-beat held note was printed as a triple-dotted 3.75
            # because the nearest 16th subdivision was chosen; a whole note
            # is far easier to read when the remainder is just key release.
            if end-start >= DIVISIONS:
                close_barline = next((
                    _ticks(boundary) for boundary in grid
                    if 0 < _ticks(boundary)-end <= _ticks(.25)
                ), None)
                if close_barline is not None:
                    rounded = close_barline
            # Never shorten an unusual expressive MIDI duration by more
            # than .08 beat. Small release noise around ordinary subdivisions
            # is still normalized; genuine .625-beat values are preserved.
            tolerance = _release_tolerance(rounded, end)
            if rounded > end and end-start >= DIVISIONS:
                tolerance = max(tolerance,.25) if rounded in {
                    _ticks(boundary) for boundary in grid} else tolerance
            if (_tuplet_type(end-start) is None and rounded > start
                    and abs(rounded-end) <= _ticks(tolerance)):
                end = min(rounded,_ticks(phrase.end-phrase.start),
                          lane[i+1][0] if i+1 < len(lane)
                          else _ticks(phrase.end-phrase.start))
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
                       inferred_clefs: dict[int, dict[str, dict]] | None = None,
                       barlines: tuple = (), written_marks: bool = True) -> LessonScore:
    """Create notation from the source measure grid, not averaged bars."""
    identities = [source_note_id(note,index) for index,note in enumerate(phrase.notes)]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate required source-note identity')
    grid = phrase_grid(phrase, boundaries)
    bars = len(grid) - 1
    changes = sorted(time_signatures)
    if any(not math.isfinite(beat) or numerator <= 0 or denominator <= 0
           for beat, numerator, denominator in changes):
        raise ValueError("Invalid imported time signature")
    barline_at = {}
    for mark in barlines:
        key = (round(mark.beat, 8), mark.location)
        current = (mark.style, mark.repeat, mark.ending)
        if key in barline_at and barline_at[key] != current:
            raise ValueError("Conflicting source barline declarations")
        barline_at[key] = current

    def append_barline(measure, beat, location):
        style_and_repeat = barline_at.get((round(beat, 8), location))
        if style_and_repeat is None:
            return
        style, direction, ending = style_and_repeat
        tag = ET.Element("barline", location=location)
        ET.SubElement(tag, "bar-style").text = style
        if ending is not None:
            ET.SubElement(tag, "ending", number=ending["number"],
                          type=ending["type"])
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
    lanes_by_staff = {hand:_phrase_lanes(phrase,hand,grid) for hand in ('right','left')}
    if not clef_changes:
        display_clefs = (default_clefs or infer_piece_clefs(phrase.notes)).copy()
        if inferred_clefs:
            display_clefs.update(inferred_clefs.get(phrase.first_bar, {}))
        lanes_by_staff = distribute_piano_registers(lanes_by_staff,display_clefs)
    for hand, ident in (("right", "RH"), ("left", "LH")):
        part = ET.SubElement(root, "part", id=ident)
        last_meter = None
        last_key = last_clef = None
        lanes = lanes_by_staff[hand]
        keys = sorted((key for key in key_signatures if key.hand in (hand,'both')),key=lambda item:item.beat)
        clefs = sorted((clef for clef in clef_changes if clef.hand in (hand,'both')),key=lambda item:item.beat)
        for lane in lanes:
            for _,_,tones in lane:
                for tone in tones:
                    attack_key = next((key for key in reversed(keys) if key.beat <= tone['note'].start+1e-7),None)
                    tone['spelling'] = _spelling(tone['note'],attack_key.fifths if attack_key else 0)
        midi_stems = _midi_voice_stems(lanes)
        for change in (*keys,*clefs):
            if phrase.start < change.beat < phrase.end and not any(abs(change.beat-phrase.start-beat)<1e-7 for beat in grid):
                raise ValueError('Mid-measure source key/clef changes are not supported in generated lessons')
        for b in range(bars):
            bar_start, bar_end = _ticks(grid[b]), _ticks(grid[b+1])
            if bar_end <= bar_start:
                raise ValueError("Source measure has no duration")
            beats, beat_type = source_meter(phrase.start + grid[b], grid[b+1] - grid[b], changes)
            if beats <= 0 or beat_type <= 0:
                raise ValueError("Invalid imported time signature")
            measure = ET.SubElement(part, "measure", number=str(phrase.first_bar+b))
            if abs((beats * 4.0 / beat_type) - (grid[b+1] - grid[b])) > 1e-5:
                measure.set("implicit", "yes")
            source_beat = phrase.start+grid[b]
            active_key = next((key for key in reversed(keys) if key.beat <= source_beat+1e-7),None)
            active_clef = next((clef for clef in reversed(clefs) if clef.beat <= source_beat+1e-7),None)
            key_value = (active_key.fifths,active_key.mode) if active_key else None
            # Original source clefs take precedence; otherwise use the
            # register-based MIDI plan shared by every exercise of this piece.
            # Without a plan, retain the whole-piece default rather than
            # inferring independently from a simplified practice variant.
            midi_bar_clefs = (
                inferred_clefs.get(phrase.first_bar + b, {})
                if inferred_clefs is not None else {})
            if active_clef is not None:
                chosen_clef = _readable_clef(
                    [note for note in phrase.notes if note.hand == hand],
                    active_clef, hand)
            elif hand in midi_bar_clefs:
                chosen_clef = midi_bar_clefs[hand].copy()
            elif default_clefs is not None and hand in default_clefs:
                chosen_clef = default_clefs[hand].copy()
            else:
                chosen_clef = _readable_clef(
                    [note for note in phrase.notes if note.hand == hand],
                    None, hand)
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
            _render_measure(measure,lanes,bar_end-bar_start,bar_start,bindings,
                            counts,
                            hide_performance_micro_rests=True,
                            midi_stems=midi_stems)
            _write_accidentals(measure,active_key.fifths if active_key else 0)
            _write_tuplet_groups(measure)
            # The native compiler engraves the selected MIDI attacks once,
            # retaining their source identities and actual rhythmic grid.
            beam_midi_measure(measure, beats, beat_type, DIVISIONS,
                              bar_end - bar_start)
            append_barline(measure,phrase.start+grid[b+1],"right")
    project_written_marks(root, phrase, bindings, DIVISIONS, written_marks)
    return LessonScore(
        ET.tostring(root, encoding="unicode"), phrase, bindings, staff_clefs)
