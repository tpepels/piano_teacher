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
from .score import import_piece, render_measures


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
        self.last_score = ""
        self.next_at = 0.0
        self.midi_port = None
        self.midi_device = ""
        self.enable_midi = enable_midi
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

    def start(self):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            if self.enable_midi and self.midi_port is None:
                raise ValueError("Connect your USB MIDI piano first")
            self.running=True
            self.auto=True
            self.next_at=0
            self.recorder=Recorder()
            phrase=self.plan.exercise.phrase
            measures=max(1, phrase.last_bar - phrase.first_bar+1)
            count_in_beats=max(1,round((phrase.end-phrase.start)/measures))
            self.run_at=time.monotonic()+count_in_beats*60/self.plan.bpm
            self.feedback="Count in, then play"

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
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
        if self.next_at and now >= self.next_at:
            self.start()
        if not self.running or now < self.run_at:
            return
        phrase=self.plan.exercise.phrase
        duration=(phrase.end - phrase.start)*60/self.plan.bpm
        if now < self.run_at+duration+0.20:
            return
        result=evaluate(phrase,self.plan.hand,self.plan.bpm,self.recorder.presses if self.recorder else [])
        old_key=self.plan.identity
        old_index=self.plan.index
        old_hand=self.plan.hand
        info=self.plan.apply_result(correct=result.correct,total=len(result.notes),extras=result.extra_notes)
        self.feedback=result.summary+" - "+info
        self.running=False
        self.recorder=None
        self.score_revision+=int((old_index,old_hand)!=(self.plan.index,self.plan.hand))
        self._save()
        if self.auto and info!="Piece mastered":
            self.next_at=now+2
        else:
            self.auto=False
            self.next_at=0

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
            phase="count_in" if self.running and elapsed<0 else "playing" if self.running else "feedback" if self.next_at else "ready"
            return {"loaded":True,"title":p.piece.title,"kind":ex.kind,
                    "first_bar":ex.phrase.first_bar,"last_bar":ex.phrase.last_bar,
                    "exercise":p.index+1,"exercise_count":len(p.exercises),
                    "hand":p.hand,"hands":list(p.hands),"bpm":p.bpm,"original_bpm":p.piece.bpm,
                    "streak":p.streak,"mastered":len(p.mastered),"phase":phase,
                    "countdown":max(0,-elapsed) if self.running else 0,
                    "progress":progress,"duration":seconds,"running":self.running,
                    "device":self.midi_device,"feedback":self.feedback,"revision":self.score_revision}

    def engraved(self) -> str:
        with self.lock:
            if not self.plan:
                raise ValueError("No piece loaded")
            p=self.plan
            return render_measures(self.score,p.exercise.phrase.first_bar,p.exercise.phrase.last_bar,p.hand)


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
            elif route=="/devices":
                self._json(200,{"devices":self.engine.ports()})
            elif route=="/score.svg":
                self._reply(200,self.engine.engraved().encode(),"image/svg+xml; charset=utf-8")
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
            elif route=="/device":
                self.engine.connect(args.get("name",""))
            elif route=="/control":
                self.engine.control(**args)
            else:
                self._json(404,{"error":"Not found"})
                return
            self._json(200,self.engine.state())
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
