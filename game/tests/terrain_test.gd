extends GdUnitTestSuite

## Технические тесты рельефа: правило грунта, форма мира у руин, LOD без щелей, минутный таймер.


func test_ground_of_dirt_wins_over_slope_and_stone_over_flat() -> void:
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_DIRT, Vector3.UP)).is_equal(WorldTerrain.Ground.DIRT)
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_DIRT, Vector3.RIGHT)).is_equal(WorldTerrain.Ground.DIRT)
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_STONE, Vector3.UP)).is_equal(WorldTerrain.Ground.STONE)


func test_ground_of_surface_is_grass_on_gentle_slope_and_stone_on_steep() -> void:
	var gentle := Vector3(0, 1, 0.5).normalized()
	var steep := Vector3(0, 1, 1).normalized()
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_SURFACE, gentle)).is_equal(WorldTerrain.Ground.GRASS)
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_SURFACE, steep)).is_equal(WorldTerrain.Ground.STONE)


func test_ground_of_surface_near_sea_is_sand_on_gentle_slope_only() -> void:
	var gentle := Vector3(0, 1, 0.5).normalized()
	var steep := Vector3(0, 1, 1).normalized()
	var beach := WorldTerrain.SAND_TOP - 0.5
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_SURFACE, gentle, beach)).is_equal(WorldTerrain.Ground.SAND)
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_SURFACE, steep, beach)).is_equal(WorldTerrain.Ground.STONE)
	assert_int(WorldTerrain.ground_of(WorldTerrain.INDEX_DIRT, gentle, beach)).is_equal(WorldTerrain.Ground.DIRT)


## Берег: к югу от руин рельеф уходит под воду, пляж — ниже SAND_TOP.
func test_generator_descends_south_of_ruins_below_sea() -> void:
	var gen := WorldTerrain.make_generator()
	var x := int(WorldTerrain.FLAT_CENTER.x)
	var far := int(WorldTerrain.COAST_START_Z + WorldTerrain.COAST_LENGTH)
	assert_float(_surface_y(gen, x, far)).is_less(WorldTerrain.SEA_Y)


## Под руинами и полем грунт ровный, на 0,1 м ниже пола: руины стоят на нём, герой сходит без ступеньки.
func test_generator_is_flat_under_ruins_and_field() -> void:
	var gen := WorldTerrain.make_generator()
	for p in [Vector2(-16, -24), Vector2(-16, 24), Vector2(48, -24), Vector2(48, 24), Vector2(0, 0), Vector2(28, 10)]:
		assert_float(_surface_y(gen, p.x, p.y)).is_equal_approx(WorldTerrain.FLAT_Y, 0.02)


## Дальние участки упрощаются без щелей: несколько LOD, переходные сетки Transvoxel, шейдер их сдвигает.
func test_lod_uses_transvoxel_transitions() -> void:
	var terrain := auto_free(WorldTerrain.new()) as WorldTerrain
	assert_int(terrain.lod_count).is_greater(1)
	var mesher := terrain.mesher as VoxelMesherTransvoxel
	assert_bool(mesher.transitions_enabled).is_true()
	var uniforms := (terrain.material as ShaderMaterial).shader.get_shader_uniform_list().map(func(u): return u.name)
	assert_array(uniforms).contains(["u_transition_mask"])


func test_autosave_timer_repeats_every_minute() -> void:
	var store := create_temp_dir("terrain_test")
	var terrain := WorldTerrain.new()
	terrain.save_path = store + "/terrain.sqlite"
	add_child(terrain)
	var timer := terrain.get_node("Autosave") as Timer
	assert_float(timer.wait_time).is_equal(60.0)
	assert_bool(timer.one_shot).is_false()
	assert_bool(timer.is_stopped()).is_false()
	terrain.free()


func _surface_y(gen: VoxelGenerator, x: float, z: float) -> float:
	var bounds := WorldTerrain.BOUNDS
	var buffer := VoxelBuffer.new()
	buffer.create(1, int(bounds.size.y), 1)
	buffer.set_channel_depth(VoxelBuffer.CHANNEL_INDICES, VoxelBuffer.DEPTH_8_BIT)
	gen.generate_block(buffer, Vector3i(roundi(x), int(bounds.position.y), roundi(z)), 0)
	for i in range(int(bounds.size.y) - 2, -1, -1):
		var s0 := buffer.get_voxel_f(0, i, 0, VoxelBuffer.CHANNEL_SDF)
		var s1 := buffer.get_voxel_f(0, i + 1, 0, VoxelBuffer.CHANNEL_SDF)
		if s0 < 0.0 and s1 >= 0.0:
			return bounds.position.y + i + s0 / (s0 - s1)
	return NAN
