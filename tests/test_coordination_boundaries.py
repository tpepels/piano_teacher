"""Keep backend progression and Godot presentation at explicit boundaries.

These source-only tests are deliberately fast. The headless test runs only
when Godot is available and cannot certify physical MIDI latency.
"""
from pathlib import Path
import ast
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_attempt_progression_uses_explicit_inputs_and_returns_decisions():
    server = (ROOT/"piano_teacher/server.py").read_text()
    tree = ast.parse(server)
    engine = next(node for node in tree.body
                  if isinstance(node,ast.ClassDef) and node.name=="PracticeEngine")
    methods = {node.name: ast.get_source_segment(server,node)
               for node in engine.body if isinstance(node,ast.FunctionDef)}
    assert "self.attempt_progression.schedule_start(" in methods["start"]
    assert "self.attempt_progression.inspect(AttemptTick(" in methods["_update"]
    assert "self._run_pre_assessment_transition(now)" in methods["_update"]
    assert "_apply_rolling_recovery(" in methods["_update"]
    assert "_complete_attempt(" in methods["_update"]
    policy = (ROOT/"piano_teacher/application/attempt_progression.py").read_text()
    assert "class AttemptTick:" in policy
    assert "class AttemptStart:" in policy
    assert "class AttemptStep:" in policy
    assert "def schedule_start(" in policy
    assert "def inspect(" in policy
    assert "engine." not in policy
    assert "PracticeEngine" not in policy.split('"""',2)[-1]


def test_main_callbacks_keep_reply_handling_and_presentation_separate():
    main = (ROOT / "godot/main.gd").read_text()
    process = main.split("func _process(",1)[1].split("\nfunc ",1)[0]
    state = main.split("func _on_state(",1)[1].split("\nfunc ",1)[0]
    frame = (ROOT / "godot/practice_frame_coordinator.gd").read_text()
    presenter = (ROOT / "godot/practice_state_presenter.gd").read_text()
    assert "frame_coordinator.advance(" in process
    assert "_transport_beat_at(ticks)" in process
    assert "_update_count_in(beat,ticks)" in process
    assert "state_presenter.present(" in state
    assert "visual_transport_clock.accept(parsed,last_state_tick,received_ms)" in state
    assert "score_session.update_context(parsed,received_ms)" in state
    assert "renderer.present_clock(beat,visual_beat)" in frame
    assert "renderer.present(" not in frame
    assert "stage.renderer.present(" in state
    assert "app." not in frame
    assert "app." not in presenter
    assert "func _init(practice, settings, lesson, session," in frame
    assert "func _init(practice, settings, lesson, session," in presenter
    assert "visual_transport_clock" not in presenter
    assert "score_session" not in presenter
    base = (ROOT / "godot/notation/shared/view_base.gd").read_text()
    clock = base.split("func present_clock(",1)[1].split("\nfunc ",1)[0]
    assert "queue_redraw()" in clock
    assert "duplicate(true)" not in clock


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_single_clock_sample_reaches_visual_consumers():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/practice_frame_coordinator.gd")],
        capture_output=True, text=True, timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "PRACTICE_FRAME_COORDINATOR_FAILURES:0" in output, output


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_state_presenter_receives_only_visual_collaborators():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary,"--headless","--path",str(ROOT/"godot"),
         "--script",str(ROOT/"tests/godot/practice_state_presenter.gd")],
        capture_output=True,text=True,timeout=20)
    output = run.stdout+run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "PRACTICE_STATE_PRESENTER_FAILURES:0" in output, output


def test_preview_particle_ownership_is_not_in_application_root():
    main = (ROOT/"godot/main.gd").read_text()
    effects = (ROOT/"godot/score_effects.gd").read_text()
    assert "score_effects.record_preview(" in main
    assert "score_effects.transition_mode(" in main
    assert "func _preview_note_arrivals(" not in main
    assert "func _clear_assessed_effects_in_ungraded_mode(" not in main
    assert "func record_preview(" in effects
    assert "func transition_mode(" in effects


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_score_effects_owner_visual_contract():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary,"--headless","--path",str(ROOT/"godot"),
         "--script",str(ROOT/"tests/godot/score_effects_owner.gd")],
        capture_output=True,text=True,timeout=20)
    output = run.stdout+run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "SCORE_EFFECTS_OWNER_FAILURES:0" in output, output


def test_snapshot_assembly_and_live_hit_mapping_have_one_owner():
    server = (ROOT / "piano_teacher/server.py").read_text()
    assert "return capture_session_snapshot(values, reads)" in server
    assert "SnapshotValues(" in server and "SnapshotReadPorts(" in server
    assert "ActivitySnapshot(" not in server
    assert "TimingSnapshot(" not in server
    builder = (ROOT / "piano_teacher/application/session_snapshot_builder.py").read_text()
    assert "ActivitySnapshot(" in builder and "TimingSnapshot(" in builder
    assert "return SessionSnapshot(" in builder
    assert "def capture(state: SnapshotValues, reads: SnapshotReadPorts)" in builder
    assert "engine." not in builder
    assert "state.midi." not in builder

    main = (ROOT / "godot/main.gd").read_text()
    handler = main.split("func _consume_live_piano_hits(", 1)[1].split(
        "\nfunc ", 1)[0]
    assert "live_midi_feedback.consume(" in handler
    assert "for note in notes:" not in handler
    assert "live_midi_feedback.bind_layout(values, _published_revision)" in main
    index = (ROOT / "godot/live_midi_feedback.gd").read_text()
    assert "note_by_id[str(note.get(" in index
    assert "note_by_id.get(note_id, {})" in index


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_live_midi_hits_use_revision_bound_score_index():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/live_midi_feedback.gd")],
        capture_output=True, text=True, timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "LIVE_MIDI_FEEDBACK_FAILURES:0" in output, output


