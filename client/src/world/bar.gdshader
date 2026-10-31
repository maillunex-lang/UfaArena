// Billboard HP/energy bar in a single quad (no per-frame mesh edits).
shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, shadows_disabled;

uniform float hp : hint_range(0.0, 1.0) = 1.0;
uniform float hp_trail : hint_range(0.0, 1.0) = 1.0;
uniform float shield : hint_range(0.0, 1.0) = 0.0;
uniform float energy : hint_range(0.0, 1.0) = 0.0;
uniform vec4 hp_color : source_color = vec4(0.36, 0.86, 0.45, 1.0);

void vertex() {
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
}

void fragment() {
	vec2 uv = UV;
	vec3 col = vec3(0.05, 0.06, 0.1);
	float a = 0.85;
	// border
	float bx = 0.012, by = 0.08;
	bool border = uv.x < bx || uv.x > 1.0 - bx || uv.y < by || uv.y > 1.0 - by;
	if (uv.y < 0.68) {
		float x = (uv.x - bx) / (1.0 - 2.0 * bx);
		if (x < hp_trail) col = vec3(0.95, 0.85, 0.75);
		if (x < hp) col = hp_color.rgb * (1.1 - uv.y * 0.5);
		if (shield > 0.0 && x < shield) col = mix(col, vec3(0.55, 0.85, 1.0), 0.65);
	} else {
		float x = (uv.x - bx) / (1.0 - 2.0 * bx);
		if (x < energy) col = mix(vec3(1.0, 0.75, 0.2), vec3(1.0, 0.95, 0.5), energy);
		else col = vec3(0.12, 0.1, 0.18);
	}
	if (border) col = vec3(0.0);
	ALBEDO = col;
	ALPHA = a;
}
