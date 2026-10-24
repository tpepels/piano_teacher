extends RefCounted
# Source-event queues for stage reactions. NativeScoreFeedback owns visible
# score marks; these queues never draw or transform page-coordinate ink.
var marks: Array = []
var hit_pulses: Array = []
var wrong_ghosts: Array = []
var preview_pulses: Array = []
