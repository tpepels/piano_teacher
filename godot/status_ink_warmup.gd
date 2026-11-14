extends Node2D
## Renderer-owned, temporary GPU warmup layer.
## Its lifetime follows the score renderer, including early teardown.
## Never await frames from Main: source replacement may free Main first.
const KEEP_FRAMES := 3
var _remaining_frames := KEEP_FRAMES

func _ready() -> void:
    set_process(true)

func _process(_delta: float) -> void:
    _remaining_frames -= 1
    if _remaining_frames <= 0:
        queue_free()
