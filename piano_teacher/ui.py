"""Deliberately sparse Qt piano-roll user interface."""
from __future__ import annotations

import math
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer, QRectF, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget, QSizePolicy,
)

from .midi_input import MidiInput

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # Can still be used with a visual count-in.
    QSoundEffect = None


def make_click() -> str:
    """Generate a short PCM metronome tick without an external audio file."""
    path = str(Path(tempfile.gettempdir()) / "piano_teacher_click.wav")
    if Path(path).exists():
        return path
    rate, count = 22050, 1102
    samples = bytearray()
    for i in range(count):
        envelope = math.exp(-i / 240)
        amplitude = int(12000 * envelope * math.sin(2 * math.pi * 1000 * i / rate))
        samples.extend(struct.pack('<h', amplitude))
    with wave.open(path, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples)
    return path
from .music import Piece, Phrase, load_midi, note_name
from .practice import Assessment, Curriculum, Recorder, evaluate

BG = "#10151b"
PANEL = "#182129"
INK = "#e8edf0"
SOFT = "#8999a6"
GRID = "#30404b"
NOTE = "#91c7c1"
GOOD = "#5dbe98"
BAD = "#da786e"


class Roll(QWidget):
    """Static note blocks, scrolling *playhead only*, readable pitch and beat grid."""

    def __init__(self) -> None:
        super().__init__()
        self.phrase: Phrase | None = None
        self.hand = "right"
        self.progress = 0.0
        self.countdown = ""
        self.assessment: Assessment | None = None
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_passage(self, phrase: Phrase, hand: str) -> None:
        self.phrase = phrase
        self.hand = hand
        self.progress = 0.0
        self.countdown = ""
        self.assessment = None
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(PANEL))
        p.setPen(QColor(SOFT))
        if self.phrase is None:
            p.setFont(QFont("Sans Serif", 16))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open a MIDI file to begin")
            return
        phrase = self.phrase
        notes = [n for n in phrase.notes if self.hand == "both" or n.hand == self.hand]
        if not notes:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No notes in this hand")
            return
        x0, right = 74, self.width() - 24
        y0, bottom = 68, self.height() - 44
        width, height = max(1, right - x0), max(1, bottom - y0)
        low = min(n.pitch for n in notes) - 2
        high = max(n.pitch for n in notes) + 2
        if high - low < 12:
            pad = (12 - (high - low)) // 2
            low -= pad
            high += 12 - (high - low) - pad
        pitch_step = height / (high - low + 1)
        beat_span = max(0.01, phrase.end - phrase.start)

        def note_y(pitch: int) -> float:
            return y0 + (high - pitch) * pitch_step

        p.setFont(QFont("Sans Serif", 10))
        p.setPen(QColor(SOFT))
        p.drawText(x0, 33, f"BARS {phrase.first_bar}–{phrase.last_bar}  ·  {self.hand.upper()} HAND")
        p.drawText(right - 180, 33, "PLAY THE SHAPES")
        for pitch in range(low, high + 1):
            y = note_y(pitch) + pitch_step / 2
            is_c = pitch % 12 == 0
            p.setPen(QPen(QColor("#364754" if is_c else "#24313b"), 1))
            p.drawLine(x0, int(y), right, int(y))
            if is_c or pitch in {n.pitch for n in notes}:
                p.setPen(QColor(SOFT))
                p.setFont(QFont("Sans Serif", 9))
                p.drawText(10, int(note_y(pitch) + pitch_step * .70), note_name(pitch))
        p.setPen(QPen(QColor(GRID), 1))
        for beat in range(math.ceil(beat_span) + 1):
            x = x0 + width * (beat / beat_span)
            if x > right + 1:
                continue
            p.drawLine(int(x), y0, int(x), bottom)
            p.setPen(QColor(SOFT))
            p.drawText(int(x) + 3, bottom + 21, str(beat + 1))
            p.setPen(QPen(QColor(GRID), 1))
        statuses = {a.note: a.status for a in self.assessment.notes} if self.assessment else {}
        for n in notes:
            x = x0 + width * ((n.start - phrase.start) / beat_span)
            end_x = x0 + width * ((min(n.end, phrase.end) - phrase.start) / beat_span)
            note_width = max(3.0, end_x - x)
            y = note_y(n.pitch)
            status = statuses.get(n)
            color = GOOD if status == "correct" else BAD if status else NOTE
            rect = QRectF(x, y + 1.5, note_width, max(4.0, pitch_step - 3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(rect, 3, 3)
            if rect.width() >= 32 and rect.height() >= 14:
                p.setPen(QColor("#0d2427"))
                p.setFont(QFont("Sans Serif", max(8, min(12, int(pitch_step * .5))), QFont.Weight.DemiBold))
                p.drawText(rect.adjusted(5, 0, -3, 0), Qt.AlignmentFlag.AlignVCenter, note_name(n.pitch))
        play_x = x0 + width * min(1, max(0, self.progress))
        p.setPen(QPen(QColor("#faf6e7"), 2.5))
        p.drawLine(int(play_x), y0 - 8, int(play_x), bottom + 3)
        if self.countdown:
            p.fillRect(QRectF(x0, y0, width, height), QColor(15, 22, 29, 170))
            p.setPen(QColor(INK))
            p.setFont(QFont("Sans Serif", 48, QFont.Weight.Bold))
            p.drawText(QRectF(x0, y0, width, height), Qt.AlignmentFlag.AlignCenter, self.countdown)
        p.end()


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Piano Teacher")
        self.setMinimumSize(790, 510)
        self.resize(1100, 680)
        self.settings = QSettings("PianoTeacher", "PianoTeacher")
        self.midi = MidiInput()
        self.midi.note.connect(self.received_note)
        self.session: Curriculum | None = None
        self.recorder: Recorder | None = None
        self.start_at = 0.0
        self.running = False
        self.result_visible = False
        self.generation = 0
        self.count_in = 4
        self.last_beat: int | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.click = None
        if QSoundEffect is not None:
            self.click = QSoundEffect(self)
            self.click.setSource(QUrl.fromLocalFile(make_click()))
            self.click.setVolume(0.35)

        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        top = QHBoxLayout()
        self.title = QLabel("PIANO TEACHER")
        self.title.setObjectName("title")
        top.addWidget(self.title, 1)
        open_button = QPushButton("Open MIDI…")
        open_button.clicked.connect(self.open_file)
        top.addWidget(open_button)
        layout.addLayout(top)

        self.caption = QLabel("Choose a MIDI file, then connect your piano.")
        self.caption.setObjectName("caption")
        layout.addWidget(self.caption)
        self.roll = Roll()
        layout.addWidget(self.roll, 1)

        progress = QHBoxLayout()
        self.progress_label = QLabel("No passage")
        self.progress_label.setObjectName("progress")
        progress.addWidget(self.progress_label, 1)
        self.feedback = QLabel(" ")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress.addWidget(self.feedback, 2)
        layout.addLayout(progress)

        controls = QHBoxLayout()
        self.prev = QPushButton("← Previous")
        self.prev.clicked.connect(lambda: self.jump(-1))
        controls.addWidget(self.prev)
        self.play = QPushButton("Start   Space")
        self.play.setObjectName("primary")
        self.play.clicked.connect(self.toggle)
        controls.addWidget(self.play)
        self.next = QPushButton("Next →")
        self.next.clicked.connect(lambda: self.jump(1))
        controls.addWidget(self.next)
        controls.addStretch(1)
        controls.addWidget(QLabel("Hand"))
        self.hand = QComboBox()
        self.hand.currentIndexChanged.connect(self.change_hand)
        controls.addWidget(self.hand)
        controls.addWidget(QLabel("BPM"))
        self.tempo = QSpinBox()
        self.tempo.setRange(20, 300)
        self.tempo.setFixedWidth(74)
        self.tempo.valueChanged.connect(self.change_tempo)
        controls.addWidget(self.tempo)
        layout.addLayout(controls)

        midi_row = QHBoxLayout()
        midi_row.addWidget(QLabel("MIDI INPUT"))
        self.ports = QComboBox()
        self.ports.setMinimumWidth(210)
        self.ports.currentIndexChanged.connect(self.connect_port)
        midi_row.addWidget(self.ports, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        midi_row.addWidget(refresh)
        self.input_status = QLabel("No device connected")
        self.input_status.setObjectName("caption")
        midi_row.addWidget(self.input_status)
        self.click_check = QCheckBox("Click")
        self.click_check.setChecked(self.click is not None)
        self.click_check.setEnabled(self.click is not None)
        midi_row.addWidget(self.click_check)
        layout.addLayout(midi_row)

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {BG}; color: {INK}; font: 14px 'Sans Serif'; }}
            QWidget {{ selection-background-color: #487a79; }}
            QLabel#title {{ font-size: 22px; font-weight: 700; letter-spacing: 2px; }}
            QLabel#caption {{ color: {SOFT}; font-size: 13px; }}
            QLabel#progress {{ font-weight: 600; }}
            QPushButton, QComboBox, QSpinBox {{ border: 1px solid #3b4b56; border-radius: 7px;
                background: #202a33; padding: 9px 12px; min-height: 19px; }}
            QPushButton:hover {{ background: #2b3942; }}
            QPushButton#primary {{ background: {NOTE}; color: #102327; font-weight: 700; border: none; }}
            QPushButton#primary:hover {{ background: #addbd5; }}
            QPushButton:disabled {{ color: #65737c; background: #182129; }}
            QComboBox QAbstractItemView {{ background: #26333e; color: white; }}
        """)
        self.refresh_ports()
        self.render_state()

    def refresh_ports(self) -> None:
        old = self.ports.currentData()
        self.ports.blockSignals(True)
        self.ports.clear()
        try:
            names = self.midi.ports()
        except Exception as exc:
            names = []
            self.input_status.setText(f"MIDI unavailable: {exc}")
        for name in names:
            self.ports.addItem(name, name)
        if not names:
            self.ports.addItem("No MIDI ports found", "")
            self.midi.close()
            self.input_status.setText("Connect a USB MIDI piano, then Refresh")
        else:
            match = self.ports.findData(old)
            self.ports.setCurrentIndex(max(0, match))
        self.ports.blockSignals(False)
        if names:
            self.connect_port()
        self.render_state()

    def connect_port(self, _index: int = -1) -> None:
        name = self.ports.currentData() or ""
        try:
            self.midi.connect(name)
            self.input_status.setText("Connected" if name else "Not connected")
        except Exception as exc:
            self.input_status.setText(f"Cannot open MIDI input: {exc}")
        self.stop()
        self.render_state()

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose MIDI", self.settings.value("last_dir", str(Path.home())),
            "MIDI files (*.mid *.midi);;All files (*)")
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        self.stop()
        try:
            piece = load_midi(path)
            self.session = Curriculum(piece)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot load MIDI", str(exc))
            return
        self.settings.setValue("last_dir", str(Path(path).parent))
        self.feedback.setText("Two clean plays advance the tempo automatically")
        self.render_state()

    def render_state(self) -> None:
        s = self.session
        enabled = s is not None
        self.prev.setEnabled(enabled and s.phrase_index > 0)
        self.next.setEnabled(enabled and s.phrase_index < len(s.piece.phrases) - 1)
        self.play.setEnabled(enabled and self.midi.port is not None)
        self.play.setText("Stop   Space" if self.running else "Start   Space")
        self.hand.blockSignals(True)
        self.tempo.blockSignals(True)
        self.hand.clear()
        if s:
            self.title.setText(s.piece.title)
            self.caption.setText(f"{s.piece.bpm} BPM original  ·  two bars per passage  ·  right → left → both")
            self.progress_label.setText(f"PASSAGE {s.phrase_index + 1} / {len(s.piece.phrases)}")
            for phase in s.phases:
                self.hand.addItem(phase.title(), phase)
            self.hand.setCurrentIndex(s.phase_index)
            self.tempo.setValue(s.bpm)
            if not self.result_visible and (self.roll.phrase is not s.phrase or self.roll.hand != s.hand):
                self.roll.set_passage(s.phrase, s.hand)
        else:
            self.title.setText("PIANO TEACHER")
            self.progress_label.setText("No passage")
            self.tempo.setValue(60)
        self.hand.setEnabled(enabled)
        self.tempo.setEnabled(enabled)
        self.hand.blockSignals(False)
        self.tempo.blockSignals(False)

    def change_hand(self, index: int) -> None:
        if not self.session or index < 0:
            return
        self.stop()
        self.session.phase_index = index
        self.session.clean_streak = 0
        self.session.bpm = self.session.start_bpm
        self.roll.set_passage(self.session.phrase, self.session.hand)
        self.render_state()

    def change_tempo(self, value: int) -> None:
        if self.session:
            self.stop()
            self.session.bpm = value
            self.session.clean_streak = 0
            self.render_state()

    def jump(self, offset: int) -> None:
        if self.session:
            self.stop()
            self.session.jump(offset)
            self.roll.set_passage(self.session.phrase, self.session.hand)
            self.feedback.setText(" ")
            self.render_state()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self.play.isEnabled():
                self.toggle()
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self.jump(1)
        elif event.key() == Qt.Key.Key_Left:
            self.jump(-1)
        else:
            super().keyPressEvent(event)

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.begin()
        self.render_state()

    def begin(self) -> None:
        if not self.session or self.midi.port is None:
            return
        self.stop()
        s = self.session
        self.recorder = Recorder()
        # The average measure length is appropriate for 3/4 and 6/8 too.
        self.count_in = max(1, round((s.phrase.end - s.phrase.start) /
                                      (s.phrase.last_bar - s.phrase.first_bar + 1)))
        beat_seconds = 60.0 / s.bpm
        self.start_at = time.monotonic() + self.count_in * beat_seconds
        self.running = True
        self.result_visible = False
        self.roll.assessment = None
        self.roll.progress = 0.0
        self.roll.countdown = str(self.count_in)
        self.last_beat = None
        self.feedback.setText("Count in, then play")
        self.timer.start()

    def received_note(self, pitch: int, is_on: bool, timestamp: float) -> None:
        if self.running and self.recorder:
            self.recorder.add(pitch, is_on, timestamp - self.start_at)

    def tick(self) -> None:
        if not self.running or not self.session:
            return
        s = self.session
        beat_seconds = 60.0 / s.bpm
        elapsed = time.monotonic() - self.start_at
        self.roll.progress = elapsed / ((s.phrase.end - s.phrase.start) * beat_seconds)
        beat_number = math.floor(elapsed / beat_seconds)
        if beat_number != self.last_beat:
            self.last_beat = beat_number
            if self.click and self.click_check.isChecked():
                self.click.play()
        if elapsed < 0:
            self.roll.countdown = str(max(1, math.ceil(-elapsed / beat_seconds)))
        else:
            self.roll.countdown = ""
        self.roll.update()
        passage_seconds = (s.phrase.end - s.phrase.start) * beat_seconds
        if elapsed >= passage_seconds + max(.3, .28 * beat_seconds):
            result = evaluate(s.phrase, s.hand, s.bpm, self.recorder.presses if self.recorder else [])
            self.stop(clear_visual=False)
            self.result_visible = True
            self.roll.assessment = result
            self.roll.progress = 1.0
            self.roll.update()
            message = s.completed(result)
            self.feedback.setText(f"{result.summary}  ·  {message}")
            self.render_state()
            if not message.startswith("Piece complete"):
                generation = self.generation
                QTimer.singleShot(1900, lambda: self.retry_if_current(generation))

    def retry_if_current(self, generation: int) -> None:
        if self.generation != generation or self.running or not self.session:
            return
        self.result_visible = False
        self.roll.set_passage(self.session.phrase, self.session.hand)
        self.begin()
        self.render_state()

    def stop(self, *, clear_visual: bool = True) -> None:
        self.generation += 1
        self.timer.stop()
        self.running = False
        self.recorder = None
        if clear_visual:
            self.result_visible = False
            self.roll.assessment = None
            self.roll.countdown = ""
            self.roll.progress = 0.0
            self.roll.update()
        self.play.setText("Start   Space")

    def closeEvent(self, event) -> None:
        self.stop()
        self.midi.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Piano Teacher")
    window = Window()
    if len(sys.argv) > 1:
        window.load(sys.argv[1])
    window.show()
    sys.exit(app.exec())

