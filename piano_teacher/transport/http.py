"""Loopback-only HTTP API adapter with no practice-state implementation.

PracticeEngine is supplied as Handler.engine by the application entry point.
The existing route names and response contract remain unchanged.
"""
from __future__ import annotations

import json
from typing import Any
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

class Handler(BaseHTTPRequestHandler):
    engine: Any
    def _reply(self, status: int, content: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(content)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(content)
    def _json(self, status, data):
        self._reply(status,json.dumps(data).encode(),"application/json")
    def _json_error(self, status: int, message: str) -> None:
        """A client may disconnect while the server prepares an error response."""
        try:
            self._json(status, {"error": message})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        try:
            route=urlsplit(self.path).path
            if route=="/state":
                self._json(200,self.engine.state())
            elif route=="/fingering":
                self._json(200,self.engine.fingering_status())
            elif route=="/library":
                self._json(200,self.engine.library_listing())
            elif route=="/library/health":
                self._json(200,self.engine.library_health_status())
            elif route=="/lesson":
                self._json(200,self.engine.lesson_overview())
            elif route=="/settings":
                self._json(200,self.engine.preferences())
            elif route=="/exercise/diagnostics":
                self._json(200,self.engine.exercise_diagnostics())
            elif route=="/devices":
                self._json(200,{"devices":self.engine.ports()})
            elif route=="/diagnostics/hardware":
                self._json(200,self.engine.hardware_diagnostics())
            elif route=="/diagnostics/performance":
                self._json(200,self.engine.performance_diagnostics())
            elif route=="/demo.wav":
                from urllib.parse import parse_qs
                token = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
                path = self.engine.demo_audio(token)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with path.open("rb") as audio_file:
                    while block := audio_file.read(65536):
                        self.wfile.write(block)
            elif route=="/score/layout":
                from urllib.parse import parse_qs
                native_option = parse_qs(urlsplit(self.path).query).get(
                    "native", ["1"])[0]
                if native_option not in ("0", "1"):
                    raise ValueError("native must be 1, or 0 for reference-only layout")
                native = native_option == "1"
                self._json(200,self.engine.geometry(native_notes=native))
            elif route=="/score/model":
                self._json(200,self.engine.semantic_score())
            elif route in ("/score.svg", "/score.png"):
                from urllib.parse import parse_qs
                query=parse_qs(urlsplit(self.path).query)
                page=int(query.get("page", ["0"])[0])
                if route=="/score.png":
                    if "width" in query:
                        width=int(query["width"][0])
                        self._reply(200,self.engine.engraved_png(page, width=width),"image/png")
                    else:
                        self._reply(200,self.engine.engraved_png(page),"image/png")
                else:
                    self._reply(200,self.engine.engraved(page).encode(),"image/svg+xml; charset=utf-8")
            else:
                self._json(404,{"error":"Not found"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Godot cancelled this request; the response socket is already gone.
            return
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            self._json_error(400, str(exc))
        except Exception as exc:
            # Unexpected backend errors should be visible as server failures,
            # not misreported to Godot as malformed client requests.
            import traceback
            traceback.print_exc()
            self._json_error(500, f"Piano Teacher could not complete this request: {exc}")

    def do_POST(self):
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length > 1_000_000:
                raise ValueError("Request too large")
            args=json.loads(self.rfile.read(length)) if length else {}
            route=urlsplit(self.path).path
            if not isinstance(args, dict):
                raise ValueError("Request must be a JSON object")
            if route=="/load":
                self.engine.load(args["path"])
            elif route=="/fingering":
                self.engine.correct_fingering(args["source_id"], args["finger"],
                                             fingerprint=args.get("fingerprint"))
            elif route=="/library/open":
                self.engine.load_library(args["id"])
            elif route=="/library/health":
                self._json(200, self.engine.start_library_health())
                return
            elif route=="/settings":
                self.engine.set_preferences(**args)
            elif route=="/device":
                self.engine.connect(args.get("name",""))
            elif route=="/diagnostics/hardware":
                self._json(200,self.engine.hardware_diagnostics_action(args.get("action","")))
                return
            elif route=="/control":
                self.engine.control(**args)
            elif route=="/midi/live/subscribe":
                self.engine.subscribe_midi_visual(args.get("port"))
                self._json(200, {"subscribed": True})
                return
            else:
                self._json(404,{"error":"Not found"})
                return
            self._json(200,self.engine.preferences() if route == "/settings" else self.engine.state())
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # The client already closed the socket; do not try another reply.
            return
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            self._json_error(400, str(exc))
        except Exception as exc:
            # Preserve diagnostics for genuine backend failures without making
            # a failed error-response write produce a second traceback.
            import traceback
            traceback.print_exc()
            self._json_error(500, f"Piano Teacher could not complete this request: {exc}")
    def log_message(self, format, *args):
        return


