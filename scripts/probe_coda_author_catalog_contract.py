"""Verify the published *excerpt catalog* against pinned original Coda source.

This does not claim note-level MusicXML parity or an automatic curriculum:
the author exposes only caller-selected measure ranges and exercise categories.
"""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path

from piano_teacher.research.coda_author_catalog import (
    AUTHOR_CATEGORIES, AUTHOR_REVISION, AUTHOR_DOTTED_PATTERNS,
    AUTHOR_SLOWDOWN_FACTORS, catalog_requests,
)


def node_named(nodes, name):
    return next(n for n in nodes if getattr(n, "name", None)==name)


def assignment_value(body, name):
    for n in ast.walk(ast.Module(body=body,type_ignores=[])):
        if isinstance(n,(ast.Assign,ast.AnnAssign)):
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            if any(isinstance(t,ast.Name) and t.id==name for t in targets):
                return n.value
    raise AssertionError(f"Author removed {name}")


def verify_pinned_source(folder: Path) -> dict:
    exercise=ast.parse((folder/"music/exercise.py").read_text())
    endpoint=ast.parse((folder/"api/endpoints.py").read_text())
    models=ast.parse((folder/"api/models.py").read_text())

    category_fn=node_named(exercise.body,"get_all_exercises")
    strings={n.value for n in ast.walk(category_fn)
             if isinstance(n,ast.Constant) and isinstance(n.value,str)}
    assert {"Score Level","Part Level","Voice Level: Original","Voice Level: " } <= strings
    descriptions=ast.literal_eval(assignment_value(exercise.body,"MOD_EXERCISE_DESCRIPTIONS"))
    assert set(descriptions)=={"dotted","chordified","slowed_down"}
    categories=("Score Level","Part Level","Voice Level: Original",
                *(f"Voice Level: {key.replace('_',' ').title()}"
                  for key in descriptions))
    assert tuple(categories)==AUTHOR_CATEGORIES

    cls=node_named(exercise.body,"ExerciseLine")
    generate=node_named(cls.body,"generate_exercises")
    patterns=ast.literal_eval(assignment_value(generate.body,"dotted_duration_patterns"))
    factors=ast.literal_eval(assignment_value(generate.body,"factor_of_slowdown"))
    assert tuple(tuple(x) for x in patterns)==AUTHOR_DOTTED_PATTERNS
    assert tuple(factors)==AUTHOR_SLOWDOWN_FACTORS

    # Source formula is code, not a documented preference. Check each
    # operator and variable with the pinned expression through a small
    # controlled test namespace, not by copying our implementation.
    formula=assignment_value(generate.body,"level_of_chordification")
    class Object:
        pass
    self=Object()
    self.music_matrix_representation=Object()
    r=self.music_matrix_representation
    r.quantization=4
    r.time_signature=Object()
    r.time_signature.numerator=4
    r.time_signature.denominator=4
    original=eval(compile(ast.Expression(formula),"<pinned author>", "eval"),
                  {"__builtins__":{"set":set}},{"self":self})
    actual={x.parameter for x in catalog_requests(4,4,4)
            if x.category=="Voice Level: Chordified"}
    assert original==actual

    # There is no algorithm that chooses the excerpt/learning sequence:
    # GenerateRequest requires explicit bounds, and /generate calls
    # get_all_exercises for exactly that caller-selected excerpt.
    request=node_named(models.body,"GenerateRequest")
    fields={n.target.id for n in request.body if isinstance(n,ast.AnnAssign)}
    assert {"filename","start_measure","end_measure"}<=fields
    endpoint_fn=node_named(endpoint.body,"generate_exercises")
    calls=[n for n in ast.walk(endpoint_fn) if isinstance(n,ast.Call)]
    args={n.func.id:[ast.unparse(arg) for arg in n.args] for n in calls
          if isinstance(n.func,ast.Name) and n.func.id in {
              "get_music21_score_notation","get_all_exercises"}}
    assert args["get_music21_score_notation"]==[
        "data.filename","data.start_measure","data.end_measure"]
    assert args["get_all_exercises"]==["score_excerpt"]
    returns=[n for n in ast.walk(endpoint_fn) if isinstance(n,ast.Return)]
    assert len(returns)==1
    keys=set(ast.literal_eval(k) for k in returns[0].value.keys)
    assert keys=={"exercises","start_measure","end_measure"}

    return {
        "original_revision":AUTHOR_REVISION,
        "endpoint":"/generate",
        "excerpt_selection":"explicit start_measure/end_measure by caller",
        "automatic_lesson_selection":False,
        "automatic_lesson_progression":False,
        "categories":list(categories),
        "dotted_patterns":patterns,
        "slowdown_factors":factors,
        "chord_widths_for_q4_4_4":sorted(original),
        "parity_scope":"catalog schema and operation parameters, not generated notes",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream",required=True,type=Path)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    proof=verify_pinned_source(args.upstream)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
    print(json.dumps(proof,sort_keys=True))


if __name__=="__main__":
    main()
