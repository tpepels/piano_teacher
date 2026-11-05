extends ColorRect
## GPU-drawn additive bloom, confined to its own 2D quad.
## The GL Compatibility renderer cannot use Forward+ HDR 2D glow.
## No screen texture, second viewport, per-frame texture generation or
## painter-side duplicated shadow loops.
const GlowShader := preload("res://mint_glow.gdshader")

func _init() -> void:
    name = "MintGlow"
    color = Color.WHITE
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    var glow_material := ShaderMaterial.new()
    glow_material.shader = GlowShader
    material = glow_material

func configure(shape: int, strength: float = 1.0,
        tint: Color = Color("#3DF1AC")) -> void:
    var shader_material := material as ShaderMaterial
    shader_material.set_shader_parameter("shape", shape)
    shader_material.set_shader_parameter("intensity", strength)
    shader_material.set_shader_parameter("tint", tint)
