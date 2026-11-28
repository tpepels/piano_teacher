"""Value snapshot shared by the musical owner and notation subprocess."""

from dataclasses import dataclass, fields

from ..fingering.types import FingerAssignment, FingeringPlan
from ..music import BarlineChange, ClefChange, KeySignature, Note, Phrase, Piece


@dataclass(frozen=True, slots=True)
class ScoreSelection:
    piece: Piece
    phrase: Phrase
    hand: str
    stage_key: str
    revision: int
    fingerprint: str
    transformed_rhythm: bool = False

    @property
    def binding(self) -> dict:
        return {"fingerprint": self.fingerprint, "revision": self.revision,
                "stage_key": self.stage_key, "hand": self.hand}

    @property
    def identity(self) -> tuple:
        phrase = self.phrase
        return (id(self.piece.notes), self.fingerprint, self.stage_key, self.hand,
                self.transformed_rhythm, self.revision, phrase.first_bar,
                phrase.last_bar, phrase.start, phrase.end)

    def document(self, timing: dict) -> dict:
        # Only fields the notation pipeline reads. The course can contain
        # thousands of overlapping phrases and is never put on the wire.
        piece = self.piece
        return {
            "piece": {
                "title": piece.title, "bpm": piece.bpm,
                "notes": [note.score_document() for note in piece.notes],
                "bar_boundaries": piece.bar_boundaries,
                "time_signatures": piece.time_signatures,
                "key_signatures": [vars(key) for key in piece.key_signatures],
                "clef_changes": [vars(clef) for clef in piece.clef_changes],
                "barlines": [vars(barline) for barline in piece.barlines],
                "fingering_plan": _fingering_document(piece.fingering_plan),
            },
            "phrase": {**vars(self.phrase),
                       "notes": [note.score_document() for note in self.phrase.notes]},
            "timing": timing,
            "transformed_rhythm": self.transformed_rhythm,
        }


def _fingering_document(plan: FingeringPlan | None) -> dict | None:
    if plan is None:
        return None
    return {**{field.name: getattr(plan, field.name) for field in fields(plan)},
            "assignments": {key: vars(value) for key, value in plan.assignments.items()}}


def _notes(values: list[dict]) -> tuple[Note, ...]:
    return tuple(Note(**{**note, "spelling": tuple(note["spelling"])
                        if note["spelling"] is not None else None}) for note in values)


def decode_selection(binding: dict, document: dict) -> ScoreSelection:
    raw = document["piece"]
    fingering = raw["fingering_plan"]
    piece = Piece(
        title=raw["title"], bpm=raw["bpm"], notes=_notes(raw["notes"]), phrases=(),
        bar_boundaries=tuple(raw["bar_boundaries"]),
        time_signatures=tuple(map(tuple, raw["time_signatures"])),
        key_signatures=tuple(KeySignature(**value) for value in raw["key_signatures"]),
        clef_changes=tuple(ClefChange(**value) for value in raw["clef_changes"]),
        barlines=tuple(BarlineChange(**value) for value in raw["barlines"]),
        fingering_plan=_decode_fingering(fingering))
    return ScoreSelection(piece=piece, phrase=Phrase(**{
        **document["phrase"], "notes": _notes(document["phrase"]["notes"])}),
        **binding, transformed_rhythm=document["transformed_rhythm"])


def _decode_fingering(value: dict | None) -> FingeringPlan | None:
    if value is None:
        return None
    assignments = {
        key: FingerAssignment(**{**item, "authored_text": tuple(item["authored_text"])})
        for key, item in value["assignments"].items()
    }
    return FingeringPlan(**{**value, "assignments": assignments})
