shader_type spatial;

// Материал рельефа по вокселям (TER-1.2). Сетка Transvoxel в режиме TEXTURES_SINGLE_S4 кладёт в CUSTOM1
// до четырёх индексов текстур (x) и их веса (y) по байту. Индексы — WorldTerrain.INDEX_*:
// 0 — поверхность: трава на пологом, песок на пологом ниже sand_top, камень на крутом; 1 — камень; 2 — земля;
// 3 — влажный песок: тронутый грунт пляжа у поверхности.
// Пороги уклона задаёт WorldTerrain, чтобы шейдер и WorldTerrain.ground_at красили одинаково.

uniform sampler2D grass_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D stone_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D dirt_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D sand_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform float tex_scale = 0.06;
uniform float grass_min_normal_y = 0.78;
uniform float grass_blend = 0.07;
uniform float sand_top = 35.5;
uniform float sand_blend = 0.8;
// Тёплый оттенок песка по палитре арт-направления: текстура Poly Haven сероватая.
uniform vec3 sand_tint = vec3(1.5, 1.3, 0.98);
// Тёплая олива травы по палитре: текстура сероватая.
uniform vec3 grass_tint = vec3(1.05, 1.05, 0.62);
// Пятна на ровном грунте по крупному шуму: сочная тёплая трава и песчаные проплешины.
uniform sampler2D patch_tex : filter_linear_mipmap, repeat_enable;
uniform vec3 lush_tint = vec3(0.95, 1.2, 0.55);
// Влажный песок: песок палитры темнее и насыщеннее, с блеском.
uniform vec3 wet_tint = vec3(0.84, 0.72, 0.56);
uniform float wet_roughness = 0.5;


varying vec3 world_pos;
varying vec3 world_normal;
// Доли материалов в вершине: x — поверхность, y — камень, z — земля, w — влажный песок.
varying vec4 v_ground;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);

	uint indices = floatBitsToUint(CUSTOM1.x);
	uint weights = floatBitsToUint(CUSTOM1.y);
	vec4 ground = vec4(0.0);
	for (uint i = 0u; i < 4u; i++) {
		uint index = (indices >> (8u * i)) & 255u;
		float weight = float((weights >> (8u * i)) & 255u) / 255.0;
		ground += weight * vec4(float(index == 0u), float(index == 1u), float(index == 2u), float(index == 3u));
	}
	v_ground = ground / max(ground.x + ground.y + ground.z + ground.w, 0.001);
}

vec3 triplanar(sampler2D tex, vec3 p, vec3 w) {
	return texture(tex, p.zy * tex_scale).rgb * w.x
		+ texture(tex, p.xz * tex_scale).rgb * w.y
		+ texture(tex, p.xy * tex_scale).rgb * w.z;
}

void fragment() {
	vec3 n = normalize(world_normal);
	// Проекцию текстуры выбирает нормаль грани, если нормаль вершины с ней сильно расходится: на остром стыке
	// шаров копания нормаль по полю расстояния смотрит вдоль стенки, и текстура растягивается в полосы.
	vec3 face = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
	vec3 texture_normal = mix(face, n, smoothstep(0.5, 0.8, abs(dot(n, face))));
	vec3 w = pow(abs(texture_normal), vec3(4.0));
	w /= (w.x + w.y + w.z);

	vec3 grass = triplanar(grass_tex, world_pos, w) * grass_tint;
	vec3 stone = triplanar(stone_tex, world_pos, w);
	vec3 dirt = triplanar(dirt_tex, world_pos, w);
	vec3 sand = triplanar(sand_tex, world_pos, w) * sand_tint;

	float flat_amount = smoothstep(grass_min_normal_y - grass_blend, grass_min_normal_y + grass_blend, n.y);
	float sand_amount = 1.0 - smoothstep(sand_top - sand_blend, sand_top + sand_blend, world_pos.y);
	float patch_value = texture(patch_tex, world_pos.xz * 0.015).r;
	vec3 lush = grass * lush_tint;
	grass = mix(grass, lush, smoothstep(0.55, 0.68, patch_value));
	grass = mix(grass, sand, smoothstep(0.4, 0.22, patch_value) * 0.7);
	vec3 surface = mix(stone, mix(grass, sand, sand_amount), flat_amount);
	vec3 wet = sand * wet_tint;
	ALBEDO = surface * v_ground.x + stone * v_ground.y + dirt * v_ground.z + wet * v_ground.w;
	ROUGHNESS = mix(0.95, wet_roughness, v_ground.w);
}
