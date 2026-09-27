shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_always, specular_schlick_ggx;

// Море: бирюза на мелководье уходит в синеву на глубине, пена у берега, мягкие волны.

uniform vec3 shallow_color : source_color = vec3(0.2, 0.8, 0.82);
uniform vec3 deep_color : source_color = vec3(0.114, 0.435, 0.549);
uniform vec3 foam_color : source_color = vec3(0.97, 0.96, 0.9);
// Глубина, на которой вода становится глубинной, м.
uniform float deep_at = 6.0;
// Ширина полосы пены у берега, м.
uniform float foam_width = 0.7;
uniform float wave_height = 0.12;
uniform float wave_speed = 0.6;

uniform sampler2D depth_texture : hint_depth_texture, filter_linear_mipmap;
uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;

varying vec3 world_pos;

float waves(vec2 p, float t) {
	return sin(p.x * 0.35 + t) * 0.5
		+ sin(p.y * 0.27 - t * 0.8) * 0.35
		+ sin((p.x + p.y) * 0.9 + t * 1.7) * 0.15;
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float t = TIME * wave_speed;
	VERTEX.y += waves(world_pos.xz, t) * wave_height;
	world_pos.y += waves(world_pos.xz, t) * wave_height;
}

void fragment() {
	float t = TIME * wave_speed;
	// Нормаль из производной волн — мелкая рябь.
	vec2 p = world_pos.xz;
	float e = 0.2;
	float hx = waves(p + vec2(e, 0.0), t * 1.3) - waves(p - vec2(e, 0.0), t * 1.3);
	float hz = waves(p + vec2(0.0, e), t * 1.3) - waves(p - vec2(0.0, e), t * 1.3);
	vec3 n_world = normalize(vec3(-hx * 0.6, 1.0, -hz * 0.6));
	NORMAL = normalize((VIEW_MATRIX * vec4(n_world, 0.0)).xyz);

	// Толщина воды до дна по лучу взгляда.
	float raw = texture(depth_texture, SCREEN_UV).r;
	vec4 ndc = vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	vec4 bottom = INV_PROJECTION_MATRIX * ndc;
	bottom.xyz /= bottom.w;
	float thickness = max(VERTEX.z - bottom.z, 0.0);

	float deep = smoothstep(0.0, deep_at, thickness);
	vec3 water = mix(shallow_color, deep_color, deep);
	vec3 below = texture(screen_texture, SCREEN_UV + NORMAL.xy * 0.01).rgb;
	float clarity = 1.0 - smoothstep(0.0, 1.5, thickness);
	vec3 color = mix(water, below * shallow_color * 1.4, clarity * 0.55);

	float foam_line = 1.0 - smoothstep(0.0, foam_width, thickness);
	float ripple = 0.5 + 0.5 * sin(thickness * 9.0 - TIME * 2.2 + p.x * 0.4);
	float foam = clamp(foam_line * (0.55 + 0.45 * ripple), 0.0, 1.0);

	ALBEDO = mix(color, foam_color, foam);
	ROUGHNESS = mix(0.06, 0.8, foam);
	METALLIC = 0.0;
	SPECULAR = 0.6;
	float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	ALPHA = clamp(mix(0.72, 0.97, deep) + fresnel * 0.2 + foam, 0.0, 1.0);
}
