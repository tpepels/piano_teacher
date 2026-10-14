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


class PracticeEngine:
    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True):
        self.lock = threading.RLock()
        self.plan: LearningPlan | None = None
        self.score = None
        self.source = None
        self.fingerprint = ""
        self.recorder: Recorder | None = None
        self.run_at = 0.0
        self.running = False
        self.auto = False
        self.feedback = "Open a MIDI or MusicXML file"
        self.score_revision = 0
        self._layout_cache: EngravedScore | None = None
        self._layout_revision = -1
        self._page_png: dict[int, bytes] = {}
        self.next_at = 0.0
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
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER)")
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
            if self.running and self.recorder:
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
        row = self.db.execute("SELECT exercise,hand,bpm,streak FROM sessions WHERE fingerprint=?",(self.fingerprint,)).fetchone()
        if row:
            p.select(min(max(0,int(row[0])),len(p.exercises)-1))
            if row[1] in p.hands:
                p.set_hand(row[1])
            p.set_bpm(int(row[2]))
            p.streak = int(row[3])
        for key,bpm in self.db.execute("SELECT exercise,bpm FROM mastery WHERE fingerprint=?",(self.fingerprint,)):
            p.mastered[key]=bpm

    def _save(self):
        p=self.plan
        if p is None:
            return
        self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)",
                        (self.fingerprint,p.index,p.hand,p.bpm,p.streak))
        for key, bpm in p.mastered.items():
            self.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)", (self.fingerprint,key,bpm))
        self.db.commit()

    def _stop(self):
        self.running=False
        self.auto=False
        self.next_at=0
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
        before = (p.index, p.hand)
        message = p.apply_result(correct=result.correct,
                                 total=len(result.notes), extras=result.extra_notes)
        if (p.index, p.hand) != before:
            self.score_revision += 1
        self._save()
        return message

    def start(self):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            if self.enable_midi and self.midi_port is None:
                raise ValueError("Connect your USB MIDI piano first")
            self.running=True
            self.auto=True
            self.next_at=0
            self.pending_result=None
            self.feedback_marks=[]
            self.feedback_unmapped=0
            self.recorder=Recorder()
            phrase=self.plan.exercise.phrase
            measures=max(1, phrase.last_bar - phrase.first_bar+1)
            count_in_beats=max(1,round((phrase.end-phrase.start)/measures))
            self.run_at=time.monotonic()+count_in_beats*60/self.plan.bpm
            self.feedback="Count in, then play"

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            if self.pending_result is not None:
                self._commit_pending()
            if action == "stop":
                self._stop()
                self.feedback="Stopped"
                return
            if action == "start":
                self.start()
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
                message = self._commit_pending()
                self.feedback_marks=[]
                self.feedback_unmapped=0
                if self.auto and message != "Piece mastered":
                    self.start()
                else:
                    self.next_at=0
                    self.auto=False
                    self.feedback = message or self.feedback
            return
        if not self.running or now < self.run_at:
            return
        phrase=self.plan.exercise.phrase
        duration=(phrase.end - phrase.start)*60/self.plan.bpm
        if now < self.run_at+duration+0.20:
            return
        result=evaluate(phrase,self.plan.hand,self.plan.bpm,self.recorder.presses if self.recorder else [])
        # Keep the just-played score visible for feedback. Curriculum changes
        # are applied only after the display interval, never mid-feedback.
        try:
            projection = project_assessment(result, phrase, self.plan.bpm,
                                            self.engraving().layout)
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
        self.pending_result=result
        self.next_at=now+2.5 if self.auto else 0

    def state(self) -> dict:
        with self.lock:
            self._update()
            p=self.plan
            if not p:
                return {"loaded":False,"running":False,"feedback":self.feedback,"device":self.midi_device,"revision":self.score_revision}
            ex=p.exercise
            now=time.monotonic()
            seconds=(ex.phrase.end-ex.phrase.start)*60/p.bpm
            elapsed=now-self.run_at
            progress=min(1.0,max(0.0, elapsed/seconds)) if self.running else 0.0
            phase="count_in" if self.running and elapsed<0 else "playing" if self.running else "feedback" if self.pending_result is not None else "ready"
            return {"loaded":True,"title":p.piece.title,"kind":ex.kind,
                    "first_bar":ex.phrase.first_bar,"last_bar":ex.phrase.last_bar,
                    "exercise":p.index+1,"exercise_count":len(p.exercises),
                    "hand":p.hand,"hands":list(p.hands),"bpm":p.bpm,"original_bpm":p.piece.bpm,
                    "streak":p.streak,"mastered":len(p.mastered),"phase":phase,
                    "countdown":max(0,-elapsed) if self.running else 0,
                    "progress":progress,"duration":seconds,"beat":progress * (ex.phrase.end - ex.phrase.start),
                    "duration_beats":ex.phrase.end - ex.phrase.start,"running":self.running,
                    "device":self.midi_device,"feedback":self.feedback,"revision":self.score_revision,
                    "feedback_marks":self.feedback_marks if phase == "feedback" else [],
                    "feedback_unmapped":self.feedback_unmapped if phase == "feedback" else 0}

    def engraving(self) -> EngravedScore:
        with self.lock:
            if not self.plan:
                raise ValueError("No piece loaded")
            if self._layout_revision != self.score_revision or self._layout_cache is None:
                p=self.plan
                phrase=p.exercise.phrase
                self._layout_cache = render_layout(self.score,phrase.first_bar,phrase.last_bar,p.hand,
                                                   total_beats=phrase.end - phrase.start)
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
