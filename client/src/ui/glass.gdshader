// Liquid Glass panel: blurred backdrop + tint + top highlight + soft refraction.
// The panel's StyleBoxFlat supplies the rounded shape (COLOR.a) and border.
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform float blur_lod = 3.2;
uniform vec4 tint : source_color = vec4(0.62, 0.74, 0.95, 1.0);
uniform float tint_strength = 0.18;
uniform float highlight = 0.09;
uniform float refraction = 0.006;

void fragment() {
	vec4 shape = COLOR;
	if (shape.a < 0.003) { discard; }
	vec2 off = (UV - 0.5) * refraction;
	vec3 bg = textureLod(screen_tex, SCREEN_UV - off, blur_lod).rgb;
	// smoky glass: dark enough that light text stays readable over bright sky and grass
	vec3 glass = mix(bg * 0.40 + vec3(0.02, 0.03, 0.06), tint.rgb * 0.45, tint_strength);
	glass += highlight * pow(1.0 - UV.y, 3.0);
	// shape.rgb carries the stylebox fill/border colour; strong alpha = border
	float border = smoothstep(0.35, 0.8, shape.a);
	vec3 col = mix(glass, shape.rgb, border * 0.85);
	COLOR = vec4(col, clamp(shape.a * 6.0, 0.0, 1.0));
}
