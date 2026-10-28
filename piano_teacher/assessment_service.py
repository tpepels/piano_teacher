"""Assessment policy independent of session state, transport and persistence.

The practice engine owns the Recorder and score timing, and supplies an
immutable view of the current source phrase and played MIDI attacks. This
service grades a bounded take, builds the source-bar review, and matches
live feedback to real engraved noteheads. It does not mutate lesson state.
"""
from __future__ import annotations

from .music import Phrase, note_name
from .measure_grid import phrase_grid, two_bar_chunks, bar_number_at
from .practice import evaluate
from .feedback import project_assessment
from .live_feedback import settled_assessment, expired_attack_misses


class AssessmentService:
    def assess_take(self, phrase: Phrase, *, hand: str, bpm: float, played,
                    from_beat: float, end_beat: float, evaluator=evaluate):
        """Grade only events in the attempted source interval."""
        active_phrase = Phrase(
            phrase.number, phrase.first_bar, phrase.last_bar,
            phrase.start+from_beat, phrase.start+end_beat,
            tuple(note for note in phrase.notes
                  if phrase.start+from_beat-1e-7 <= note.start
                  < phrase.start+end_beat-1e-7))
        return evaluator(active_phrase, hand, bpm, played)

    def review(self, phrase: Phrase, result, *, bar_boundaries, played_from_beat: float, bpm: float) -> dict:
        """Review real scored attacks by source measure, including chord pitches.

        Every recommended retry corresponds to an existing two-bar source
        interval. No independent note judgement or synthetic timing is used.
        """
        grid = phrase_grid(phrase, bar_boundaries)
        weaknesses = []
        sections = []
        for start, end in two_bar_chunks(grid):
            issues = []
            counts = {status: 0 for status in
                      ("missed", "wrong", "early", "late", "short", "long", "extra")}
            for entry in result.notes:
                local = entry.note.start - phrase.start
                if entry.status == "correct" or not start-1e-7 <= local < end-1e-7:
                    continue
                counts[entry.status] += 1
                issue = {"bar": bar_number_at(grid, local, phrase.first_bar),
                         "status": entry.status,
                         "pitch": entry.note.pitch,
                         "name": note_name(entry.note.pitch),
                         "hand": entry.note.hand,
                         "source_id": entry.note.source_id}
                if entry.played_pitch is not None:
                    issue["played_pitch"] = entry.played_pitch
                    issue["played_name"] = note_name(entry.played_pitch)
                issues.append(issue)
            for note in result.unmatched_played:
                local = played_from_beat + note.onset * bpm / 60
                if start-1e-7 <= local < end-1e-7:
                    counts["extra"] += 1
                    issues.append({"bar": bar_number_at(grid, local, phrase.first_bar),
                                   "status": "extra", "pitch": note.pitch,
                                   "name": note_name(note.pitch), "hand": "unknown"})
            errors = sum(counts.values())
            if not errors:
                continue
            first = next(i for i, beat in enumerate(grid) if abs(beat-start) < 1e-6)
            last = next(i for i, beat in enumerate(grid) if abs(beat-end) < 1e-6)
            section = {"first_bar": phrase.first_bar+first, "last_bar": phrase.first_bar+last-1,
                       "start_beat": start, "end_beat": end, "errors": errors,
                       "counts": counts,
                       "issues": sorted(issues, key=lambda issue:
                           (issue["bar"], issue["pitch"], issue["status"]))}
            weaknesses.append({key: section[key] for key in
                               ("first_bar", "last_bar", "start_beat", "end_beat", "errors")})
            sections.append(section)
        ordering = lambda entry: (-entry["errors"], entry["first_bar"])
        timing = {status: sum(entry.status == status for entry in result.notes)
                  for status in ("early", "late", "short", "long")}
        return {"accuracy_percent": round(100*result.correct/max(1, len(result.notes)), 1),
                "correct": result.correct, "total": len(result.notes), **timing, "timing": timing,
                "missed_pitches": sorted({entry.note.pitch for entry in result.notes if entry.status == "missed"}),
                "missed": sum(entry.status == "missed" for entry in result.notes),
                "wrong": sum(entry.status == "wrong" for entry in result.notes),
                "extra_notes": result.extra_notes,
                "sections": sorted(sections, key=ordering),
                "weakest_bars": sorted(weaknesses, key=ordering)}


    def live_marks(self, *, phrase: Phrase, hand: str, bpm: float, played,
                   played_from_beat: float, elapsed_seconds: float,
                   bar_boundaries, layout: dict, projector=project_assessment) -> list[dict]:
        """Score settled attacks and independently recognize expired misses."""
        total=phrase.end-phrase.start
        if total<=0 or elapsed_seconds<0:
            return []
        per_bar=total/max(1,phrase.last_bar-phrase.first_bar+1)
        now_beat=played_from_beat+elapsed_seconds*bpm/60
        settled=settled_assessment(phrase,hand,bpm,played,
                                  from_beat=played_from_beat,
                                  until_beat=now_beat,beats_per_bar=per_bar)
        grid=phrase_grid(phrase,bar_boundaries)
        active_bar=max(index for index, bar_beat in enumerate(grid)
                       if bar_beat <= now_beat + 1e-7)
        window_start=grid[max(0, active_bar-2)]
        missed=expired_attack_misses(phrase,hand,bpm,played,
                                     from_beat=played_from_beat,
                                     until_beat=now_beat,
                                     window_start_beat=window_start)
        if settled is None and missed is None:
            return []
        try:
            marks=[]
            if settled is not None:
                marks=projector(settled,phrase,bpm,layout,
                                         played_from_beat=played_from_beat)["marks"]
            if missed is not None:
                existing={m.get("note_id") for m in marks}
                new=projector(missed,phrase,bpm,layout,
                                       played_from_beat=played_from_beat)["marks"]
                marks.extend(m for m in new if m.get("note_id") not in existing)
            return marks
        except (ValueError, RuntimeError, KeyError):
            return []

