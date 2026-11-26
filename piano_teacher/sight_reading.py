"""Procedural sight-reading scores on the existing timed practice engine."""
from __future__ import annotations
from dataclasses import replace
import math
import random
import secrets
from .music import Note, Phrase, Piece, KeySignature
from .learning import LearningPlan
from .lesson_contracts import Exercise, LessonPlanDefinition
from .exercise_pipeline import ExerciseStage
from .exercise_generator import ExerciseVariant
from .practice_flow_course import _base_decision
from .application.assessment_verdict import AssessmentVerdict
from .teaching_decisions import TeachingDecision, full_target_take

PROFILE = "sight-reading"
BARS = 16
TEMPOS = {"largo":40, "lento":50, "adagio":60, "andante":80,
          "moderato":100, "allegretto":112, "allegro":132, "vivace":160,
          "presto":184}
LEVELS = ("Single notes", "Sixteenth notes", "Triads", "Seventh chords",
          "Chord progressions")
LETTERS = "CDEFGAB"
NATURALS = (0,2,4,5,7,9,11)
TRIADS = ((0,4,7),(0,3,7),(0,3,6),(0,4,8))
SEVENTHS = ((0,4,7,11),(0,4,7,10),(0,3,7,10),(0,3,6,10),
            (0,3,6,9),(0,3,7,11),(0,4,8,11),(0,4,8,10))
# Six diatonic staff steps beyond the outer staff lines.
LOW, HIGH = 33, 88
KEYS = ((0,0),(7,1),(2,2),(9,3),(5,-1),(10,-2),(3,-3),(8,-4),
        (4,4),(11,5),(6,6),(1,-5))
MAJOR = (0,2,4,5,7,9,11)
MINOR = (0,2,3,5,7,8,11)
# Each entry is a diatonic degree and seventh-chord quality.
MAJOR_ROUTES = (
    ((0,0),(3,0),(4,1),(0,0)), ((0,0),(5,2),(1,2),(4,1)),
    ((1,2),(4,1),(0,0),(5,2)), ((0,0),(2,2),(3,0),(4,1)),
    ((0,0),(4,1),(5,2),(3,0)), ((0,0),(1,2),(4,1),(5,2)),
    ((3,0),(0,0),(1,2),(4,1)), ((0,0),(6,3),(2,2),(5,2)),
)
MINOR_ROUTES = (
    ((0,2),(3,2),(4,1),(0,2)), ((0,2),(5,0),(1,3),(4,1)),
    ((0,2),(2,6),(5,0),(4,1)), ((1,3),(4,1),(0,2),(0,2)),
    ((0,2),(6,4),(0,2),(3,2)), ((0,2),(4,1),(5,0),(4,1)),
)


def _spelling(pitch, letter):
    index = LETTERS.index(letter)
    octave = round((pitch-NATURALS[index])/12)-1
    alter = pitch-(12*(octave+1)+NATURALS[index])
    return letter, alter, octave


def _spell_pitch(pitch, fifths):
    order = "FCGDAEB" if fifths >= 0 else "BEADGCF"
    signature = {letter:1 if fifths > 0 else -1 for letter in order[:abs(fifths)]}
    options = [_spelling(pitch, letter) for letter in LETTERS]
    return min(options,key=lambda s:(s[1] != signature.get(s[0],0),abs(s[1]),
                                    s[1] > 0 if fifths < 0 else s[1] < 0))


def _near(rng, values, previous, sigma):
    weights = [math.exp(-.5*((value-previous)/sigma)**2) for value in values]
    return rng.choices(values,weights=weights,k=1)[0]


def _voicings(root, intervals):
    for inversion in range(len(intervals)):
        rotated = intervals[inversion:]+tuple(x+12 for x in intervals[:inversion])
        for octave in range(1,8):
            pitches = tuple(root+12*octave+x for x in rotated)
            if LOW <= pitches[0] and pitches[-1] <= HIGH:
                yield inversion,pitches


