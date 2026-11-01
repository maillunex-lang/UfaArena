// Round avatar mask with a soft edge.
shader_type canvas_item;
void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float d = distance(UV, vec2(0.5));
	c.a *= 1.0 - smoothstep(0.47, 0.5, d);
	COLOR = c * COLOR;
}
