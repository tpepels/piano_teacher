#!/usr/bin/env bash
# Automatic push CI only: cheap Python contracts with a hard deadline.
# No Godot rasterization, full notation corpus, ONNX, or model installation.
# Broader scenarios belong to explicit-only scripts/ci-extended.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python}"
"$PYTHON" -m compileall -q piano_teacher tests scripts
find scripts -type f -name '*.sh' -print0 | xargs -0 -r bash -n
# Focused, self-contained MIDI and state/assessment contracts.
timeout 25s "$PYTHON" -m pytest -q \
  tests/test_practice_warning_policy.py \
  tests/test_live_input_index.py \
  tests/test_engine_command_errors.py \
  tests/test_library_api.py \
  tests/test_frontend_startup.py \
  tests/test_phase0_smoke.py \
  tests/test_transport_projection.py \
  tests/test_inprocess_dispatcher.py \
  tests/test_inprocess_artifact_install.py \
  tests/test_inprocess_transport_structure.py \
  tests/test_godot_preload_paths.py \
  tests/test_coordination_boundaries.py::test_attempt_progression_uses_explicit_inputs_and_returns_decisions \
  tests/test_coordination_boundaries.py::test_main_callbacks_keep_reply_handling_and_presentation_separate \
  tests/test_tempo_map_cache.py \
  tests/test_feedback_route.py \
  tests/test_guided_fragment.py \
  tests/test_assessment_settlement.py \
  tests/test_assessment_evidence.py \
  tests/test_assessment_commit.py \
  tests/test_control_routing.py \
  tests/test_control_engine_routes.py \
  tests/test_score_ack.py \
  tests/test_course_navigation.py \
  tests/test_coordination_boundaries.py::test_success_effects_keep_ordering_without_main_access \
  tests/test_stage_change.py \
  tests/test_coordination_boundaries.py::test_control_dispatch_is_pure_and_domain_effects_are_locked \
  tests/test_coordination_boundaries.py::test_command_request_owner_has_no_scene_or_application_dependencies \
  tests/test_coordination_boundaries.py::test_learner_navigation_validates_before_transport_changes \
  tests/test_practice_transitions.py \
  tests/test_guided_session.py \
  tests/test_coordination_boundaries.py::test_transition_selection_and_guidance_own_narrow_inputs \
  tests/test_coordination_boundaries.py::test_successful_command_view_effects_have_injected_dependencies \
  tests/test_learner_progress_coordination.py \
  tests/test_coordination_boundaries.py::test_snapshot_assembly_and_live_hit_mapping_have_one_owner \
  tests/test_coordination_boundaries.py::test_command_error_publication_has_injected_screen_dependencies \
  tests/test_coordination_boundaries.py::test_completed_take_owns_only_transport_and_session_persistence \
  tests/test_coordination_boundaries.py::test_teaching_selection_and_preparation_are_learner_owned \
  tests/test_coordination_boundaries.py::test_successful_command_route_has_no_application_dependency \
  tests/test_attempt_progression.py::test_authoritative_tick_caches_source_grid_until_phrase_changes \
  tests/test_retained_score_pipeline.py::test_frame_path_never_reassembles_source_or_preparation_ink \
  tests/test_retained_score_pipeline.py::test_fingering_overlay_has_bounded_source_window \
  tests/test_midi_polyphonic_stems.py \
  tests/test_midi_visual_fast_path.py \
  tests/test_midi_calibration.py \
  tests/test_forgiving_midi_practice.py \
  tests/test_midi_only_product.py \
  tests/test_library.py \
  tests/test_midi_connection.py \
  tests/test_rolling_recovery_transition.py \
  tests/test_continuous_practice_loop.py::test_coda_practice_finishes_before_adaptive_retry_or_guided_switch \
  tests/test_assessment_service.py \
  tests/test_state_projection.py \
  tests/test_exercise_contracts.py \
  tests/test_exercise_strategies.py \
  tests/test_timing_live_integration.py \
  tests/test_strategy_pipeline.py \
  tests/test_timed_real_scores_and_recovery.py \
  tests/test_step4_algorithms.py \
  tests/test_step4_real_scores.py \
  tests/test_rubricnet_reproduction.py \
  tests/test_rubricnet_offline_integration.py \
  tests/test_moonlight_real_midi_beams.py \
  tests/test_shared_tempo_timeline.py \
  tests/test_live_input_view.py \
  tests/test_notation_coverage_report.py
