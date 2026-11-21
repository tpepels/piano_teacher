"""Selection-side cursor; not the live musical transport clock."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class LessonCursor:
    opening_beat: float = 0.0
    course_guided: bool = False

    def select_opening(self, beat: float) -> None:
        self.opening_beat = beat

    def set_course_guided(self, guided: bool) -> None:
        self.course_guided = guided