def test_command_error_publication_has_injected_screen_dependencies():
    main = (ROOT / "godot/main.gd").read_text()
    presenter = (ROOT / "godot/command_failure_presenter.gd").read_text()
    handler = main.split("func _on_action(", 1)[1].split("\nfunc ", 1)[0]
    assert "command_failure_presenter.present(message,path,queued_library_failed)" in handler
    assert "CommandFailurePresenter.new(" in main
    assert "func _init(library, practice, settings, home)" in presenter
    assert "app." not in presenter
    assert "request(" not in presenter


def test_navigation_pause_decision_has_explicit_inputs():
    main = (ROOT / "godot/main.gd").read_text()
    policy = (ROOT / "godot/navigation_policy.gd").read_text()
    assert "NavigationPolicy.plan(" in main
    assert 'if bool(decision["pause"]):' in main
    assert "func _navigate(" not in policy
    assert "app." not in policy
    assert "get_tree()" not in policy


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
@pytest.mark.parametrize(("script", "success"), [
    ("command_failure_presenter", "COMMAND_FAILURE_PRESENTER_FAILURES:0"),
    ("navigation_policy", "NAVIGATION_POLICY_FAILURES:0"),
])
def test_pure_frontend_policy_with_headless_godot(script, success):
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests" / "godot" / (script + ".gd"))],
        capture_output=True, text=True, timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert success in output, output


def test_completed_take_owns_only_transport_and_session_persistence():
    server = (ROOT/"piano_teacher/server.py").read_text()
    assessment = (ROOT/"piano_teacher/application/assessment_settlement.py").read_text()
    evidence = (ROOT/"piano_teacher/application/assessment_evidence.py").read_text()
    commit = (ROOT/"piano_teacher/application/assessment_commit.py").read_text()
    assert "assess_completed_take(" in server
    assert "commit_assessed_result(" in server
    assert "def assess_completed_take(" in assessment
    assert "def observe_assessed_take(" in evidence
    assert "def commit_assessed_result(" in commit
    assert "observe_assessed_take(" in commit
    assert commit.index("observe_assessed_take(") < commit.index("message = plan.apply_result(")
    for source in (assessment, evidence, commit):
        assert "engine." not in source
        assert "PracticeEngine" not in source

def test_teaching_selection_and_preparation_are_learner_owned():
    server = (ROOT/"piano_teacher/server.py").read_text()
    learner = (ROOT/"piano_teacher/application/learner_progress.py").read_text()
    assert "self.learner_progress.next_course_unit(" in server
    assert "self.learner_progress.record_guided_preparation(" in server
    assert "def next_course_unit(" in learner
    assert "def record_guided_preparation(" in learner


def test_successful_command_route_has_no_application_dependency():
    main = (ROOT/"godot/main.gd").read_text()
    policy = (ROOT/"godot/command_success_policy.gd").read_text()
    response = main.split("func _on_action(",1)[1].split("\nfunc ",1)[0]
    assert "CommandSuccessPolicy.decide(" in response
    assert "NavigationPolicy.plan(" in main
    assert "static func decide(" in policy
    assert "app." not in policy
    assert "request(" not in policy


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_successful_command_decisions_headless():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary,"--headless","--path",str(ROOT/"godot"),
         "--script",str(ROOT/"tests/godot/command_success_policy.gd")],
        capture_output=True,text=True,timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "COMMAND_SUCCESS_POLICY_FAILURES:0" in output, output


def test_transition_selection_and_guidance_own_narrow_inputs():
    server = (ROOT/"piano_teacher/server.py").read_text()
    transitions = (ROOT/"piano_teacher/application/practice_transitions.py").read_text()
    guided = (ROOT/"piano_teacher/application/guided_session.py").read_text()
    assert "decide_transition(" in server
    assert "TransitionContext(" in server
    assert "def decide_transition(context: TransitionContext" in transitions
    assert "engine." not in transitions
    assert "run_before_assessment(" not in transitions
    assert "self.guided_session.advance(" in server
    assert "self.guided_session.bind(" in server
    assert "self.guided_session.commit_completed_preparation(" in server
    assert "self.guided_session.marks(" in server
    assert "engine." not in guided


def test_successful_command_view_effects_have_injected_dependencies():
    main = (ROOT/"godot/main.gd").read_text()
    presenter = (ROOT/"godot/command_success_presenter.gd").read_text()
    assert "CommandSuccessPresenter.new(" in main
    assert "command_success_presenter.present_accepted(decision)" in main
    assert "command_success_presenter.present_source_picker(opened)" in main
    assert "lesson_session.invalidate()" not in main.split(
        "func _on_action(", 1)[1].split("\nfunc ", 1)[0]
    assert "func _init(library, practice, settings, lesson)" in presenter
    assert "app." not in presenter
    assert "request(" not in presenter


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_successful_command_view_effects_headless():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary,"--headless","--path",str(ROOT/"godot"),
         "--script",str(ROOT/"tests/godot/command_success_presenter.gd")],
        capture_output=True,text=True,timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "COMMAND_SUCCESS_PRESENTER_FAILURES:0" in output, output