def generate_piece(level, tempo, *, seed):
    if type(level) is not int or not 1 <= level <= len(LEVELS):
        raise ValueError("Choose a sight-reading level from 1 to 5")
    if not isinstance(tempo,str) or tempo not in TEMPOS:
        raise ValueError("Choose a named sight-reading tempo")
    rng = random.Random(seed)
    bpm = TEMPOS[tempo]
    tonic,fifths = rng.choice(KEYS) if level == 5 else (0,0)
    minor = level == 5 and rng.random() < .4
    if minor:
        tonic = (tonic+9)%12
    notes = []
    previous = 60
    previous_chord = ()

    def add(beat,duration,pitches,spellings=None,hand=None):
        for i,pitch in enumerate(pitches):
            staff = hand or ("left" if pitch < 60 else "right")
            notes.append(Note(beat,beat+duration,pitch,0 if staff=="right" else 1,
                0 if staff=="right" else 1,staff,f"reading-{len(notes)+1}",
                "1",spellings[i] if spellings else _spell_pitch(pitch,fifths)))

    if level <= 2:
        scale = [p for p in range(LOW,HIGH+1) if p%12 in NATURALS]
        for bar in range(BARS):
            beat = 0.0
            while beat < 4:
                choices = (1.,.5) if level==1 else (1.,.5,.25)
                duration = rng.choice([d for d in choices if beat+d <= 4])
                pitch = _near(rng,scale,previous,5.0)
                add(bar*4+beat,duration,(pitch,))
                previous = pitch
                beat += duration
    else:
        progression = []
        if level == 5:
            routes = MINOR_ROUTES if minor else MAJOR_ROUTES
            for _ in range(BARS//2):
                progression.extend(rng.choice(routes))
            progression[-2:] = [(4,1),(0,2 if minor else 0)]
        for attack in range(BARS*2):
            if level == 5:
                degree,quality = progression[attack]
                root = (tonic+(MINOR if minor else MAJOR)[degree])%12
                intervals = SEVENTHS[quality]
                if rng.random() < .35:
                    intervals = intervals[:3]
            else:
                root = _near(rng,list(range(LOW,HIGH+1)),previous,5.0)%12
                intervals = rng.choice(TRIADS if level==3 else TRIADS+SEVENTHS)
            candidates = list(_voicings(root,intervals))
            weights = []
            for _,pitches in candidates:
                center = sum(pitches)/len(pitches)
                motion = (sum(min(abs(p-q) for q in previous_chord) for p in pitches)/len(pitches)
                          if previous_chord else abs(center-previous))
                weights.append(math.exp(-.5*((center-previous)/8.0)**2)/(1+motion*.15))
            inversion,pitches = rng.choices(candidates,weights=weights,k=1)[0]
            root_letter = LETTERS.index(_spell_pitch(root+60,fifths)[0])
            spellings = [_spelling(pitch,LETTERS[(root_letter+2*((inversion+i)%len(intervals)))%7])
                         for i,pitch in enumerate(pitches)]
            hand = "right" if sum(pitches)/len(pitches)>=60 else "left"
            add(attack*2,2.,pitches,spellings,hand)
            previous = sum(pitches)/len(pitches)
            previous_chord = pitches
    boundaries = tuple(float(i*4) for i in range(BARS+1))
    phrase = Phrase(1,1,BARS,0.,boundaries[-1],tuple(notes))
    return Piece(f"Sight reading · Level {level} · {tempo.capitalize()}",bpm,
        tuple(notes),(phrase,),bar_boundaries=boundaries,time_signatures=((0.,4,4),),
        key_signatures=(KeySignature(0.,fifths,mode="minor" if minor else "major"),),
        source_format="midi")


class SightReadingGenerator:
    name = PROFILE

    def generate(self,piece):
        phrase = piece.phrases[0]
        exercise = Exercise("perform",phrase,"reading:round",hands=("both",))
        variant = ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))
        return LessonPlanDefinition((exercise,),{(exercise.key,"both"):(ExerciseStage(variant),)},
                                    self.name,requires_unique_source_ids=True)

    def decide_teaching(self,event,state):
        if event.kind in ("full_result","focused_result"):
            result = event.assessment
            eligible = full_target_take(event,state)
            verdict = AssessmentVerdict.decide(result,policy="practice-flow",eligible=eligible)
            return TeachingDecision(1,event.event_id+":teaching",event.event_id,state.binding,
                state.progress,state.definition,state.progress,None,None,"stop",
                eligible and not verdict.accepted,False,"sight_reading",
                f"Round complete · {result.accuracy_percent:.1f}% accuracy",None,verdict)
        decision = _base_decision(event,state)
        if decision.next_exposure is not None:
            bpm = state.progress.target_bpm
            return replace(decision,progress_after=replace(decision.progress_after,bpm=bpm),
                next_exposure=replace(decision.next_exposure,bpm=bpm,mode="practice",
                                      assisted=False,automatic=False))
        return decision


def new_round(level,tempo):
    seed = secrets.randbits(256)
    piece = generate_piece(level,tempo,seed=seed)
    return LearningPlan(piece,lesson_generator=SightReadingGenerator()),f"{seed:064x}"
