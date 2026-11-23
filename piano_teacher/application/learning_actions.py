"""Route the learner's listening and learning commands to their owners.

CourseFlow runs course steps and Free; LessonNavigation applies
navigation; ExposureWorkflows prepares Listen, Perform and Practice.
"""
from __future__ import annotations


class LearningActions:
    def __init__(self, *, lesson, transport, course, navigation,
                 exposure_workflows, measurement, clock):
        self.lesson = lesson
        self.transport = transport
        self.course = course
        self.navigation = navigation
        self.exposure_workflows = exposure_workflows
        self.measurement = measurement
        self.clock = clock

    def control_listening(self, action: str, kwargs: dict, *, effect=None) -> None:
        if action == "listen":
            if (self.lesson.flow_active and self.lesson.flow_state is not None
                    and self.lesson.flow_state.stage_key == self.lesson.plan.identity
                    and self.transport.mode != "listen"):
                # Listen again: the state machine plays it, then Free.
                self.course.flow_execute(self.lesson.flow_listen_again(),reason=action)
            else:
                self.exposure_workflows.prepare_listen(effect=effect,reason=action)
        elif action == "perform":
            self.exposure_workflows.prepare_perform(
                scope=str(kwargs.get("scope", "current")), effect=effect,
                reason=action)
        elif action == "practice_weak":
            self.navigation.practice_weak(effect=effect)
        elif action == "review_retry":
            self.navigation.review_retry(
                kwargs.get("first_bar"), kwargs.get("last_bar"), effect=effect)
        elif action == "seek":
            self.navigation.seek(kwargs.get("bar"), effect=effect)

    def control_learning(self, action: str, kwargs: dict, *, effect=None) -> None:
        if action == "learn_next":
            if (self.transport.mode != "learn" or self.lesson.guided_controller is None
                    or not self.lesson.guided_controller.snapshot(now=self.clock())["completed"]):
                raise ValueError("Find the current notes before continuing to the next idea")
            self.course.save_guided_preparation()
            if self.lesson.guided_return_context is not None:
                self.exposure_workflows.prepare_practice(effect=effect,reason=action)
            else:
                self.course.begin_course_stage(effect=effect,reason=action)
        elif action == "skip_stage":
            self.navigation.skip_stage(kwargs.get("reason"), effect=effect)
        elif action == "place_original":
            self.navigation.place_original(effect=effect)
        elif action == "revisit_trouble":
            self.navigation.revisit_trouble(
                kwargs.get("stage_key"), kwargs.get("start_beat"), effect=effect)
        elif action in ("learn", "learn_retry"):
            if action == "learn":
                self.lesson.set_course_guided(True)
                if "from_beat" not in kwargs:
                    self.course.begin_course_stage(
                        explicit_learn=True, effect=effect, reason=action)
                    return
            previous_start = (self.lesson.guided_beat_range[0]
                              if self.lesson.guided_beat_range else 0.0)
            self.course.begin_learn(
                from_beat=float(kwargs.get(
                    "from_beat",
                    previous_start if action == "learn_retry" else 0.0)),
                recovery=self.lesson.guided_return_context is not None and action == "learn_retry",
                effect=effect,reason=action)
        elif action == "open_at":
            self.navigation.open_selected_measure(kwargs, effect=effect)
        elif action == "hints":
            self.lesson.set_hints(
                bool(kwargs.get("enabled", False)), now=self.clock())
            if kwargs.get("enabled", False) and self.measurement.attempt_id is not None:
                self.measurement.use_assistance()
