#!/usr/bin/env python3
"""Verify imported MIDI -> generated exercise -> Verovio glyphs -> PNG."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from piano_teacher.score import import_piece, render_layout
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.raster import rasterize_score


def check(path: Path, output_dir: Path | None = None) -> None:
    piece,_=import_piece(path)
    plan=LearningPlan(piece)
    print(f"Song: {piece.title}; {len(piece.notes)} source notes; {len(plan.exercises)} passages")
    for i,stage in enumerate(plan.variants):
        notation=build_lesson_score(stage.phrase)
        engraving=render_layout(notation,stage.phrase.first_bar,stage.phrase.last_bar,
                                 plan.hand,total_beats=stage.phrase.end-stage.phrase.start)
        require_lesson_alignment(stage.phrase,engraving.layout,plan.hand)
        image=rasterize_score(engraving.pages[0])
        if output_dir:
            output_dir.mkdir(parents=True,exist_ok=True)
            (output_dir/f"level-{i+1}-{stage.level}.png").write_bytes(image)
        print(f"PASS {stage.level}: {len(stage.notes)} required notes, "
              f"{len(engraving.layout['notes'])} positioned notes, "
              f"{len(engraving.pages)} page(s), {len(image)} PNG bytes")
    print("GENERATED LESSON ENGRAVING PASSED")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("music_file",type=Path)
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args()
    try:
        check(args.music_file,args.output_dir)
    except Exception as exc:
        print(f"GENERATED LESSON FAILED: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
