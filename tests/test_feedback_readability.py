"""Feedback must leave engraved noteheads readable in actual rendered pixels."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_error_markers_preserve_the_notehead_pixels(tmp_path):
    godot=shutil.which('godot') or shutil.which('godot4')
    if not godot or not os.environ.get('DISPLAY'):
        pytest.skip('Actual graphical Godot required')
    script=tmp_path/'readability.gd'
    script.write_text('''extends SceneTree
func _initialize() -> void: call_deferred("run")
func run() -> void:
    root.size=Vector2i(800,600)
    var note:=ColorRect.new()
    note.color=Color("#C4CDC6")
    note.position=Vector2(395,295)
    note.size=Vector2(10,10)
    root.add_child(note)
    var overlay=load("res://score_overlay.gd").new()
    overlay.size=Vector2(800,600)
    overlay.image_size=overlay.size
    overlay.active_page=0
    root.add_child(overlay)
    for status in ["wrong","missed","early","late","short","long","assisted","correct"]:
        overlay.marks=[{"page":0,"x":.5,"y":.5,"status":status}]
        overlay.queue_redraw()
        await process_frame
        await RenderingServer.frame_post_draw
        var color:Color=root.get_texture().get_image().get_pixel(400,300)
        if color.r < .70 or color.g < .70:
            print("OBSCURED_NOTE:",status," ",color)
            quit(1)
            return
    print("NOTEHEAD_INK_PRESERVED")
    quit()
''')
    result=subprocess.run([godot,'--path',str(ROOT/'godot'),'--windowed','--rendering-method','gl_compatibility','--script',str(script)],capture_output=True,text=True,timeout=20)
    output=result.stdout+result.stderr
    assert result.returncode==0 and 'SCRIPT ERROR' not in output,output
    assert 'NOTEHEAD_INK_PRESERVED' in output
