"""Loopback-only practice service for the native Godot UI.

Start: python -m piano_teacher.server. No Internet, account, or Qt required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .learning import LearningPlan
from .practice import Recorder, evaluate
from .score import import_piece, render_layout, EngravedScore
from .feedback import project_assessment
from .library import ScoreLibrary
from .raster import rasterize_score
from .recovery import check_two_bar_window
from .music import Phrase
from .lesson_score import build_lesson_score
from .lesson_validation import require_lesson_alignment
from .live_feedback import settled_assessment


class PracticeEngine:
    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True):
        self.lock = threading.RLock()
        self.plan: LearningPlan | None = None
        self.score = None
        self.source = None
        self.fingerprint = ""
        self.recorder: Recorder | None = None
        self.run_at = 0.0
        self.play_from_beat = 0.0
        self.next_boundary_beat = 0.0
        self.pending_rewind: float | None = None
        self.feedback_seconds = 2.5
        self.paused = False
        self.paused_at = 0.0
        self.transport_id = 0
        self.running = False
        self.auto = False
        self.preview_only = False
        self.count_in_beats = 0
        self.feedback = "Open a MIDI or MusicXML file"
        self.score_revision = 0
        self._layout_cache: EngravedScore | None = None
        self._layout_revision = -1
        self._page_png: dict[int, bytes] = {}
        self.next_at = 0.0
        self.awaiting_score_revision: int | None = None
        self.pending_result = None
        self.feedback_marks: list[dict] = []
        self.feedback_unmapped = 0
        self.midi_port = None
        self.midi_device = ""
        self.enable_midi = enable_midi
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "progress.db", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER)")
        columns={row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        if "target_bpm" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN target_bpm INTEGER")
        if "variant_index" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN variant_index INTEGER NOT NULL DEFAULT 0")
        self.db.execute("CREATE TABLE IF NOT EXISTS mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY (fingerprint, exercise))")
        self.db.commit()

    def ports(self) -> list[str]:
        if not self.enable_midi:
            return []
        import mido
        return mido.get_input_names()

    def connect(self, name: str):
        with self.lock:
            if self.midi_port:
                self.midi_port.close()
                self.midi_port = None
            self.midi_device = ""
            if name:
                import mido
                self.midi_port = mido.open_input(name, callback=self._receive)
                self.midi_device = name
            self._stop()
            self.library.update(midi_device=name)

    def library_listing(self) -> dict:
        with self.lock:
            return self.library.scan()

    def preferences(self) -> dict:
        with self.lock:
            return self.library.public_settings()

    def set_preferences(self, **changes) -> dict:
        with self.lock:
            return self.library.update(**changes)

    def load_library(self, identifier: str) -> None:
        with self.lock:
            path = self.library.resolve(identifier)
        self.load(str(path))  # Parse before recording success.
        with self.lock:
            self.library.mark_opened(identifier)

    def _receive(self, message):
        # Timestamp in the hardware input callback, not on the rendering thread.
        now = time.monotonic()
        with self.lock:
            if self.running and not self.paused and now >= self.run_at and self.recorder:
                if message.type == "note_on":
                    self.recorder.add(message.note, message.velocity > 0, now - self.run_at)
                elif message.type == "note_off":
                    self.recorder.add(message.note, False, now - self.run_at)

    def load(self, path: str):
        piece, score = import_piece(path)
        with self.lock:
            self._stop()
            self.source = str(Path(path).resolve())
            self.fingerprint = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            self.plan = LearningPlan(piece)
            self.score = score
            self._restore()
            self.feedback = "Press Start to practice"
            self.score_revision += 1
            self.pending_result = None
            self.feedback_marks = []
            self.feedback_unmapped = 0

    def _restore(self):
        p = self.plan
        if p is None:
            return
        row = self.db.execute("SELECT exercise,hand,bpm,streak,target_bpm,variant_index FROM sessions WHERE fingerprint=?",(self.fingerprint,)).fetchone()
        if row:
            p.select(min(max(0,int(row[0])),len(p.exercises)-1))
            if row[1] in p.hands:
                p.set_hand(row[1])
            p.set_bpm(int(row[4] or p.piece.bpm))
            p.bpm = int(row[2])
            p.streak = int(row[3])
            p.variant_index = min(max(0,int(row[5])),len(p.variants)-1)
        for key,bpm in self.db.execute("SELECT exercise,bpm FROM mastery WHERE fingerprint=?",(self.fingerprint,)):
            p.mastered[key]=bpm

    def _save(self):
        p=self.plan
        if p is None:
            return
        self.db.execute("INSERT OR REPLACE INTO sessions (fingerprint,exercise,hand,bpm,streak,target_bpm,variant_index) VALUES (?,?,?,?,?,?,?)",
                        (self.fingerprint,p.index,p.hand,p.bpm,p.streak,p.target_bpm,p.variant_index))
        for key, bpm in p.mastered.items():
            self.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)", (self.fingerprint,key,bpm))
        self.db.commit()

    def _stop(self):
        self.paused=False
        self.paused_at=0.0
        self.running=False
        self.auto=False
        self.preview_only=False
        self.count_in_beats=0
        self.next_at=0
        self.awaiting_score_revision=None
        self.pending_rewind=None
        self.play_from_beat=0.0
        self.recorder=None
        self.pending_result=None
        self.feedback_marks=[]
        self.feedback_unmapped=0

    def _commit_pending(self) -> str:
        """Apply a completed attempt after feedback has been shown on its own score."""
        if self.pending_result is None or self.plan is None:
            return ""
        p = self.plan
        result = self.pending_result
        self.pending_result = None
        before = p.identity
        message = p.apply_result(correct=result.correct,
                                 total=len(result.notes), extras=result.extra_notes)
        if p.identity != before:
            self.score_revision += 1
        self._save()
        return message

    def start(self, *, from_beat: float = 0.0):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            # A user must be able to watch the time-driven score without a
            # connected instrument. Only actual MIDI input enables assessment.
            self.preview_only = self.midi_port is None
            phrase=self.plan.active_phrase
            self.play_from_beat=max(0.0,min(float(from_beat),phrase.end-phrase.start-1e-6))
            self.paused=False
            self.paused_at=0.0
            self.transport_id+=1
            self.running=True
            self.auto=not self.preview_only
            self.next_at=0
            self.awaiting_score_revision=None
            self.pending_result=None
            self.pending_rewind=None
            self.feedback_marks=[]
            self.feedback_unmapped=0
            self.recorder=Recorder()
            measures=max(1, phrase.last_bar - phrase.first_bar+1)
            beats_per_bar=(phrase.end-phrase.start)/measures
            self.count_in_beats=max(1,round(2*beats_per_bar))
            self.next_boundary_beat = min(phrase.end-phrase.start,
                (int(self.play_from_beat/(2*beats_per_bar))+1)*2*beats_per_bar)
            self.run_at=time.monotonic()+self.count_in_beats*60/self.plan.bpm
            self.feedback="Count in, then play"

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            # Explicit navigation, Stop and Restart abandon the current
            # attempt. Only the timed feedback lifecycle commits assessment.
            # Otherwise Stop during feedback could accidentally earn mastery.
            if action == "score_ready":
                revision = int(kwargs.get("revision", -1))
                # Ignore delayed PNG acknowledgements from older passages.
                if self.awaiting_score_revision == revision and revision == self.score_revision:
                    self.start()
                return
            if action == "stop":
                self._stop()
                self.feedback="Stopped"
                return
            if action in ("start", "restart"):
                self.start()  # Fresh count-in; previous MIDI notes cannot carry over.
                return
            if action == "pause":
                if not self.running or self.paused:
                    raise ValueError("Cannot pause unless an exercise is playing")
                self.paused_at = time.monotonic()
                self.paused = True
                self.feedback = "Paused"
                return
            if action == "resume":
                if not self.running or not self.paused:
                    raise ValueError("Cannot resume unless an exercise is paused")
                # Shift time-zero by the exact suspended duration, preserving
                # both the count-in and all note timestamps on the same clock.
                self.run_at += time.monotonic() - self.paused_at
                self.paused_at = 0.0
                self.paused = False
                self.feedback = "Count in" if time.monotonic() < self.run_at else "Playing"
                return
            p=self.plan
            if not p:
                raise ValueError("Open a piece first")
            self._stop()
            if action == "next":
                p.jump(1)
            elif action == "previous":
                p.jump(-1)
            elif action == "hand":
                p.set_hand(str(kwargs.get("hand", "both")))
            elif action == "tempo":
                p.set_bpm(int(kwargs["bpm"]))
            else:
                raise ValueError(f"Unsupported action: {action}")
            self.score_revision+=1
            self.feedback="Ready"
            self._save()

    def _update(self):
        if not self.plan:
            return
        now=time.monotonic()
        if self.pending_result is not None:
            if self.next_at and now >= self.next_at:
                previous_revision = self.score_revision
                message = self._commit_pending()
                self.feedback_marks=[]
                self.feedback_unmapped=0
                if self.auto and message != "Piece mastered":
                    if self.score_revision != previous_revision:
                        # Never consume the next count-in while Godot is still
                        # rendering the newly selected score and its note map.
                        self.awaiting_score_revision = self.score_revision
                        self.auto = False
                        self.feedback = "Preparing next passage"
                        self.next_at = 0
                    else:
                        self.start()
                else:
                    self.next_at=0
                    self.auto=False
                    self.feedback = message or self.feedback
            return
        if self.pending_rewind is not None:
            if now >= self.next_at:
                where = self.pending_rewind
                self.start(from_beat=where)
            return
        if not self.running or self.paused or now < self.run_at:
            return
        phrase=self.plan.active_phrase
        total_beats=phrase.end-phrase.start
        elapsed_beats=max(0.0,(now-self.run_at)*self.plan.bpm/60)
        score_beat=self.play_from_beat+elapsed_beats
        beats_per_bar=total_beats/max(1,phrase.last_bar-phrase.first_bar+1)
        # Defer five-error recovery until the two-bar boundary. Silent
        # previews never generate failure, assessment or mastery.
        while not self.preview_only and self.next_boundary_beat and score_beat >= self.next_boundary_beat:
            decision=check_two_bar_window(phrase,self.plan.hand,self.plan.bpm,
                self.recorder.presses if self.recorder else [],
                from_beat=self.play_from_beat, end_beat=self.next_boundary_beat,
                beats_per_bar=beats_per_bar)
            if decision is not None:
                self.plan.streak=0
                self.plan.failures+=1
                before=self.plan.bpm
                self.plan.bpm=max(12,round(before*.9))
                self._save()
                self.pending_rewind=decision.restart_beat
                self.running=False
                self.recorder=None
                self.next_at=now+self.feedback_seconds
                # The same live notehead markers remain visible during the
                # feedback pause, even though this is not a full graded run.
                self.feedback_marks=self._live_feedback((now-self.run_at))
                self.feedback=(f"{decision.errors} wrong or missed notes - retrying from "
                               f"measure {phrase.first_bar + int(decision.restart_beat/beats_per_bar)} "
                               f"at {self.plan.bpm} BPM")
                return
            previous_boundary=self.next_boundary_beat
            self.next_boundary_beat=min(total_beats,self.next_boundary_beat+2*beats_per_bar)
            if self.next_boundary_beat <= previous_boundary + 1e-7:
                self.next_boundary_beat=0.0
        duration=(total_beats-self.play_from_beat)*60/self.plan.bpm
        if now < self.run_at+duration+0.20:
            return
        if self.preview_only:
            # Never grade an empty MIDI recording or retry forever simply
            # because the user's piano has not been connected yet.
            self._stop()
            self.feedback = "Timing preview complete - connect a USB MIDI piano for scoring"
            return
        active_phrase=Phrase(phrase.number,phrase.first_bar,phrase.last_bar,
            phrase.start+self.play_from_beat,phrase.end,
            tuple(n for n in phrase.notes if n.start>=phrase.start+self.play_from_beat-1e-7))
        result=evaluate(active_phrase,self.plan.hand,self.plan.bpm,self.recorder.presses if self.recorder else [])
        # Keep the just-played score visible for feedback. Curriculum changes
        # are applied only after the display interval, never mid-feedback.
        try:
            projection = project_assessment(result, phrase, self.plan.bpm,
                                            self.engraving().layout, played_from_beat=self.play_from_beat)
            self.feedback_marks = projection["marks"]
            self.feedback_unmapped = projection["unmapped"]
        except (ValueError, RuntimeError, KeyError) as exc:
            self.feedback_marks = []
            self.feedback_unmapped = len(result.notes)
            self.feedback = f"Engraving feedback unavailable: {exc}"
        else:
            self.feedback = result.summary
        self.running=False
        self.recorder=None
        if self.play_from_beat>1e-6:
            # A clean *partial* recovery cannot confer full passage mastery.
            self.pending_rewind=0.0
            self.feedback="Retry complete - now play the whole passage"
            self.next_at=now+self.feedback_seconds
            return
        self.pending_result=result
        self.next_at=now+self.feedback_seconds if self.auto else 0

    def _live_feedback(self, elapsed_seconds: float) -> list[dict]:
        """Project graded noteheads without waiting for the final attempt."""
        p=self.plan
        if (p is None or self.preview_only or not self.running
                or self._layout_revision != self.score_revision or self._layout_cache is None):
            return []
        phrase=p.active_phrase
        total=phrase.end-phrase.start
        if total<=0 or elapsed_seconds<0:
            return []
        per_bar=total/max(1,phrase.last_bar-phrase.first_bar+1)
        now_beat=self.play_from_beat+elapsed_seconds*p.bpm/60
        result=settled_assessment(phrase,p.hand,p.bpm,
                                  self.recorder.presses if self.recorder else [],
                                  from_beat=self.play_from_beat,
                                  until_beat=now_beat,beats_per_bar=per_bar)
        if result is None:
            return []
        try:
            return project_assessment(result,phrase,p.bpm,self._layout_cache.layout,
                                      played_from_beat=self.play_from_beat)["marks"]
        except (ValueError, RuntimeError, KeyError):
            return []

    def state(self) -> dict:
        with self.lock:
            self._update()
            p=self.plan
            if not p:
                return {"loaded":False,"running":False,"paused":False,"transport_id":self.transport_id,
                        "clock_beat":0.0,"feedback":self.feedback,"device":self.midi_device,"revision":self.score_revision}
            ex=p.exercise
            variant=p.active_variant
            now=self.paused_at if self.paused else time.monotonic()
            seconds=(ex.phrase.end-ex.phrase.start)*60/p.bpm
            elapsed=now-self.run_at
            exercise_beat=self.play_from_beat+max(0.0,elapsed*p.bpm/60)
            progress=min(1.0,max(0.0, exercise_beat/(ex.phrase.end-ex.phrase.start))) if self.running else 0.0
            phase=("paused" if self.paused else "count_in" if elapsed<0 else "playing") if self.running else "feedback" if self.pending_result is not None else "loading" if self.awaiting_score_revision is not None else "recovering" if self.pending_rewind is not None else "ready"
            live_marks=self._live_feedback(elapsed) if phase == "playing" else []
            return {"loaded":True,"title":p.piece.title,"kind":ex.kind,
                    "first_bar":ex.phrase.first_bar,"last_bar":ex.phrase.last_bar,
                    "exercise":p.index+1,"exercise_count":len(p.exercises),
                    "lesson_level":variant.level,"lesson_level_number":p.variant_index+1,
                    "lesson_level_count":len(p.variants),"required_notes":len(variant.notes),
                    "lesson_step":p.lesson_step_number,"lesson_steps":len(p.lesson_steps),
                    "lesson_steps_mastered":p.lesson_steps_mastered,
                    "hand":p.hand,"hands":list(p.hands),"bpm":p.bpm,"original_bpm":p.piece.bpm,"target_bpm":p.target_bpm,
                    "streak":p.streak,"mastered":len(p.mastered),"phase":phase,
                    "countdown":max(0,-elapsed) if self.running else 0,
                    "lead_in_bars":2,"play_from_beat":self.play_from_beat,
                    "recovery_beat":self.pending_rewind,
                    "clock_beat":elapsed*p.bpm/60 if self.running else 0.0,
                    "paused":self.paused,"transport_id":self.transport_id,
                    "awaiting_score_revision":self.awaiting_score_revision,
                    "count_in_beats":self.count_in_beats if self.running else 0,
                    "midi_notes":len(self.recorder.presses) if self.recorder is not None else 0,
                    "preview_only":self.preview_only,
                    "progress":progress,"duration":seconds,"beat":exercise_beat if self.running else 0.0,
                    "duration_beats":ex.phrase.end - ex.phrase.start,"running":self.running,
                    "device":self.midi_device,"feedback":self.feedback,"revision":self.score_revision,
                    "feedback_marks":self.feedback_marks if phase in ("feedback", "recovering") else live_marks,
                    "feedback_unmapped":self.feedback_unmapped if phase in ("feedback", "recovering") else 0}

    def engraving(self) -> EngravedScore:
        with self.lock:
            if not self.plan:
                raise ValueError("No piece loaded")
            if self._layout_revision != self.score_revision or self._layout_cache is None:
                p=self.plan
                phrase=p.active_phrase
                notation=build_lesson_score(phrase)
                layout = render_layout(notation,phrase.first_bar,phrase.last_bar,p.hand,
                                       total_beats=phrase.end - phrase.start)
                require_lesson_alignment(phrase, layout.layout, p.hand)
                self._layout_cache = layout
                self._page_png.clear()
                self._layout_revision=self.score_revision
            return self._layout_cache

    def engraved(self, page: int = 0) -> str:
        score=self.engraving()
        if not 0 <= page < len(score.pages):
            raise ValueError("Invalid score page")
        return score.pages[page]

    def engraved_png(self, page: int = 0) -> bytes:
        # Verovio glyph references are not rendered consistently by Godot SVG.
        # Keep the SVG for geometry, but send a verified raster page to the UI.
        with self.lock:
            score = self.engraving()
            if not 0 <= page < len(score.pages):
                raise ValueError("Invalid score page")
            if page not in self._page_png:
                self._page_png[page] = rasterize_score(score.pages[page])
            return self._page_png[page]

    def geometry(self) -> dict:
        return self.engraving().layout

    def lesson_overview(self) -> dict:
        """Full readable curriculum, with unique per-hand/per-level progress."""
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            p = self.plan
            return {
                "current_step": p.lesson_step_number,
                "total_steps": len(p.lesson_steps),
                "completed_steps": p.lesson_steps_mastered,
                "steps": [
                    {"number": i+1, "exercise": step.exercise_index+1,
                     "hand": step.hand, "level": step.level, "key": step.key,
                     "kind": step.kind, "first_bar": step.first_bar,
                     "last_bar": step.last_bar, "required_notes": step.required_notes,
                     "completed": step.key in p.mastered}
                    for i, step in enumerate(p.lesson_steps)
                ],
            }


class Handler(BaseHTTPRequestHandler):
    engine: PracticeEngine
    def _reply(self, status: int, content: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(content)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(content)
    def _json(self, status, data):
        self._reply(status,json.dumps(data).encode(),"application/json")
    def do_GET(self):
        try:
            route=urlsplit(self.path).path
            if route=="/state":
                self._json(200,self.engine.state())
            elif route=="/library":
                self._json(200,self.engine.library_listing())
            elif route=="/lesson":
                self._json(200,self.engine.lesson_overview())
            elif route=="/settings":
                self._json(200,self.engine.preferences())
            elif route=="/devices":
                self._json(200,{"devices":self.engine.ports()})
            elif route=="/score/layout":
                self._json(200,self.engine.geometry())
            elif route in ("/score.svg", "/score.png"):
                from urllib.parse import parse_qs
                values=parse_qs(urlsplit(self.path).query).get("page", ["0"])
                page=int(values[0])
                if route=="/score.png":
                    self._reply(200,self.engine.engraved_png(page),"image/png")
                else:
                    self._reply(200,self.engine.engraved(page).encode(),"image/svg+xml; charset=utf-8")
            else:
                self._json(404,{"error":"Not found"})
        except Exception as exc:
            self._json(400,{"error":str(exc)})
    def do_POST(self):
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length > 1_000_000:
                raise ValueError("Request too large")
            args=json.loads(self.rfile.read(length)) if length else {}
            route=urlsplit(self.path).path
            if route=="/load":
                self.engine.load(args["path"])
            elif route=="/library/open":
                self.engine.load_library(args["id"])
            elif route=="/settings":
                self.engine.set_preferences(**args)
            elif route=="/device":
                self.engine.connect(args.get("name",""))
            elif route=="/control":
                self.engine.control(**args)
            else:
                self._json(404,{"error":"Not found"})
                return
            self._json(200,self.engine.preferences() if route == "/settings" else self.engine.state())
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            self._json(400,{"error":str(exc)})
        except Exception as exc:
            # Converter and plugin exceptions must not close the HTTP socket,
            # leaving Godot with no actionable error message.
            import traceback
            traceback.print_exc()
            self._json(500, {"error": f"Piano Teacher could not complete this request: {exc}"})
    def log_message(self, format, *args):
        return


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--no-midi",action="store_true",help="Test server without an attached MIDI device")
    args=parser.parse_args()
    Handler.engine=PracticeEngine(enable_midi=not args.no_midi)
    # The service must never bind to a public interface.
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Piano Teacher backend: http://127.0.0.1:{args.port}",flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        Handler.engine.connect("")
        Handler.engine.db.close()

if __name__=="__main__":
    main()
