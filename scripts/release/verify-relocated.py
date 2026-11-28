"""Exercise production MusicXML import, Listen render, persistence and MIDI discovery."""

import hashlib
import os
import sys
import tempfile
import wave
from pathlib import Path

from piano_teacher.application.midi_connection import MidiConnection
from piano_teacher.demo import DemoAudioCache
from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan
from piano_teacher.progress_repository import ProgressRepository

SCORE = b"""<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name>
</score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>
<time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><pitch><step>C</step>
<octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>"""


def verify(work):
    source = work / "Listen.musicxml"
    source.write_bytes(SCORE)
    plan = LearningPlan(import_piece(source))
    assert [n.pitch for n in plan.piece.notes] == [72]
    audio = DemoAudioCache(work / "audio", sample_rate=16000).render(plan.active_variant, 120)
    sampled = bool(os.environ.get("PIANO_TEACHER_SOUNDFONT"))
    with wave.open(str(audio.path)) as wav:
        assert wav.getnchannels() == (2 if sampled else 1)
        assert wav.getnframes() == audio.frame_count
        assert any(wav.readframes(wav.getnframes()))
    assert audio.instrument.endswith("(sampled)") == sampled
    key = hashlib.sha256(SCORE).hexdigest()
    db = work / "progress.db"
    repository = ProgressRepository(db)
    plan.bpm = 53
    repository.save(plan, key)
    repository.close()
    repository = ProgressRepository(db)
    restored = LearningPlan(import_piece(source))
    assert repository.restore(restored, key) and restored.bpm == 53
    repository.close()
    scan = MidiConnection().scan()
    # A headless Linux host may have no ALSA sequencer.
    if scan.error and (not isinstance(scan.error, RuntimeError) or "ALSA" not in str(scan.error)):
        raise scan.error
    print("RELOCATED_XML_AUDIO_PROGRESS_MIDI", audio.instrument, audio.frame_count,
          scan.feedback if scan.error else scan.names)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(dir=Path(sys.argv[1])) as scratch:
        verify(Path(scratch))
